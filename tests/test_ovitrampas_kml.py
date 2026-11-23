import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from flask import Flask

from app_core import contaovos_client, contaovos_registro, ovitrampas_kml
from blueprints import ovitrampas as rotas
from tests.test_contaovos_registro import _remote_row


class OvitrampasKmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "kml.db"
        with closing(sqlite3.connect(self.target)) as conn:
            conn.execute("""CREATE TABLE ovitrampas_armadilhas (
                ovitrampa_id TEXT PRIMARY KEY, localidade TEXT, bairro TEXT, quarteirao TEXT,
                rua TEXT, numero TEXT, complemento TEXT, localizacao TEXT, responsavel TEXT,
                telefone_responsavel TEXT, ativo INTEGER, latitude REAL, longitude REAL
            )""")
            conn.execute("""INSERT INTO ovitrampas_armadilhas VALUES
                ('97','Sede','Bairro','0001','Rua A & B','2','Casa','Fundos <portão>',
                 'Pessoa fictícia','9999',1,-1,-2)""")
            conn.execute("""INSERT INTO ovitrampas_armadilhas (ovitrampa_id,localidade)
                VALUES ('98','Roma')""")
            conn.commit()
        self.now = datetime(2026, 11, 23, 10, tzinfo=timezone.utc)

    def gerar(self, rows=None, filtros=None):
        rows = [_remote_row()] if rows is None else rows
        return ovitrampas_kml.gerar_kml(
            self.target, filtros, now=self.now,
            page_fetcher=lambda **kw: rows if kw["page"] == 1 else [],
        )

    def pontos(self, conteudo):
        return ET.fromstring(conteudo).findall(".//{*}Placemark")

    def test_titulo_e_coordenadas_remotas_com_detalhes_locais_seguros(self):
        with closing(sqlite3.connect(self.target)) as conn:
            antes = conn.execute("SELECT * FROM ovitrampas_armadilhas ORDER BY ovitrampa_id").fetchall()
        conteudo, resumo = self.gerar()
        ponto, = self.pontos(conteudo)
        self.assertEqual(ponto.find("{*}name").text, "97")
        self.assertEqual(ponto.find(".//{*}coordinates").text, "-49.29,-25.31,0")
        descricao = ponto.find("{*}description").text
        self.assertIn("Fundos &lt;portão&gt;", descricao)
        self.assertIn("Rua A &amp; B", descricao)
        self.assertIn("9999", descricao)
        self.assertIn("2026-11-23T10:00:00+00:00", descricao)
        campos = {r.attrib["name"]: r.find("{*}value").text for r in ponto.findall(".//{*}Data")}
        self.assertEqual(campos["Responsável"], "Pessoa fictícia")
        self.assertEqual(campos["Quarteirão"], "0001")
        self.assertEqual(resumo["apenas_locais"], 1)
        self.assertEqual(resumo["pontos"], 1)
        with closing(sqlite3.connect(self.target)) as conn:
            self.assertEqual(conn.execute("SELECT * FROM ovitrampas_armadilhas ORDER BY ovitrampa_id").fetchall(), antes)

    def test_filtros_sobre_cadastro_local_e_id_sem_limite_da_tabela(self):
        rows = [_remote_row(), _remote_row("98")]
        conteudo, _ = self.gerar(rows, {"distrito": "Roma", "busca": "98"})
        self.assertEqual([p.find("{*}name").text for p in self.pontos(conteudo)], ["98"])
        _, resumo = self.gerar([_remote_row(str(i)) for i in range(1, 502)])
        self.assertEqual(resumo["pontos"], 501)

    def test_sem_coordenada_nao_usa_latitude_local(self):
        for invalidos in (
            {"ovitrap_lat": None}, {"ovitrap_lat": "NaN"}, {"ovitrap_lng": "inf"},
            {"ovitrap_lat": 100}, {"ovitrap_lat": 0, "ovitrap_lng": 0},
            {"ovitrap_lat_lng_error": 1},
        ):
            with self.subTest(invalidos=invalidos):
                conteudo, resumo = self.gerar([_remote_row(**invalidos), _remote_row("99")])
                self.assertEqual(resumo["ignoradas"], 1)
                self.assertEqual([p.find("{*}name").text for p in self.pontos(conteudo)], ["99"])
                self.assertEqual(resumo["sem_cadastro_local"], 1)

    def test_nenhum_ponto_valido_ou_filtro_vazio_explica_sem_baixar(self):
        for rows, filtros in (([], None), ([_remote_row(ovitrap_lat=None)], None),
                              ([_remote_row()], {"distrito": "Inexistente"})):
            with self.subTest(rows=rows, filtros=filtros), self.assertRaisesRegex(ValueError, "Nenhuma ovitrampa"):
                self.gerar(rows, filtros)

    def test_recusa_municipio_estranho_e_cadastros_conflitantes(self):
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError):
            self.gerar([_remote_row(municipality_code="999")])
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError):
            self.gerar([_remote_row(), _remote_row(ovitrap_lat=-26)])
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError):
            self.gerar([_remote_row(), _remote_row("097")])

    def test_cada_exportacao_consulta_api_novamente_sem_espelho(self):
        with patch.object(contaovos_client, "public_ovitraps_page",
                          side_effect=[[_remote_row()], [], [_remote_row(ovitrap_lat=-25.5)], []]) as api:
            primeiro, _ = ovitrampas_kml.gerar_kml(self.target)
            segundo, _ = ovitrampas_kml.gerar_kml(self.target)
        self.assertIn(b"-49.29,-25.31,0", primeiro)
        self.assertIn(b"-49.29,-25.5,0", segundo)
        self.assertEqual([c.kwargs["page"] for c in api.call_args_list], [1, 2, 1, 2])
        self.assertTrue(all(c.kwargs["max_attempts"] == 1 for c in api.call_args_list))

    def test_interrupcao_da_api_nao_retorna_mapa_incompleto(self):
        def fetcher(**kw):
            if kw["page"] == 1:
                return [_remote_row()]
            raise contaovos_client.ContaOvosError("indisponível")
        with self.assertRaises(contaovos_client.ContaOvosError):
            ovitrampas_kml.gerar_kml(self.target, page_fetcher=fetcher)

    def test_limites_do_my_maps(self):
        with patch.object(ovitrampas_kml, "LIMITE_PONTOS", 1):
            with self.assertRaisesRegex(ValueError, "2.000"):
                self.gerar([_remote_row(), _remote_row("99")])
        with patch.object(ovitrampas_kml, "LIMITE_BYTES", 50):
            with self.assertRaisesRegex(ValueError, "5 MB"):
                self.gerar()

    def test_rota_entrega_kml_com_auditoria_e_recusa_erros_remotos(self):
        app = Flask(__name__)
        app.secret_key = "somente-teste"
        app.config.update(TESTING=True, DB_PATH=self.target)
        app.register_blueprint(rotas.bp)
        app.add_url_rule("/login", endpoint="auth.login", view_func=lambda: "Login")
        client = app.test_client()
        self.assertEqual(client.post("/api/ovitrampas/armadilhas/exportar.kml").status_code, 302)
        with client.session_transaction() as sess:
            sess["uid"] = 1
        conteudo, resumo = self.gerar()
        with patch.object(rotas.auth_core, "usuario_atual", return_value={"id_usuario": 1}), \
                patch.object(rotas.ovitrampas_kml, "gerar_kml", return_value=(conteudo, resumo)) as gerar, \
                patch.object(rotas.audit, "registrar_evento") as auditar:
            response = client.post("/api/ovitrampas/armadilhas/exportar.kml?distrito=Sede&busca=97")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/vnd.google-earth.kml+xml")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
            self.assertEqual(response.headers["X-Ovitrampas-Pontos"], "1")
            self.assertIn(".kml", response.headers["Content-Disposition"])
            self.assertEqual(gerar.call_args.args[1], {"distrito": "Sede", "busca": "97"})
            self.assertNotIn("Pessoa fictícia", str(auditar.call_args))
            for erro, status in ((contaovos_client.ContaOvosError("falha"), 502),
                                 (ValueError("Nenhuma ovitrampa"), 422)):
                gerar.side_effect = erro
                self.assertEqual(client.post("/api/ovitrampas/armadilhas/exportar.kml").status_code, status)


if __name__ == "__main__":
    unittest.main()
