"""Histórico detalhado por agente em vetores e esporotricose."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import fitz
from flask import Flask

from criar_banco import SQL
from app_core import esporotricose
from app_core import relatorio_visitas_completo as historico
from app_core import relatorio_visitas_pdf
from blueprints.auth import bp as auth_bp
from blueprints.relatorio_agente import bp as relatorio_bp


class HistoricoVisitasPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "relatorio.db")
        conn = sqlite3.connect(self.db)
        conn.executescript(SQL)
        esporotricose.ensure_schema(conn)
        conn.execute("INSERT INTO localidades (id_localidade,nome) VALUES (1,'São Venâncio')")
        conn.execute("INSERT INTO agentes (id_agente,nome,nome_completo) VALUES (1,'João','João Silva')")
        conn.execute("INSERT INTO agentes (id_agente,nome,nome_completo) VALUES (2,'Ana','Ana Lima')")
        conn.execute("INSERT INTO agentes (id_agente,nome,nome_completo,ativo) VALUES (3,'Pedro','Pedro Antigo',0)")
        conn.execute("INSERT INTO acs_catalogo VALUES ('ACS-006','Maria ACS','2026-10-02')")
        conn.execute("""INSERT INTO visitas (id_visita,kobo_uuid,tipo,data,hora_inicio,localidade,
            id_localidade,logradouro,numero,morador,visita,observacoes,processado_em)
            VALUES ('vet-1','uuid-vet-1','PVE','2026-09-14','10:45','São Venâncio',1,
                'Rua dos Salgueiros','51','José da Silva','Normal','Observação completa','2026-09-15')""")
        conn.executemany("INSERT INTO visita_agentes VALUES ('vet-1',?)", [(1,), (2,)])
        conn.execute("INSERT INTO visita_acs VALUES ('vet-1','ACS-006')")
        conn.execute("""UPDATE visitas SET kobo_id=777777,
            submission_time='2099-01-01T11:22:33', processado_em='2099-12-31'
            WHERE id_visita='vet-1'""")
        conn.execute("""INSERT INTO depositos_inspecionados
            (id_visita,tipo_deposito,inspecionado,eliminado,tratado) VALUES ('vet-1','A1',3,1,0)""")
        conn.execute("INSERT INTO tratamentos (id_visita,tipo,quantidade_carga) VALUES ('vet-1','Larvicida',2)")
        conn.execute("INSERT INTO coletas (id_coleta,id_visita,num_tubo) VALUES ('col-1','vet-1','666')")
        conn.execute("""INSERT INTO resultados_laboratorio (id_coleta,num_tubo,data_coleta,
            laboratorista,aegypt_larvas) VALUES ('col-1','666','2026-09-14','Ana',7)""")
        conn.execute("""INSERT INTO focos_positivos (id_foco,id_visita,id_coleta,codigo,
            status_notificacao) VALUES ('foco-1','vet-1','col-1','FOCO-666','pendente')""")
        conn.execute("""INSERT INTO esporotricose_visitas (id_visita,kobo_uuid,data,hora_inicio,
            localidade,logradouro,numero,morador,telefone,visita,observacoes,processado_em)
            VALUES ('esp-1','uuid-esp-1','2026-09-15','08:30','São Venâncio',
                'Rua do Gato','20','Maria','41999999999','Normal','Acompanhamento','2026-09-16')""")
        conn.execute("INSERT INTO esporotricose_visita_agentes VALUES ('esp-1',1)")
        conn.execute("INSERT INTO esporotricose_visita_acs VALUES ('esp-1','ACS-006')")
        conn.execute("""UPDATE esporotricose_visitas SET kobo_id=888888,
            submission_time='2099-02-02T11:22:33', processado_em='2099-12-30'
            WHERE id_visita='esp-1'""")
        conn.execute("""INSERT INTO esporotricose_animais
            (id_animal,id_visita,nome,especie,feridas,processado_em)
            VALUES ('animal-1','esp-1','Mingau','Gato','Sim','2026-09-16')""")
        conn.execute("""INSERT INTO visitas (id_visita,kobo_uuid,tipo,data,processado_em)
            VALUES ('fora','uuid-fora','TB','2026-08-01','2026-08-02')""")
        conn.execute("INSERT INTO visita_agentes VALUES ('fora',1)")
        conn.execute("""INSERT INTO usuarios (id_usuario,usuario,nome,senha_hash,nivel,ativo,criado_em)
            VALUES (1,'teste','Teste','hash','admin',1,'2026-10-02')""")
        conn.commit()
        conn.close()

    def test_coleta_todas_as_fontes_uma_vez_por_visita_e_detalhes(self):
        dados = historico.coletar(self.db, "João", "2026-09-14", "2026-09-15")
        self.assertEqual(dados["totais"], {"vetores": 1, "esporotricose": 1})
        self.assertEqual([v["origem"] for v in dados["visitas"]], ["Vetores", "Esporotricose"])
        vetor, esporo = dados["visitas"]
        self.assertEqual(vetor["visita"]["acs"], "Maria ACS")
        self.assertIn("Ana", vetor["visita"]["agentes"])
        secoes = {s["titulo"]: s["registros"] for s in vetor["secoes"]}
        self.assertEqual(secoes["Resultados laboratoriais"][0]["aegypt_larvas"], 7)
        self.assertEqual(secoes["Coletas"][0]["num_tubo"], "666")
        self.assertEqual(secoes["Focos positivos e notificações"][0]["codigo"], "FOCO-666")
        self.assertEqual(esporo["visita"]["acs"], "Maria ACS")
        self.assertEqual(esporo["secoes"][0]["registros"][0]["nome"], "Mingau")

    def test_pdf_compacto_com_dados_de_campo_sem_ids_tecnicos(self):
        dados = historico.coletar(self.db, "João", "2026-09-14", "2026-09-15")
        self.assertTrue(all(len(relatorio_visitas_pdf._linhas_visita(item, i)) <= 5
                            for i, item in enumerate(dados["visitas"], 1)))
        self.assertIn("3 insp.", str(relatorio_visitas_pdf._linhas_visita(dados["visitas"][0], 1)))
        conteudo = relatorio_visitas_pdf.gerar(dados)
        self.assertTrue(conteudo.startswith(b"%PDF-"))
        with fitz.open(stream=conteudo, filetype="pdf") as pdf:
            texto = "\n".join(pagina.get_text() for pagina in pdf)
            self.assertGreater(pdf[0].rect.width, pdf[0].rect.height)
        for esperado in ("João Silva", "Rua dos Salgueiros", "José da Silva", "666",
                         "3 insp.", "Ae. aegypti 7 larvas", "Focos positivos: 1",
                         "Mingau", "Maria ACS", "Esporotricose"):
            self.assertIn(esperado, texto)
        for proibido in ("uuid-vet-1", "uuid-esp-1", "FOCO-666", "777777", "888888",
                         "2099-01-01", "2099-02-02", "2099-12-31", "2099-12-30",
                         "processado em", "id localidade", "Kobo ID", "Identificador da visita"):
            self.assertNotIn(proibido, texto)

    def test_texto_longo_e_multiplas_paginas_mantem_cinco_linhas(self):
        dados = historico.coletar(self.db, "João", "2026-09-14", "2026-09-15")
        dados["visitas"][0]["visita"]["observacoes"] = "Observação longa " * 100
        dados["visitas"] = dados["visitas"] * 25
        for numero, item in enumerate(dados["visitas"], 1):
            self.assertLessEqual(len(relatorio_visitas_pdf._linhas_visita(item, numero)), 5)
        with fitz.open(stream=relatorio_visitas_pdf.gerar(dados), filetype="pdf") as pdf:
            self.assertGreater(len(pdf), 1)
            texto = "\n".join(pagina.get_text() for pagina in pdf)
            self.assertIn("Observações: Observação longa", texto)
            self.assertIn("...", texto)
            self.assertNotIn("Observação longa " * 100, texto)

    def test_rota_autenticada_valida_datas_e_entrega_pdf(self):
        app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
        app.secret_key = "teste-isolado"
        app.config.update(DB_PATH=self.db, DB_BACKEND="sqlite", BASE_DIR=self.temp.name)
        app.register_blueprint(auth_bp)
        app.register_blueprint(relatorio_bp)
        app.jinja_env.globals.update(csrf_token=lambda: "teste")
        @app.context_processor
        def contexto():
            return {"TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {},
                    "sidebar_groups": [], "APP_VERSION_LABEL": "Teste"}
        with app.test_client() as client:
            self.assertEqual(client.get("/relatorio-agente/visitas/pdf").status_code, 302)
            with client.session_transaction() as sessao:
                sessao["uid"] = 1
            pagina = client.get("/relatorio-agente?d_ini=2026-09-14&d_fim=2026-09-15")
            self.assertEqual(pagina.status_code, 200)
            self.assertIn("Histórico das visitas - PDF compacto", pagina.get_data(as_text=True))
            self.assertIn("Pedro Antigo (inativo)", pagina.get_data(as_text=True))
            url = "/relatorio-agente/visitas/pdf?agente=Jo%C3%A3o&d_ini=2026-09-14&d_fim=2026-09-15"
            resposta = client.get(url)
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.mimetype, "application/pdf")
            self.assertIn("attachment", resposta.headers["Content-Disposition"])
            self.assertIn("historico-visitas-joao-", resposta.headers["Content-Disposition"])
            self.assertIn("no-store", resposta.headers["Cache-Control"])
            self.assertTrue(resposta.data.startswith(b"%PDF-"))
            self.assertEqual(client.get(url.replace("d_fim=2026-09-15", "d_fim=2026-09-01")).status_code, 400)
            self.assertEqual(client.get(url.replace("agente=Jo%C3%A3o", "agente=Inexistente")).status_code, 400)

    def test_sem_visitas_gera_pdf_com_aviso(self):
        dados = historico.coletar(self.db, "Ana", "2026-09-15", "2026-09-15")
        self.assertEqual(dados["visitas"], [])
        with fitz.open(stream=relatorio_visitas_pdf.gerar(dados), filetype="pdf") as pdf:
            self.assertIn("Nenhuma visita encontrada", pdf[0].get_text())


if __name__ == "__main__":
    unittest.main()
