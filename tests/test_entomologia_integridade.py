import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from flask import Flask

import criar_banco
from app_core import bri, db, ovitrampas, ovitrampas_laboratorio, pontos_estrategicos, sispncd
from app_core.territorio import chave_territorial, quarteirao_canonico
from blueprints import mapa


def preparar_banco(path):
    conn = db.connect(path)
    conn.executescript(criar_banco.SQL)
    bri.ensure_schema(conn)
    pontos_estrategicos.ensure_schema(conn)
    ovitrampas.ensure_schema(conn)
    conn.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES(1,'leitor','Pessoa ficticia','hash-ficticio','admin','2026-01-01')")
    conn.execute("INSERT INTO localidades(id_localidade,nome) VALUES(1,'Localidade A'),(2,'Localidade B')")
    conn.commit()
    conn.close()
    ovitrampas_laboratorio.ensure_schema(path)


def inserir_lote(conn, armadilhas, data="2026-08-20", status="pendente", ovos=0):
    agora = data + "T10:00:00"
    diario = conn.execute(
        "INSERT INTO ovitrampas_diarios(nome,criado_em,atualizado_em) VALUES(?,?,?)",
        ("Diario " + str(conn.execute("SELECT COUNT(*) FROM ovitrampas_diarios").fetchone()[0]), agora, agora),
    ).lastrowid
    conn.execute(
        "INSERT INTO ovitrampas_calendario_eventos(data,movimento,criado_em) VALUES(?,'troca',?) ON CONFLICT(data) DO NOTHING",
        (data, agora),
    )
    evento = conn.execute("SELECT id_evento FROM ovitrampas_calendario_eventos WHERE data=?", (data,)).fetchone()[0]
    lote = conn.execute(
        """INSERT INTO ovitrampas_laboratorio_lotes
           (id_evento,id_diario,diario_nome,data_movimento,movimento,status,criado_em,atualizado_em)
           VALUES(?,?,'Diario ficticio',?,'troca',?,?,?)""",
        (evento, diario, data, status, agora, agora),
    ).lastrowid
    itens = []
    for armadilha in armadilhas:
        itens.append(conn.execute(
            "INSERT INTO ovitrampas_laboratorio_itens(id_lote,ovitrampa_id,ovos) VALUES(?,?,?)",
            (lote, armadilha, ovos),
        ).lastrowid)
    return lote, itens


def inserir_api(conn, armadilha="1", data="2026-08-20", ovos=12, identificador="api-1"):
    dia = date.fromisoformat(data)
    conn.execute(
        """INSERT INTO ovitrampas_ocorrencias_conta_ovos
           (id_contagem,ovitrampa_id,ano,semana,data,ovos,importado_em) VALUES(?,?,?,?,?,?,?)""",
        (identificador, armadilha, dia.year, ovitrampas._semana_epi(dia), data, ovos, data),
    )


def inserir_legado(conn, armadilha="1", data="2026-08-20", ovos=2):
    dia = date.fromisoformat(data)
    conn.execute(
        """INSERT INTO ovitrampas_leituras
           (id_leitura,ovitrampa_id,ano,semana,data_coleta,ovos,importado_em) VALUES(?,?,?,?,?,?,?)""",
        (f"legado-{armadilha}-{data}", armadilha, dia.year, ovitrampas._semana_epi(dia), data, ovos, data),
    )


def executar_mapa(path, query="", pontos=False):
    app = Flask(__name__)
    app.config.update(SETORES_ENABLED=True, SETOR="endemias")
    view = mapa.api_mapa_ovitrampas if pontos else mapa.api_mapa
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    with app.test_request_context("/api/mapa" + query), mock.patch.object(mapa.bh, "get_db", side_effect=lambda: db.connect(path)):
        response = view()
    if isinstance(response, tuple):
        raise AssertionError(response[0].get_json())
    return response.get_json()


class BancoEntomologiaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ficticio.db"
        preparar_banco(self.path)


