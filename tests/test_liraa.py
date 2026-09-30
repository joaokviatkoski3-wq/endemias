import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape
from flask import Flask

from app_core import liraa
from app_core import registro_geografico as rg_core
from blueprints.liraa import bp as liraa_bp
from blueprints.auth import bp as auth_bp


ROOT = Path(__file__).resolve().parents[1]


def camada(quarteiroes=("0001", "0002", "0003", "0004", "0005")):
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"Localidade": "Sede" if i < 3 else "Graziela", "id_Q": q},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-49.30 + i * .01, -25.30], [-49.295 + i * .01, -25.30],
             [-49.30 + i * .01, -25.305], [-49.30 + i * .01, -25.30]]]}}
        for i, q in enumerate(quarteiroes)
    ]}, ensure_ascii=False).encode("utf-8")


class LiraaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "liraa.db")
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        conn.executescript("""CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT NOT NULL);
            CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER);
            INSERT INTO localidades VALUES (1,'Sede');
            INSERT INTO localidades VALUES (2,'Graziela');""")
        rg_core.ensure_schema(conn)
        conn.commit()
        conn.close()
        self.importar(camada())

    def importar(self, arquivo):
        previa = rg_core.preview_importacao_geojson(self.db, arquivo, "quarteiroes.geojson", self.temp.name)
        rg_core.importar_geojson(self.db, arquivo, "quarteiroes.geojson", previa["sha256"], self.temp.name)

    def criar(self):
        return liraa.criar_ciclo(self.db, {"ano": 2026, "nome": "1º LIRAa", "inicio": "2026-10-01"})

    def estrato(self, ciclo, localidades=(1, 2), n=9000, tipo="normal"):
        return liraa.salvar_estrato(self.db, ciclo, {
            "numero": 1, "tipo": tipo, "imoveis_confirmados": n,
            "localidades": list(localidades)}, base_dir=self.temp.name)

    def test_inventario_deduplica_geometria_e_exclui_pe(self):
        conn = sqlite3.connect(self.db)
        q = conn.execute("""INSERT INTO registro_geografico_quarteiroes
            (id_localidade,localidade,quarteirao,criado_em,atualizado_em)
            VALUES (1,'Sede','0001','2026-09-30','2026-09-30')""").lastrowid
        for tipo, condo in (("R", 4), ("C", 0), ("PE", 0), ("REF", 0)):
            conn.execute("""INSERT INTO registro_geografico_imoveis
                (id_quarteirao,id_localidade,localidade,quarteirao,logradouro,numero,tipo,condominio,criado_em,atualizado_em)
                VALUES (?,1,'Sede','0001','Rua Teste','1',?,?,'2026-09-30','2026-09-30')""", (q, tipo, condo))
        conn.commit()
        conn.close()
        dados = liraa.inventario(self.db, self.temp.name)
        self.assertEqual(len(dados["quarteiroes"]), 5)
        sede = next(r for r in dados["localidades"] if r["nome"] == "Sede")
        self.assertEqual(sede["registros_rg_sem_pe"], 2)
        self.assertEqual(sede["unidades_rg_sem_pe"], 5)
        self.assertEqual(sede["pe_rg"], 1)

    def test_ciclo_estrato_sorteio_congela_snapshot(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        primeiro = liraa.sortear(self.db, estrato, self.temp.name, seed=123)
        self.assertEqual(primeiro["a"], 5)
        self.assertEqual(primeiro["q"], 2)
        self.assertEqual(primeiro["n"], 429)
        self.assertEqual(len({r["quarteirao"] for r in primeiro["selecionados"]}), 2)
        with self.assertRaisesRegex(liraa.LiraaError, "já foi sorteado"):
            liraa.sortear(self.db, estrato, self.temp.name, seed=123)
        with self.assertRaisesRegex(liraa.LiraaError, "congelado"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "localidades": [1, 2]}, estrato, self.temp.name)
        self.importar(camada(("0001", "0002", "0003", "0004", "0006")))
        salvo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["sorteio"]
        self.assertEqual(salvo["selecionados"], primeiro["selecionados"])
        self.assertEqual(salvo["q"], 2)

    def test_sem_localidade_repetida_ou_duplo_uso_no_ciclo(self):
        ciclo = self.criar()
        self.estrato(ciclo, (1,))
        with self.assertRaisesRegex(liraa.LiraaError, "repita"):
            self.estrato(ciclo, (2, 2))
        with self.assertRaisesRegex(liraa.LiraaError, "localidade já usado"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "localidades": [1]}, base_dir=self.temp.name)

    def test_ciclo_pode_ser_corrigido_antes_e_congelado_depois(self):
        vazio = self.criar()
        liraa.atualizar_ciclo(self.db, vazio, {"ano": 2026, "nome": "2º LIRAa"})
        liraa.excluir_ciclo_vazio(self.db, vazio)
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        with self.assertRaisesRegex(liraa.LiraaError, "Remova primeiro"):
            liraa.excluir_ciclo_vazio(self.db, ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=55)
        with self.assertRaisesRegex(liraa.LiraaError, "congelado"):
            liraa.atualizar_ciclo(self.db, ciclo, {"ano": 2026, "nome": "Alterado"})

    def test_faixa_de_imoveis_e_formula_do_manual(self):
        universo = [{"id_localidade": 1, "quarteirao": str(i)} for i in range(1, 351)]
        calculo = liraa._calcular_sorteio(9000, universo, "normal", 123)
        self.assertEqual((calculo["n"], calculo["a"], calculo["q"]), (429, 350, 84))
        self.assertEqual(len({r["ordem_universo"] for r in calculo["selecionados"]}), 84)
        self.assertEqual(calculo, liraa._calcular_sorteio(9000, universo, "normal", 123))
        with self.assertRaisesRegex(liraa.LiraaError, "8.100"):
            liraa._calcular_sorteio(4000, universo, "normal", 123)
        self.assertEqual(liraa._calcular_sorteio(4000, universo, "reduzido", 123)["fracao"], .5)

    def test_template_renderiza_planejamento_e_sem_exportacao_falsa(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=42)
        env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html"]))
        env.globals.update({"csrf_token": lambda: "teste", "url_for": lambda name, **kw: "/" + name,
                            "get_flashed_messages": lambda **kw: []})
        html = env.get_template("liraa.html").render(dados=liraa.painel(self.db, self.temp.name),
                                                       erro=None, editando=None, is_admin=True,
                                                       APP_VERSION_LABEL="Teste", TIPO_CORES={},
                                                       TIPO_LABELS={}, AGENDA_TIPO_LABELS={},
                                                       sidebar_groups=[], request=SimpleNamespace(endpoint="liraa.page"))
        self.assertIn("Pontos Estratégicos", html)
        self.assertIn("Novo ciclo", html)
        self.assertIn("Sorteio registrado", html)
        self.assertIn("Ver 2 quarteirões sorteados", html)
        self.assertIn("exportação", html)
        self.assertNotIn("Baixar .lira", html)

    def test_rota_exige_login_e_admin_para_gravar(self):
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE usuarios (
            id_usuario INTEGER PRIMARY KEY, usuario TEXT, nome TEXT, nivel TEXT, ativo INTEGER)""")
        conn.execute("INSERT INTO usuarios VALUES (1,'teste','Teste','visualizador',1)")
        conn.commit()
        conn.close()
        app = Flask(__name__, template_folder=str(ROOT / "templates"))
        app.secret_key = "teste-isolado"
        app.config.update(DB_PATH=self.db, DB_BACKEND="sqlite", BASE_DIR=self.temp.name)
        app.register_blueprint(auth_bp)
        app.register_blueprint(liraa_bp)
        app.jinja_env.globals.update(csrf_token=lambda: "teste")
        @app.context_processor
        def contexto():
            return {"TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {},
                    "sidebar_groups": [], "APP_VERSION_LABEL": "Teste"}
        with app.test_client() as client:
            self.assertEqual(client.get("/liraa").status_code, 302)
            with client.session_transaction() as session:
                session["uid"] = 1
            self.assertEqual(client.get("/liraa").status_code, 200)
            self.assertEqual(client.post("/liraa/ciclos", data={"ano": 2026, "nome": "1º"}).status_code, 403)
            conn = sqlite3.connect(self.db)
            conn.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=1")
            conn.commit()
            conn.close()
            response = client.post("/liraa/ciclos", data={"ano": 2026, "nome": "1º"}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("1º", response.get_data(as_text=True))
            ciclo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["id_ciclo"]
            response = client.post(f"/liraa/ciclos/{ciclo}/estratos", data={
                "numero": "1", "tipo": "normal", "imoveis_confirmados": "9000",
                "localidades": ["1", "2"]}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Estrato 1", response.get_data(as_text=True))
            estrato = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["id_estrato"]
            response = client.post(f"/liraa/estratos/{estrato}/sortear", follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Sorteio registrado", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
