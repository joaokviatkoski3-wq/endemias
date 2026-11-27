"""Controle de folgas e faltas com contas e saldos inteiramente fictícios."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
import re
import shutil
import tempfile
from threading import Barrier
import unittest
from unittest import mock

import app
import criar_banco
from app_core import auth, db, esporotricose, pessoal_folgas


API = "/api/pessoal/folgas"
PAGINA = "/admin/agentes?aba=folgas"
AGORA = datetime(2026, 11, 27, 12, tzinfo=pessoal_folgas.FUSO_LOCAL)


class PessoalFolgasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = tempfile.TemporaryDirectory(prefix="endemias-pessoal-")
        cls.addClassCleanup(area.cleanup)
        cls.area = Path(area.name)
        cls.seed = cls.area / "seed.db"
        with mock.patch.object(criar_banco, "BANCO", str(cls.seed)), redirect_stdout(StringIO()):
            criar_banco.main()
        cls.senha_hash = auth.hash_senha("SenhaSomenteDeTeste123!")
        with closing(db.connect(cls.seed)) as conn, conn:
            conn.execute("UPDATE usuarios SET nivel='superadmin', senha_hash=? WHERE id_usuario=1", (cls.senha_hash,))
            conn.executemany(
                """INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em)
                   VALUES (?,?,?,?,?,'2026-11-01')""",
                [(uid, f"teste-{uid}", f"Conta Fictícia {uid}", cls.senha_hash, nivel)
                 for uid, nivel in ((2, "admin"), (3, "operador"), (4, "visualizador"), (5, "usuario"))],
            )
            conn.execute("INSERT INTO agentes(id_agente,nome,nome_completo) VALUES(11,'Apelido','Servidor Fictício')")
            conn.execute("INSERT INTO agentes(id_agente,nome,ativo) VALUES(12,'Servidor Inativo Fictício',0)")
            conn.execute("INSERT INTO agentes(id_agente,nome) VALUES(13,'Outro Servidor Fictício')")

    def setUp(self):
        area = tempfile.TemporaryDirectory(dir=self.area)
        self.addCleanup(area.cleanup)
        self.directory = Path(area.name)
        self.path = self.directory / "ensaio.db"
        shutil.copyfile(self.seed, self.path)
        self.config = dict(
            DB_PATH=str(self.path), DB_BACKEND="sqlite", TESTING=True,
            WTF_CSRF_ENABLED=True, SETORES_ENABLED=True, TERMOS_USO_ENABLED=False,
            SETOR="endemias", AMBIENTE="teste", ACESSO_EXTERNO=False,
            SECRET_KEY_PATH=str(self.directory / "chave"), LOG_PATH=str(self.directory / "teste.log"),
            BACKUP_DIR=str(self.directory / "backups"), BACKUP_COMPLETO_DIR=str(self.directory / "completos"),
            UPLOAD_TEMP=str(self.directory / "uploads"), ANEXOS_DIR=str(self.directory / "anexos"),
            KOBO_CONFIG_PATH=str(self.directory / "kobo_config.json"),
        )
        self.enterContext(mock.patch.object(app, "_configure_logging"))
        self.app = app.create_app(self.config)
        self.clock = self.enterContext(mock.patch.object(pessoal_folgas, "_agora", return_value=AGORA))
        self.admin = self.logged(self.app, 2)

    def logged(self, application, uid):
        client = application.test_client()
        with application.app_context(), client.session_transaction() as session:
            session.update(uid=uid, nome=f"Conta Fictícia {uid}", auth_token=auth.token_sessao(self.senha_hash))
        return client

    def csrf(self, client, path=PAGINA):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(token)
        return {"X-CSRFToken": token.group(1)}

    def post(self, client, path, payload, expected, headers=None):
        response = client.post(API + path, json=payload, headers=headers or self.csrf(client))
        self.assertEqual(response.status_code, expected, response.get_data(as_text=True))
        return response.json

    def get(self, client, path, expected=200, query=None):
        response = client.get(API + path, query_string=query)
        self.assertEqual(response.status_code, expected, response.get_data(as_text=True))
        self.assertIn("no-store", response.headers["Cache-Control"])
        return response.json

    def credito(self, expected=201, client=None, **overrides):
        payload = dict(id_agente=11, data_aquisicao="2026-11-21", validade="2026-12-31",
                       unidades=2, origem="sabado", descricao="Plantão fictício autorizado", referencia="Ofício 123")
        return self.post(client or self.admin, "/creditos", {**payload, **overrides}, expected)

    def ocorrencia(self, expected=201, client=None, **overrides):
        payload = dict(id_agente=11, tipo="folga", data="2026-12-04", dia_inteiro=True)
        return self.post(client or self.admin, "/ocorrencias", {**payload, **overrides}, expected)

    def extrato(self, client=None, agente=11):
        return self.get(client or self.admin, f"/servidores/{agente}/extrato")

    def test_somente_admin_e_superadmin_acessam_pagina_e_todas_as_apis(self):
        leitura = (
            ("/saldos", None), ("/ocorrencias", {"inicio": "2026-11-01", "fim": "2026-12-01"}),
            ("/servidores/11/extrato", None),
        )
        escrita = (
            "/creditos", "/creditos/1/cancelar", "/ocorrencias", "/ocorrencias/1/confirmar",
            "/ocorrencias/1/cancelar", "/ocorrencias/1/classificar",
        )
        anonimo = self.app.test_client()
        self.assertIn(anonimo.get(PAGINA).status_code, (302, 401))
        self.assertIn(anonimo.get(API + "/saldos").status_code, (302, 401))
        for uid in (3, 4, 5):
            with self.subTest(uid=uid):
                cliente = self.logged(self.app, uid)
                self.assertEqual(cliente.get(PAGINA).status_code, 403)
                token = self.csrf(cliente, "/agenda")
                for caminho, query in leitura:
                    self.get(cliente, caminho, 403, query=query)
                for caminho in escrita:
                    self.post(cliente, caminho, {}, 403, headers=token)
        for uid in (1, 2):
            with self.subTest(uid=uid):
                cliente = self.logged(self.app, uid)
                html = cliente.get(PAGINA).get_data(as_text=True)
                self.assertIn("Folgas e Ausências", html)
                self.assertIn("Servidores", html)
                for caminho, query in leitura:
                    self.get(cliente, caminho, query=query)
        self.assertIn("Novo servidor", self.admin.get("/admin/agentes").get_data(as_text=True))

    def test_escrita_exige_csrf_e_validacao_de_entrada(self):
        response = self.admin.post(API + "/creditos", json={"id_agente": 11})
        self.assertEqual(response.status_code, 400)
        self.credito(expected=400, unidades=1.5)
        self.credito(expected=400, unidades=True)
        self.credito(expected=400, validade="2026-02-30")
        self.credito(expected=400, validade="2026-11-20")
        self.ocorrencia(expected=400, dia_inteiro=False, hora_inicio="08:00")
        self.ocorrencia(expected=400, dia_inteiro=False, hora_inicio="12:00", hora_fim="08:00")
        self.get(self.admin, "/ocorrencias", 400, {"inicio": "2026-12-04", "fim": "2026-12-04"})
        self.get(self.admin, "/ocorrencias", 400, {"inicio": "invalida", "fim": "2026-12-04"})
        self.get(self.admin, "/servidores/999/extrato", 404)
        self.assertEqual(self.extrato()["creditos"], [])

    def test_saldo_global_e_consumo_combina_creditos_que_vencem_primeiro(self):
        ambiental = app.create_app({**self.config, "SETOR": "ambiental"})
        superadmin_ambiental = self.logged(ambiental, 1)
        longo = self.credito(client=superadmin_ambiental, unidades=2, validade="2027-01-01")["id"]
        curto = self.credito(unidades=1, validade="2026-12-04")["id"]
        self.assertEqual(self.extrato()["saldo"]["a_vencer"], 1)
        folga = self.ocorrencia()["id"]

        for cliente in (self.admin, superadmin_ambiental):
            extrato = self.extrato(cliente)
            self.assertEqual(extrato["saldo"]["disponivel"], 1)
            self.assertEqual(extrato["saldo"]["reservado"], 2)
            self.assertEqual(extrato["saldo"]["utilizado"], 0)
            creditos = {item["id_credito"]: item for item in extrato["creditos"]}
            self.assertEqual((creditos[longo]["setor"], creditos[curto]["setor"]), ("ambiental", "endemias"))
            self.assertEqual(creditos[curto]["disponivel"], 0)
            self.assertEqual(creditos[longo]["disponivel"], 1)
            consumos = {(item["id_credito"], item["id_ocorrencia"], item["status"], item["unidades"])
                        for item in extrato["consumos"]}
            self.assertEqual(consumos, {(longo, folga, "reservado", 1), (curto, folga, "reservado", 1)})
        self.ocorrencia(expected=409, data="2026-12-07")

    def test_retroativos_requerem_motivo_e_confirmacao_respeita_data_e_horario(self):
        self.credito(unidades=5)
        self.ocorrencia(expected=400, data="2026-11-26")
        retroativa = self.ocorrencia(data="2026-11-26", observacao="Regularização de ensaio")["id"]
        parcial = self.ocorrencia(data="2026-11-27", dia_inteiro=False, hora_inicio="13:00", hora_fim="17:00")["id"]
        integral = self.ocorrencia(data="2026-11-28")["id"]
        ocorrencias = {item["id_ocorrencia"]: item for item in self.extrato()["ocorrencias"]}
        self.assertEqual(ocorrencias[retroativa]["status"], "aguardando_confirmacao")
        self.assertEqual(ocorrencias[parcial]["status"], "agendada")
        self.assertEqual(ocorrencias[integral]["status"], "agendada")

        self.post(self.admin, f"/ocorrencias/{retroativa}/confirmar", {}, 200)
        self.post(self.admin, f"/ocorrencias/{retroativa}/confirmar", {}, 409)
        self.post(self.admin, f"/ocorrencias/{parcial}/confirmar", {}, 409)
        self.clock.return_value = AGORA.replace(hour=17, minute=1)
        self.post(self.admin, f"/ocorrencias/{parcial}/confirmar", {}, 200)
        self.clock.return_value = AGORA.replace(day=28, hour=23, minute=59)
        self.post(self.admin, f"/ocorrencias/{integral}/confirmar", {}, 409)
        self.clock.return_value = AGORA.replace(day=29, hour=0)
        self.post(self.admin, f"/ocorrencias/{integral}/confirmar", {}, 200)
        saldo = self.extrato()["saldo"]
        self.assertEqual((saldo["reservado"], saldo["utilizado"], saldo["disponivel"]), (0, 5, 0))

    def test_creditos_respeitam_aquisicao_e_expiram_sem_saida_do_historico(self):
        vencido = self.credito(validade="2026-11-25", unidades=2)["id"]
        posterior = self.credito(data_aquisicao="2026-11-26", unidades=1)["id"]
        self.ocorrencia(expected=409, data="2026-11-20", observacao="Ajuste de teste",
                        dia_inteiro=True)
        saldo = self.extrato()["saldo"]
        self.assertEqual((saldo["concedido"], saldo["disponivel"], saldo["expirado"]), (3, 1, 2))
        self.ocorrencia(data="2026-11-25", observacao="Ajuste de teste", dia_inteiro=True)
        extrato = self.extrato()
        self.assertEqual(extrato["consumos"][0]["id_credito"], vencido)
        self.assertEqual((extrato["saldo"]["reservado"], extrato["saldo"]["disponivel"]), (2, 1))
        self.assertCountEqual([item["id_credito"] for item in extrato["creditos"]], [vencido, posterior])

    def test_cancelamentos_mantem_extrato_e_auditoria_e_estornam_reserva(self):
        credito = self.credito()["id"]
        folga = self.ocorrencia()["id"]
        self.post(self.admin, f"/creditos/{credito}/cancelar", {"motivo": "Concessão duplicada"}, 409)
        self.post(self.admin, f"/ocorrencias/{folga}/cancelar", {"motivo": ""}, 400)
        self.post(self.admin, f"/ocorrencias/{folga}/cancelar", {"motivo": "Mudança da escala"}, 200)
        extrato = self.extrato()
        self.assertEqual(extrato["saldo"]["disponivel"], 2)
        self.assertEqual(extrato["saldo"]["reservado"], 0)
        self.assertEqual(extrato["ocorrencias"][0]["status"], "cancelada")
        self.assertEqual(extrato["consumos"][0]["status"], "cancelado")
        self.post(self.admin, f"/creditos/{credito}/cancelar", {"motivo": "Concessão duplicada"}, 200)
        extrato = self.extrato()
        self.assertEqual(extrato["saldo"]["disponivel"], 0)
        self.assertEqual(extrato["creditos"][0]["status"], "cancelado")

        eventos = db.query(str(self.path), """SELECT acao, usuario_id, setor FROM auditoria_eventos
                                               WHERE acao LIKE 'pessoal_%' ORDER BY id_evento""")
        self.assertEqual([evento["acao"] for evento in eventos], [
            "pessoal_credito_criado", "pessoal_ocorrencia_criada", "pessoal_ocorrencia_cancelada", "pessoal_credito_cancelado",
        ])
        self.assertTrue(all((evento["usuario_id"], evento["setor"]) == (2, "endemias") for evento in eventos))

    def test_falta_parcial_nao_abate_saldo_e_nao_se_sobrepoe_a_outra_ocorrencia(self):
        self.credito()
        falta = self.ocorrencia(tipo="falta", data="2026-11-27", dia_inteiro=False, hora_inicio="08:15",
                                hora_fim="10:20", classificacao="pendente")["id"]
        self.ocorrencia(tipo="falta", data="2026-11-27", expected=409, dia_inteiro=False, hora_inicio="10:19",
                        hora_fim="11:00", classificacao="pendente")
        self.ocorrencia(tipo="falta", data="2026-11-27", dia_inteiro=False, hora_inicio="10:20",
                        hora_fim="11:00", classificacao="pendente")
        self.ocorrencia(data="2026-11-27", expected=409)
        self.post(self.admin, f"/ocorrencias/{falta}/classificar", {"classificacao": "abonada"}, 400)
        self.post(self.admin, f"/ocorrencias/{falta}/classificar",
                  {"classificacao": "abonada", "motivo": "Documento validado pela chefia"}, 200)
        self.post(self.admin, f"/ocorrencias/{falta}/confirmar", {}, 409)
        extrato = self.extrato()
        self.assertEqual(extrato["saldo"]["disponivel"], 2)
        self.assertEqual(extrato["consumos"], [])
        dados = next(item for item in extrato["ocorrencias"] if item["id_ocorrencia"] == falta)
        self.assertEqual((dados["classificacao"], dados["status"], dados["hora_inicio"], dados["hora_fim"]),
                         ("abonada", "registrada", "08:15", "10:20"))

    def test_filtros_periodo_exclusivo_servidor_tipo_e_canceladas(self):
        self.credito(unidades=4)
        self.credito(id_agente=13)
        consulta = dict(inicio="2026-11-27", fim="2026-12-04", id_agente=11, tipo="folga")
        dentro = self.ocorrencia(data="2026-11-30")["id"]
        self.ocorrencia(data="2026-12-04")
        self.ocorrencia(id_agente=13, data="2026-11-30")
        self.ocorrencia(tipo="falta", data="2026-11-27", classificacao="pendente")
        eventos = self.get(self.admin, "/ocorrencias", query=consulta)["ocorrencias"]
        self.assertEqual([item["id_ocorrencia"] for item in eventos], [dentro])
        self.post(self.admin, f"/ocorrencias/{dentro}/cancelar", {"motivo": "Mudança de escala"}, 200)
        self.assertEqual(self.get(self.admin, "/ocorrencias", query=consulta)["ocorrencias"], [])
        eventos = self.get(self.admin, "/ocorrencias", query={**consulta, "incluir_canceladas": 1})["ocorrencias"]
        self.assertEqual([item["status"] for item in eventos], ["cancelada"])

    def test_reservas_concorrentes_so_podem_usar_o_mesmo_credito_uma_vez(self):
        self.credito(unidades=1)
        barreira = Barrier(2)

        def reservar(dia):
            dados = dict(id_agente=11, tipo="folga", data=dia, dia_inteiro=False,
                         hora_inicio="08:00", hora_fim="12:00")
            with closing(db.connect(str(self.path))) as conn:
                barreira.wait(timeout=10)
                try:
                    with conn:
                        pessoal_folgas.criar_ocorrencia(conn, dados, 2, "endemias")
                    return "gravada"
                except pessoal_folgas.Conflito:
                    return "conflito"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(reservar, ("2026-12-02", "2026-12-03"), timeout=15))
        self.assertCountEqual(resultados, ["gravada", "conflito"])
        extrato = self.extrato()
        self.assertEqual(extrato["saldo"]["disponivel"], 0)
        self.assertEqual(extrato["saldo"]["reservado"], 1)
        self.assertEqual(len(extrato["ocorrencias"]), 1)
        self.assertEqual(len(extrato["consumos"]), 1)

    def test_falha_na_auditoria_reverte_ocorrencia_e_reserva_juntas(self):
        self.credito()
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        with mock.patch("blueprints.controle_pessoal.audit.registrar_evento", side_effect=RuntimeError("Falha simulada")):
            response = self.admin.post(API + "/ocorrencias", headers=self.csrf(self.admin), json={
                "id_agente": 11, "tipo": "folga", "data": "2026-12-04", "dia_inteiro": True,
            })
        self.assertEqual(response.status_code, 500)
        extrato = self.extrato()
        self.assertEqual(extrato["ocorrencias"], [])
        self.assertEqual(extrato["consumos"], [])
        self.assertEqual((extrato["saldo"]["disponivel"], extrato["saldo"]["reservado"]), (2, 0))

    def test_normalizacao_legada_preserva_agente_com_historico_de_folga(self):
        with closing(db.connect(str(self.path))) as conn, conn:
            conn.execute("INSERT INTO agentes(id_agente,nome) VALUES(20,'cecon'), (21,'Ceccon')")
        credito = self.credito(id_agente=20)["id"]
        with closing(db.connect(str(self.path))) as conn, conn:
            esporotricose._normalizar_agentes_existentes(conn)
        extrato = self.extrato(agente=20)
        self.assertEqual(extrato["creditos"][0]["id_credito"], credito)
        self.assertEqual(extrato["saldo"]["disponivel"], 2)
        self.assertEqual(self.extrato(agente=21)["creditos"], [])

    def test_inativacao_bloqueia_novos_lancamentos_e_mantem_extrato_e_estorno(self):
        credito = self.credito(id_agente=13)["id"]
        folga = self.ocorrencia(id_agente=13)["id"]
        with closing(db.connect(str(self.path))) as conn, conn:
            conn.execute("UPDATE agentes SET ativo=0 WHERE id_agente=13")

        self.credito(id_agente=13, expected=409)
        self.ocorrencia(id_agente=13, tipo="falta", data="2026-11-27", expected=409)
        saldo = self.extrato(agente=13)["saldo"]
        self.assertFalse(saldo["ativo"])
        self.assertEqual(saldo["reservado"], 2)
        self.post(self.admin, f"/ocorrencias/{folga}/cancelar", {"motivo": "Saída do servidor"}, 200)
        extrato = self.extrato(agente=13)
        self.assertEqual(extrato["consumos"][0]["id_credito"], credito)
        self.assertEqual(extrato["consumos"][0]["status"], "cancelado")

    def test_adiantamento_parcial_confirmado_compensado_e_revertido(self):
        self.credito(unidades=1)
        self.ocorrencia(data="2026-11-26", observacao="Retroativa", expected=409)
        self.ocorrencia(data="2026-11-27", autorizar_adiantamento=True, expected=400)
        folga = self.ocorrencia(data="2026-11-26", autorizar_adiantamento=True,
                                observacao="Plantão reprogramado")["id"]
        saldo = self.extrato()["saldo"]
        self.assertEqual((saldo["saldo_liquido"], saldo["adiantado_reservado"], saldo["em_debito"]), (-1, 1, 0))
        rota = f"/ocorrencias/{folga}/compensar"
        baixa = {"unidades": 1, "origem": "credito", "motivo": "Saldo da campanha"}
        self.post(self.admin, rota, baixa, 409)
        self.post(self.admin, f"/ocorrencias/{folga}/confirmar", {}, 200)
        self.assertEqual(self.extrato()["saldo"]["em_debito"], 1)
        self.post(self.admin, rota, baixa, 409)
        credito = self.credito(data_aquisicao="2026-11-27", unidades=1)["id"]
        self.ocorrencia(data="2026-11-30", dia_inteiro=False, hora_inicio="08:00",
                        hora_fim="12:00", expected=409)
        self.post(self.admin, rota, baixa, 201)
        extrato = self.extrato()
        self.assertEqual((extrato["saldo"]["em_debito"], extrato["saldo"]["disponivel"]), (0, 0))
        self.assertEqual(extrato["compensacoes"][0]["id_credito"], credito)
        self.post(self.admin, rota, baixa, 409)
        self.post(self.admin, f"/creditos/{credito}/cancelar", {"motivo": "Teste"}, 409)
        self.post(self.admin, f"/ocorrencias/{folga}/cancelar", {"motivo": "Teste"}, 409)
        baixa_id = extrato["compensacoes"][0]["id_compensacao"]
        self.post(self.logged(self.app, 1), f"/compensacoes/{baixa_id}/apagar",
                  {"confirmacao": "APAGAR", "motivo": "erro_lancamento"}, 200)
        self.assertEqual(self.extrato()["saldo"]["em_debito"], 1)
        self.post(self.admin, rota, {**baixa, "origem": "ferias"}, 201)
        extrato = self.extrato()
        self.assertIsNone(extrato["compensacoes"][0]["id_credito"])
        self.assertEqual(extrato["saldo"]["saldo_liquido"], 1)

    def test_apagar_servidor_isola_historico_e_credito_vinculado(self):
        superadmin = self.logged(self.app, 1)
        credito = self.credito()["id"]
        folga = self.ocorrencia()["id"]
        self.credito(id_agente=13)
        motivo = {"confirmacao": "APAGAR", "motivo": "lancamento_teste"}
        alvo = "/servidores/11/apagar-historico"
        self.post(self.admin, alvo, motivo, 403)
        self.post(superadmin, alvo, {**motivo, "confirmacao": ""}, 400)
        self.post(superadmin, f"/creditos/{credito}/apagar", motivo, 409)
        self.post(superadmin, f"/ocorrencias/{folga}/apagar", motivo, 200)
        self.assertEqual(self.extrato()["saldo"]["disponivel"], 2)
        self.assertEqual(self.extrato()["consumos"], [])
        self.ocorrencia(data="2026-11-26", observacao="Registro retroativo",
                        autorizar_adiantamento=True)
        self.post(superadmin, alvo, motivo, 200)
        self.post(superadmin, alvo, motivo, 409)
        self.assertEqual(self.extrato()["saldo"]["saldo_liquido"], 0)
        self.assertEqual(self.extrato()["ocorrencias"], [])
        self.assertEqual(self.extrato()["creditos"], [])
        self.assertEqual(self.extrato(agente=13)["saldo"]["disponivel"], 2)
        with closing(db.connect(str(self.path))) as conn:
            row = conn.execute("SELECT detalhes_json FROM auditoria_eventos WHERE acao='pessoal_historico_apagado'").fetchone()
        self.assertIn("lancamento_teste", row[0])

    def test_relatorios_e_exportacoes_usam_o_mesmo_recorte_inclusivo(self):
        from openpyxl import load_workbook
        import fitz

        self.credito(data_aquisicao="2026-11-27", unidades=1, descricao="=Texto administrativo")
        self.credito(id_agente=13, descricao="PLANTAO FORA DO FILTRO")
        self.ocorrencia(data="2026-11-27", autorizar_adiantamento=True, observacao="Urgência fictícia")
        query = {"inicio": "2026-11-27", "fim": "2026-11-27", "id_agente": 11}
        pagina = self.admin.get("/admin/agentes", query_string={"aba": "relatorios", **query})
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("Urgência fictícia", pagina.get_data(as_text=True))
        self.assertNotIn("PLANTAO FORA DO FILTRO", pagina.get_data(as_text=True))
        xlsx = self.admin.get("/admin/agentes/relatorios/xlsx", query_string=query)
        self.assertEqual(xlsx.status_code, 200)
        self.assertIn("no-store", xlsx.headers["Cache-Control"])
        with closing(load_workbook(BytesIO(xlsx.data))) as livro:
            self.assertEqual(livro.sheetnames, ["Saldos atuais", "Créditos concedidos", "Folgas e faltas", "Compensações"])
            self.assertEqual(livro["Saldos atuais"]["C5"].value, -0.5)
            self.assertEqual(livro["Créditos concedidos"]["H5"].value, "=Texto administrativo / Ofício 123")
            self.assertEqual(livro["Créditos concedidos"]["H5"].data_type, "s")
            self.assertEqual(livro["Folgas e faltas"]["H5"].value, "Urgência fictícia")
        pdf = self.admin.get("/admin/agentes/relatorios/pdf", query_string=query)
        self.assertEqual(pdf.status_code, 200)
        with fitz.open(stream=pdf.data, filetype="pdf") as arquivo:
            texto = "\n".join(pagina.get_text() for pagina in arquivo)
        self.assertIn("Urgência fictícia", texto)
        self.assertNotIn("PLANTAO FORA DO FILTRO", texto)
        operador = self.logged(self.app, 3)
        self.assertEqual(operador.get("/admin/agentes/relatorios/pdf", query_string=query).status_code, 403)