class CompletudeLaboratorioTests(BancoEntomologiaTests):
    def setUp(self):
        super().setUp()
        conn = db.connect(self.path)
        self.lote, self.itens = inserir_lote(conn, ["1", "2"])
        conn.commit()
        conn.close()
        self.usuario = {"id_usuario": 1, "nome": "Pessoa ficticia"}

    def test_conclusao_rejeita_ausencia_parcial_duplicado_e_ovos_omitidos(self):
        a, b = self.itens
        for payload in ([], [{"id_item": a, "ovos": 3}],
                        [{"id_item": a, "ovos": 3}, {"id_item": a, "ovos": 0}],
                        [{"id_item": a, "ovos": 3}, {"id_item": b}],
                        [{"id_item": a, "ovos": 3}, {"id_item": b, "ovos": None}],
                        [{"id_item": a, "ovos": 3}, {"id_item": b, "ovos": 1.5}],
                        [{"id_item": a, "ovos": 3}, "invalido"]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                ovitrampas_laboratorio.concluir_lote(self.path, self.lote, payload, self.usuario)
            lote = ovitrampas_laboratorio.obter_lote(self.path, self.lote)
            self.assertEqual("pendente", lote["status"])
            self.assertEqual(0, lote["ovos"])
            self.assertIsNone(lote["concluido_em"])

    def test_rascunho_parcial_preservado_mas_conclusao_exige_todos_zeros_explicitos(self):
        a, b = self.itens
        rascunho = ovitrampas_laboratorio.salvar_rascunho(self.path, self.lote, [{"id_item": a, "ovos": 4}], self.usuario)
        self.assertEqual("em_preenchimento", rascunho["status"])
        self.assertEqual([True, False], [item["leitura_informada"] for item in rascunho["itens"]])
        with self.assertRaises(ValueError):
            ovitrampas_laboratorio.concluir_lote(self.path, self.lote, [], self.usuario)
        lote = ovitrampas_laboratorio.concluir_lote(self.path, self.lote, [{"id_item": a, "ovos": 4}, {"id_item": b, "ovos": 0}], self.usuario)
        self.assertEqual("concluido", lote["status"])
        self.assertEqual([4, 0], [item["ovos"] for item in lote["itens"]])
        self.assertTrue(all(item["leitura_informada"] for item in lote["itens"]))

    def test_lote_sem_armadilhas_nao_pode_ser_concluido(self):
        conn = db.connect(self.path)
        lote, _ = inserir_lote(conn, [])
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ValueError, "todas as armadilhas"):
            ovitrampas_laboratorio.concluir_lote(self.path, lote, [], self.usuario)

    def test_ocorrencia_sem_contagem_e_zero_explicito_permanecem_distintos(self):
        a, b = self.itens
        seca = {"id_item": a, "ovos": None, "ocorrencia": 5}
        fechada = {"id_item": b, "ovos": None, "ocorrencia": 6}
        rascunho = ovitrampas_laboratorio.salvar_rascunho(
            self.path, self.lote, [seca, fechada], self.usuario,
        )
        self.assertEqual([5, 6], [item["ocorrencia"] for item in rascunho["itens"]])
        self.assertFalse(any(item["ovos_informados"] for item in rascunho["itens"]))
        with self.assertRaisesRegex(ValueError, "armadilha 2"):
            ovitrampas_laboratorio.concluir_lote(
                self.path, self.lote, [seca, dict(fechada, ocorrencia=None)], self.usuario,
            )
        lote = ovitrampas_laboratorio.concluir_lote(
            self.path, self.lote, [dict(seca, ovos=0), fechada], self.usuario,
        )
        self.assertEqual(lote["status"], "concluido")
        self.assertEqual([True, False], [item["ovos_informados"] for item in lote["itens"]])
        with self.assertRaisesRegex(ValueError, "armadilha 2"):
            ovitrampas_laboratorio.salvar_rascunho(
                self.path, self.lote, [dict(fechada, ocorrencia=None)], self.usuario,
            )


