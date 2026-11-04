"""Regressões dos casos da auditoria de 30/10, com dados sintéticos isolados."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import threading
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from flask import Flask
from blueprints.liraa import bp as liraa_bp
from blueprints.auth import bp as auth_bp
from app_core import db, liraa, liraa_kobo as kobo, liraa_boletim as boletim
from app_core import liraa_laboratorio as lab, liraa_modelo as modelo, liraa_operacional as op, liraa_xlsform as xls
from tests import test_liraa_operacao as fixtures


class CorrecoesLiraaTests(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.OperacaoTests()
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.target, self.ciclo, self.base = self.env.target, self.env.ciclo, self.env.base

    def grupo(self):
        return boletim.resumir(self.target, self.ciclo, self.base)["grupos"][0]

    def test_todos_tipos_publicados_consolidam_e_preservam_subtipo(self):
        for i, tipo in enumerate(("residencia", "comercio", "outros", "terreno_baldio", "rco")):
            r = self.env.registro(str(i))
            r["Dados_visita"].update(Imovel=tipo, Numero=i + 1)
            r["group_jr1vc40"][0]["N_mero_do_tubito"] = 100 + i
            kobo.importar(self.target, self.ciclo, [r])
        for tube in lab.listar(self.target, self.ciclo):
            lab.salvar(self.target, tube["id_tubito"], self.env.payload(aegypt_larvas="2", albopictus_pupas="1"), self.env.user)
        g = self.grupo()
        self.assertEqual((g["trabalhados"], g["aegypt_tb"], g["aegypt_outros"], g["albopictus_outros"]), (5, 1, 4, 4))
        self.assertFalse(g["parcial"])
        self.assertEqual({v["tipo_imovel"] for v in kobo.listar(self.target)}, {"residencia", "comercio", "outros", "terreno_baldio", "rco"})

    def test_quarteirao_outros_lote_preserva_vinculos_e_decimais(self):
        good = self.env.registro("outro")
        municipal = good["Dados_visita"]["Quarteir_o"]
        good["Dados_visita"].update(Quarteir_o="outros", Quarteir_o_outros=municipal)
        outside = self.env.registro("fora")
        outside["Dados_visita"].update(Quarteir_o="outros", Quarteir_o_outros="408,1")
        self.assertEqual(kobo.importar(self.target, self.ciclo, [good, outside]), 2)
        visits = {v["kobo_uuid"]: v for v in kobo.listar(self.target)}
        self.assertEqual(visits["outro"]["situacao_vinculo"], "sorteado")
        self.assertEqual(visits["fora"]["quarteirao"], "408.1")
        self.assertNotEqual(visits["fora"]["situacao_vinculo"], "sorteado")
        good["_uuid"] = "invalido"
        good["Dados_visita"]["Quarteir_o_outros"] = ""
        with self.assertRaises(kobo.LiraaKoboError):
            kobo.importar(self.target, self.ciclo, [good])
        self.assertEqual(len(kobo.listar(self.target)), 2)

    def test_coleta_e_acs_complementares_persistem_sem_migracao(self):
        r = self.env.registro("coleta", tubitos=0, Houve_coleta="sim", ACS="outros", ACS_outros="ACS sintético")
        kobo.importar(self.target, self.ciclo, [r])
        v = kobo.listar(self.target)[0]
        self.assertEqual(v["acs_outros"], "ACS sintético")
        self.assertEqual(v["houve_coleta"], "sim")
        self.assertTrue(v["avisos"])
        self.assertEqual(self.grupo()["coletas_inconsistentes"], 1)
        self.assertTrue(self.grupo()["parcial"])
        self.assertEqual(lab.painel(self.target, {})["total_pendentes"], 0)
        self.assertTrue(kobo.previa(self.target, self.ciclo, [r])[0]["avisos"])

    def test_coleta_nao_com_tubos_e_tubo_sem_numero_sao_sinalizados(self):
        r = self.env.registro(Houve_coleta="nao")
        r["group_jr1vc40"][0]["N_mero_do_tubito"] = ""
        kobo.importar(self.target, self.ciclo, [r])
        self.assertEqual(len(kobo.listar(self.target)[0]["avisos"]), 2)
        self.assertEqual(self.grupo()["coletas_inconsistentes"], 1)

    def test_duplicidades_apenas_alertam_sem_excluir_contagens(self):
        kobo.importar(self.target, self.ciclo, [self.env.registro("um"), self.env.registro("dois")])
        g = self.grupo()
        self.assertEqual((g["trabalhados"], g["visitas_suspeitas"], g["tubitos_repetidos"]), (2, 2, 2))
        self.assertTrue(all(v["avisos"] for v in kobo.listar(self.target)))
        self.assertTrue(all(t["numero_repetido"] for t in lab.listar(self.target)))
        t = lab.listar(self.target)[0]
        lab.salvar(self.target, t["id_tubito"], self.env.payload(numero_tubito="200"), self.env.user)
        self.assertFalse(any(t["numero_repetido"] for t in lab.listar(self.target)))

    def test_corrigir_visita_preserva_leitura_uuid_plano_e_tratamento(self):
        r = self.env.registro(tratamento_001={"foi_tratado": "sim", "Quantidade_carga_gr": 2})
        kobo.importar(self.target, self.ciclo, [r])
        t = lab.listar(self.target)[0]
        lab.salvar(self.target, t["id_tubito"], self.env.payload(aegypt_larvas="3"), self.env.user)
        v = kobo.listar(self.target)[0]
        eventos = []
        kobo.corrigir(self.target, v["id_visita"], {"versao": v["versao_dados"], "motivo": "Tipo conferido", "tipo_imovel": "terreno_baldio"}, auditar=lambda c, d: eventos.append(d))
        novo = kobo.listar(self.target)[0]
        self.assertEqual(novo["kobo_uuid"], v["kobo_uuid"])
        self.assertEqual(novo["plano_hash"], v["plano_hash"])
        self.assertEqual(lab.listar(self.target)[0]["aegypt_larvas"], 3)
        self.assertEqual(json.loads(novo["tratamento_json"])["Quantidade_carga_gr"], 2)
        self.assertEqual(self.grupo()["aegypt_tb"], 1)
        self.assertEqual(len(eventos), 1)
        with self.assertRaisesRegex(kobo.LiraaKoboError, "alterada"):
            kobo.corrigir(self.target, v["id_visita"], {"versao": v["versao_dados"], "motivo": "Desatualizada"})
        with self.assertRaisesRegex(kobo.LiraaKoboError, "motivo"):
            kobo.corrigir(self.target, v["id_visita"], {})

    def test_corrigir_rejeita_fora_plano_e_rollback_auditoria(self):
        kobo.importar(self.target, self.ciclo, [self.env.registro()])
        v = kobo.listar(self.target)[0]
        p = {"versao": v["versao_dados"], "motivo": "Conferência"}
        with self.assertRaisesRegex(kobo.LiraaKoboError, "sorteado"):
            kobo.corrigir(self.target, v["id_visita"], {**p, "quarteirao": "9999"})
        def falhar(c, d):
            raise RuntimeError("Auditoria indisponível")
        with self.assertRaises(RuntimeError):
            kobo.corrigir(self.target, v["id_visita"], {**p, "tipo_imovel": "terreno_baldio"}, auditar=falhar)
        self.assertEqual(kobo.listar(self.target)[0]["versao_dados"], v["versao_dados"])

    def test_reimportacao_exige_liberacao_explicita_e_nao_recupera_leitura(self):
        r = self.env.registro()
        kobo.importar(self.target, self.ciclo, [r])
        t = lab.listar(self.target)[0]
        lab.salvar(self.target, t["id_tubito"], self.env.payload(), self.env.user)
        kobo.excluir(self.target, kobo.listar(self.target)[0]["id_visita"], "Teste")
        self.assertEqual(kobo.importar(self.target, self.ciclo, [r]), 0)
        self.assertEqual(len(kobo.exclusoes(self.target)), 1)
        with self.assertRaises(kobo.LiraaKoboError):
            kobo.permitir_reimportacao(self.target, r["_uuid"], "")
        def falhar(c, d):
            raise RuntimeError("Auditoria")
        with self.assertRaises(RuntimeError):
            kobo.permitir_reimportacao(self.target, r["_uuid"], "Conferido", auditar=falhar)
        self.assertEqual(len(kobo.exclusoes(self.target)), 1)
        kobo.permitir_reimportacao(self.target, r["_uuid"], "Conferido")
        self.assertEqual(kobo.importar(self.target, self.ciclo, [r]), 1)
        self.assertIsNone(lab.listar(self.target)[0]["leitura_id"])

    def test_periodos_incompativeis_recusados_antes_do_sorteio(self):
        with self.assertRaisesRegex(liraa.LiraaError, "ano"):
            liraa.criar_ciclo(self.target, {"ano": 2026, "nome": "Incompatível", "inicio": "2027-01-01"})
        with self.assertRaisesRegex(liraa.LiraaError, "ano"):
            liraa.atualizar_ciclo(self.target, self.ciclo, {"ano": 2026, "nome": "Incompatível", "fim": "2027-01-01"})

    def test_excluir_outro_estrato_e_adicionar_sorteio_nao_invalidam_visitas(self):
        cid = liraa.criar_ciclo(self.target, {"ano": 2026, "nome": "Dois estratos"})
        ids = []
        for num, qs in ((1, ["1:0001", "1:0002", "1:0003"]), (2, ["2:0004", "2:0005"])):
            e = liraa.salvar_estrato(self.target, cid, {"numero": num, "tipo": "normal", "imoveis_confirmados": 9000, "quarteiroes": qs}, base_dir=self.base)
            liraa.sortear(self.target, e, self.base, seed=42)
            ids.append(e)
        plano = op.plano(self.target, cid, self.base)
        q = plano["quarteiroes"][0]
        r = self.env.registro(endemias_ciclo=str(cid), endemias_plano=plano["plano_hash"])
        r["Dados_visita"].update(Localidade=q["localidade"], Quarteir_o=q["quarteirao"])
        kobo.importar(self.target, cid, [r])
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.excluir_estrato(self.target, ids[1])
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.salvar_estrato(self.target, cid, {"numero": 3, "tipo": "normal", "imoveis_confirmados": 9000, "quarteiroes": ["1:0001"]}, base_dir=self.base)
        self.assertEqual(op.plano(self.target, cid, self.base)["plano_hash"], plano["plano_hash"])
        self.assertEqual(kobo.listar(self.target, cid)[0]["situacao_vinculo"], "sorteado")

    def modelo_isolado(self):
        path = Path(self.base) / "aprovado.xlsx"
        shutil.copy2(modelo.APROVADO_XLSFORM, path)
        w = load_workbook(path)
        sheet = w["survey"]
        headers = {c.value: c.column for c in sheet[1]}
        for row in sheet.iter_rows(min_row=2):
            name = row[headers["name"] - 1].value
            if name == "endemias_ciclo":
                sheet.cell(row[0].row, headers["default"], str(self.ciclo))
            if name == "endemias_plano":
                sheet.cell(row[0].row, headers["default"], op.plano(self.target, self.ciclo, self.base)["plano_hash"])
        w.save(path)
        w.close()
        return path

    def test_aprovado_protege_plano_mesmo_apos_apagar_testes(self):
        arquivo = self.modelo_isolado()
        with patch.object(modelo, "APROVADO_XLSFORM", arquivo):
            kobo.importar(self.target, self.ciclo, [self.env.registro()])
            kobo.excluir(self.target, kobo.listar(self.target)[0]["id_visita"], "Teste")
            for operacao in (
                lambda: liraa.excluir_ciclo(self.target, self.ciclo),
                lambda: liraa.excluir_estrato(self.target, self.env.estrato),
                lambda: liraa.sortear(self.target, self.env.estrato, self.base, ressortear=True, id_sorteio_esperado=self.env.draw["id_sorteio"]),
                lambda: liraa.salvar_estrato(self.target, self.ciclo, {"numero": 2, "tipo": "normal", "imoveis_confirmados": 9000, "localidades": [1]}, base_dir=self.base)):
                with self.assertRaisesRegex(liraa.LiraaError, "aprovado"):
                    operacao()
            self.assertEqual(op.plano(self.target, self.ciclo, self.base)["plano_hash"], modelo.contrato()["plano_hash"])

    def test_acs_podem_mudar_depois_preservando_todo_formulario_e_plano(self):
        arquivo = self.modelo_isolado()
        before = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        def conteudo(w):
            return {s.title: [list(r) for r in s.values if any(v is not None for v in r)] for s in w}
        original = load_workbook(arquivo)
        valores = conteudo(original)
        original.close()
        with patch.object(modelo, "APROVADO_XLSFORM", arquivo):
            hash_plano = modelo.contrato()["plano_hash"]
            kobo.importar(self.target, self.ciclo, [self.env.registro()])
            for codigos in (["ACS-006"], [], ["ACS-006"]):
                op.salvar_configuracao(self.target, self.ciclo, codigos, "")
                gerado = load_workbook(BytesIO(xls.gerar(self.target, self.ciclo, self.base)))
                atual = conteudo(gerado)
                def registros(valores, excluir_campos=(), excluir_nomes=()):
                    return [{k: v for k, v in zip(valores[0], r) if v is not None and k not in excluir_campos}
                            for r in valores[1:] if dict(zip(valores[0], r)).get('name') not in excluir_nomes]
                self.assertEqual(registros(atual["survey"], excluir_nomes=('Logradouro', 'Logradouro_outro')),
                                 registros(valores["survey"], excluir_nomes=('Logradouro', 'Logradouro_outro')))
                self.assertEqual(registros(atual["settings"], excluir_campos=('version',)),
                                 registros(valores["settings"], excluir_campos=('version',)))
                lista = next(r for r in xls._rows(gerado["survey"]) if r["name"] == "ACS")["type"].split()[1]
                self.assertEqual([r for r in registros(atual['choices']) if r['list_name'] not in {lista, 'endemias_logradouros_rg'}],
                                 [r for r in registros(valores['choices']) if r['list_name'] != lista])
                self.assertEqual({r["name"] for r in xls._rows(gerado["choices"]) if r["list_name"] == lista}, set(codigos) | {"no-acs", "outros"})
                self.assertEqual(op.plano(self.target, self.ciclo, self.base)["plano_hash"], hash_plano)
                gerado.close()
            with patch.object(op, "plano_hash_conn", return_value="divergente"):
                with self.assertRaisesRegex(liraa.LiraaError, "diverge"):
                    xls.gerar(self.target, self.ciclo, self.base)
        self.assertEqual(hashlib.sha256(arquivo.read_bytes()).hexdigest(), before)

    def test_quarteirao_sem_visita_mantem_boletim_parcial(self):
        self.assertTrue(self.grupo()["parcial"])
        self.assertEqual(self.grupo()["quarteiroes_sem_visita"], self.grupo()["quarteiroes"])


    def test_edicao_e_sorteio_concorrentes_nao_misturam_parametros(self):
        cid = liraa.criar_ciclo(self.target, {"ano": 2026, "nome": "Concorrência"})
        payload = {"numero": 1, "tipo": "normal", "imoveis_confirmados": 9000, "localidades": [1]}
        eid = liraa.salvar_estrato(self.target, cid, payload, base_dir=self.base)
        consulta, terminou = threading.Event(), threading.Event()
        resultados = []
        real_connect = db.connect
        class Conexao:
            def __init__(self, conn): self.conn = conn
            def __getattr__(self, name): return getattr(self.conn, name)
            def __enter__(self): self.conn.__enter__(); return self
            def __exit__(self, *args): return self.conn.__exit__(*args)
            def execute(self, sql, args=()):
                cursor = self.conn.execute(sql, args)
                if sql == "SELECT 1 FROM liraa_sorteios WHERE id_estrato=?" and args == (eid,):
                    consulta.set()
                    if not terminou.wait(4): raise AssertionError("Ensaio concorrente não terminou")
                return cursor
        def connect(target):
            conn = real_connect(target)
            conn.execute("PRAGMA busy_timeout=20")
            return Conexao(conn)
        def sortear():
            try:
                if not consulta.wait(4): raise AssertionError("Edição não chegou ao ponto de concorrência")
                liraa.sortear(self.target, eid, self.base, seed=42)
                resultados.append("sorteou_durante_edicao")
            except sqlite3.OperationalError as exc:
                resultados.append("bloqueado" if db.is_concurrency_error(exc) else str(exc))
            finally:
                terminou.set()
        with patch.object(db, "connect", connect):
            thread = threading.Thread(target=sortear)
            thread.start()
            try:
                liraa.salvar_estrato(self.target, cid, {**payload, "tipo": "reduzido", "imoveis_confirmados": 4000}, id_estrato=eid, base_dir=self.base)
            finally:
                thread.join(5)
        self.assertEqual(resultados, ["bloqueado"])
        sorteio = liraa.sortear(self.target, eid, self.base, seed=42)
        self.assertEqual((sorteio["fracao"], sorteio["n"]), (.5, liraa._plano_amostral(4000, 3, "reduzido")["n"]))

    def test_rotas_de_correcao_e_reimportacao_restritas_a_admin(self):
        kobo.importar(self.target, self.ciclo, [self.env.registro()])
        conn = db.connect(self.target)
        conn.execute("CREATE TABLE usuarios(id_usuario INTEGER PRIMARY KEY,login TEXT,nome TEXT,nivel TEXT,ativo INTEGER)")
        conn.execute("INSERT INTO usuarios VALUES(1,'teste','Teste','admin',1)")
        conn.commit(); conn.close()
        app = Flask(__name__, template_folder=str(fixtures.fixtures.ROOT / "templates"))
        app.testing = True
        app.secret_key = "teste"
        app.config.update(DB_PATH=self.target, DB_BACKEND="sqlite", BASE_DIR=self.base)
        app.register_blueprint(auth_bp); app.register_blueprint(liraa_bp)
        app.jinja_env.globals.update(csrf_token=lambda: "teste")
        app.context_processor(lambda: {"TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {}, "sidebar_groups": [], "APP_VERSION_LABEL": "Teste"})
        client = app.test_client()
        with client.session_transaction() as sessao: sessao["uid"] = 1
        v = kobo.listar(self.target)[0]
        response = client.post(f"/liraa/visitas/{v['id_visita']}/corrigir", data={"versao": v["versao_dados"], "motivo": "Conferido", "tipo_imovel": "comercio"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(kobo.listar(self.target)[0]["tipo_imovel"], "comercio")
        self.assertIn("Corrigir dados de campo", client.get(f"/liraa?ciclo={self.ciclo}").get_data(as_text=True))
        kobo.excluir(self.target, v["id_visita"], "Teste")
        response = client.post("/liraa/visitas/permitir-reimportacao", data={"uuid": v["kobo_uuid"], "motivo": "Conferido", "confirmar_reimportacao": "sim"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(kobo.exclusoes(self.target), [])
        conn = db.connect(self.target)
        conn.execute("UPDATE usuarios SET nivel='visualizador'")
        conn.commit(); conn.close()
        self.assertEqual(client.post(f"/liraa/visitas/{v['id_visita']}/corrigir", data={}).status_code, 403)
        self.assertEqual(client.post("/liraa/visitas/permitir-reimportacao", data={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