class AutoridadeLeiturasMapaTests(BancoEntomologiaTests):
    def leituras(self):
        conn = db.connect(self.path)
        try:
            return [dict(row) for row in conn.execute(ovitrampas.leituras_mapa_cte(conn) + "SELECT * FROM ovi_leituras ORDER BY data_coleta,id_leitura")]
        finally:
            conn.close()

    def test_api_prevalece_sobre_laboratorio_e_legado_sem_triplicar(self):
        conn = db.connect(self.path)
        inserir_api(conn)
        inserir_legado(conn)
        inserir_lote(conn, ["1"], status="concluido", ovos=10)
        conn.commit()
        conn.close()
        self.assertEqual([("api:api-1", 12)], [(r["id_leitura"], r["ovos"]) for r in self.leituras()])

    def test_laboratorio_concluido_sem_api_entra_e_rascunho_fica_fora(self):
        conn = db.connect(self.path)
        inserir_lote(conn, ["1"], status="concluido", ovos=4)
        inserir_lote(conn, ["2"], status="em_preenchimento", ovos=8)
        inserir_legado(conn, ovos=1)
        inserir_legado(conn, armadilha="3", ovos=2)
        conn.commit()
        conn.close()
        self.assertEqual({("1", 4), ("3", 2)}, {(r["ovitrampa_id"], r["ovos"]) for r in self.leituras()})

    def test_laboratorio_em_outro_dia_e_historico_de_outra_semana_preservados(self):
        conn = db.connect(self.path)
        inserir_api(conn)
        inserir_lote(conn, ["1"], data="2026-08-21", status="concluido", ovos=4)
        inserir_legado(conn, data="2026-08-10", ovos=2)
        inserir_legado(conn, data="2026-08-19", ovos=9)
        conn.commit()
        conn.close()
        rows = self.leituras()
        self.assertEqual(4, len(rows))
        self.assertEqual(27, sum(r["ovos"] for r in rows))

    def test_lotes_mesmo_dia_usam_uma_unica_versao_enviada(self):
        conn = db.connect(self.path)
        inserir_lote(conn, ["1"], status="enviado_conta_ovos", ovos=4)
        inserir_lote(conn, ["1"], status="concluido", ovos=8)
        conn.commit()
        conn.close()
        self.assertEqual([4], [r["ovos"] for r in self.leituras()])

    def test_api_sem_data_de_coleta_usa_precedencia_semanal(self):
        conn = db.connect(self.path)
        inserir_api(conn)
        conn.execute("UPDATE ovitrampas_ocorrencias_conta_ovos SET data=NULL,data_envio_contagem='2026-08-21T09:00:00'")
        inserir_lote(conn, ["1"], status="concluido", ovos=4)
        inserir_legado(conn)
        conn.commit()
        conn.close()
        self.assertEqual([12], [r["ovos"] for r in self.leituras()])

    def test_data_de_envio_nao_suprime_coleta_conhecida_de_outra_semana(self):
        conn = db.connect(self.path)
        inserir_api(conn)
        inserir_api(conn, armadilha="2", identificador="api-2")
        conn.execute("UPDATE ovitrampas_ocorrencias_conta_ovos SET data=NULL,data_envio_contagem='2026-09-10T09:00:00'")
        inserir_lote(conn, ["1"], data="2026-09-10", status="concluido", ovos=4)
        inserir_legado(conn, armadilha="2", data="2026-09-10", ovos=5)
        conn.commit()
        conn.close()
        self.assertEqual({("1", 12), ("1", 4), ("2", 12), ("2", 5)},
                         {(r["ovitrampa_id"], r["ovos"]) for r in self.leituras()})

    def test_semana_do_laboratorio_no_inicio_do_ano_nao_duplica_legado(self):
        conn = db.connect(self.path)
        inserir_lote(conn, ["1"], data="2026-01-01", status="concluido", ovos=4)
        conn.execute("INSERT INTO ovitrampas_leituras(id_leitura,ovitrampa_id,ano,semana,ovos,importado_em) VALUES('legado-sem-data','1',2025,52,7,'2026-01-02')")
        conn.commit()
        conn.close()
        self.assertEqual([(2025, 52, 4)], [(r["ano"], r["semana"], r["ovos"]) for r in self.leituras()])

    def test_funciona_sem_tabelas_de_laboratorio(self):
        conn = db.connect(self.path)
        conn.execute("DROP TABLE ovitrampas_laboratorio_itens")
        conn.execute("DROP TABLE ovitrampas_laboratorio_lotes")
        inserir_legado(conn)
        conn.commit()
        conn.close()
        self.assertEqual([2], [r["ovos"] for r in self.leituras()])


class TerritorioMapaSisPNCDTests(BancoEntomologiaTests):
    def adicionar_visita(self, conn, identificador, localidade=1, quarteirao="1", tipo="TB", id_pe=None):
        conn.execute("INSERT INTO visitas(id_visita,kobo_uuid,data,id_localidade,quarteirao,tipo,visita,tipo_imovel,processado_em,id_pe) VALUES(?,?,'2026-08-20',?,?,?,'normal','R','2026-08-20',?)", (identificador, identificador, localidade, quarteirao, tipo, id_pe))

    def test_chave_preserva_fracoes_e_identificadores_alfanumericos(self):
        self.assertEqual("1:1", chave_territorial(1, "0001"))
        self.assertEqual("1:1", chave_territorial(1, 1.0))
        self.assertEqual("1:1.1", chave_territorial(1, "0001.1"))
        self.assertNotEqual(chave_territorial(1, "1.1"), chave_territorial(1, "1.2"))
        self.assertEqual("A-1", quarteirao_canonico(" A-1 "))
        self.assertIsNone(chave_territorial(None, 1))
        self.assertIsNone(chave_territorial(1, " "))

    def test_mapa_reune_api_visitas_e_quarteirao_fracionado(self):
        conn = db.connect(self.path)
        self.adicionar_visita(conn, "visita-1")
        self.adicionar_visita(conn, "visita-2", quarteirao="1.1")
        conn.execute("INSERT INTO ovitrampas_armadilhas(ovitrampa_id,localidade,quarteirao,latitude,longitude,atualizado_em) VALUES('1','Localidade A','0001',-25,-49,'2026-08-20')")
        inserir_api(conn)
        inserir_legado(conn, data="2026-08-19")
        conn.execute("UPDATE ovitrampas_leituras SET data_coleta=NULL,data_leitura='2026-08-19'")
        inserir_lote(conn, ["1"], status="concluido", ovos=10)
        conn.commit()
        conn.close()
        dados = executar_mapa(self.path)
        self.assertEqual(1, dados["1:1"]["total"])
        self.assertEqual(12, dados["1:1"]["ovi_ovos"])
        self.assertEqual(1, dados["1:1"]["ovi_leituras"])
        self.assertEqual(1, dados["1:1.1"]["total"])
        self.assertNotIn("1:0001", dados)
        pontos = executar_mapa(self.path, "?d_ini=2026-08-20&d_fim=2026-08-20&min_ovos=12&positivas=1", pontos=True)
        self.assertEqual(12, pontos["resumo"]["ovos"])
        self.assertEqual(1, pontos["resumo"]["leituras"])
        vazio = executar_mapa(self.path, "?d_ini=2026-08-19&d_fim=2026-08-19&min_ovos=1", pontos=True)
        self.assertEqual([], vazio["pontos"])

    def test_mapa_pe_nao_empresta_visita_com_id_a_outro_pe(self):
        conn = db.connect(self.path)
        for ident in (1, 2):
            conn.execute("INSERT INTO pontos_estrategicos(id_pe,codigo_pe,nome,id_localidade,localidade,quarteirao,situacao,criado_em,atualizado_em) VALUES(?,?,?,1,'Localidade A',1,1,'2026-08-20','2026-08-20')", (ident, f"PE-{ident}", f"PE ficticio {ident}"))
        self.adicionar_visita(conn, "pe-vinculado", tipo="PE", id_pe=1)
        conn.execute("UPDATE visitas SET data=? WHERE id_visita='pe-vinculado'", (date.today().isoformat(),))
        conn.commit()
        conn.close()
        dados = executar_mapa(self.path)
        self.assertEqual(2, dados["1:1"]["pes_ativos"])
        self.assertEqual(1, dados["1:1"]["pes_atrasados"])
        conn = db.connect(self.path)
        self.adicionar_visita(conn, "pe-legado", tipo="PE")
        conn.execute("UPDATE visitas SET data=? WHERE id_visita='pe-legado'", (date.today().isoformat(),))
        conn.commit()
        conn.close()
        self.assertEqual(0, executar_mapa(self.path)["1:1"]["pes_atrasados"])

    def test_sispncd_conta_localidades_distintas_e_ignora_territorio_desconhecido(self):
        conn = db.connect(self.path)
        self.adicionar_visita(conn, "a", localidade=1)
        self.adicionar_visita(conn, "b", localidade=2)
        self.adicionar_visita(conn, "c", localidade=1, quarteirao="0001")
        self.adicionar_visita(conn, "d", localidade=1, quarteirao="1.1")
        self.adicionar_visita(conn, "e", localidade=None)
        self.adicionar_visita(conn, "f", quarteirao=None)
        conn.commit()
        conn.close()
        ano, semana = sispncd.epidemiological_week_for_date("2026-08-20")
        resultado = sispncd.sispncd(self.path, ano, semana, ["TB/TBO"])
        self.assertEqual(3, resultado["dados_gerais"]["total_quarteiroes"])
        filtrado = sispncd.sispncd(self.path, ano, semana, ["TB/TBO"], id_localidade=2)
        self.assertEqual(1, filtrado["dados_gerais"]["total_quarteiroes"])
