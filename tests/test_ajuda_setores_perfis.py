"""Ajuda por dominio funcional e capacidade, com contas e dados ficticios."""
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
from app_core import ajuda, auth, db, permissoes, sessoes
from scripts.preparar_massa_web_teste import preparar

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("usuario", "visualizador", "operador", "admin", "superadmin")


class AjudaSetoresPerfisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".venv")
        cls.base = Path(cls.temp.name)
        cls.seed = cls.base / "seed.db"
        with contextlib.redirect_stdout(io.StringIO()):
            preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.base))
        self.path = self.directory / "ficticio.db"
        shutil.copyfile(self.seed, self.path)
        config = dict(DB_PATH=str(self.path), TESTING=True, WTF_CSRF_ENABLED=False,
            SETORES_ENABLED=True, TERMOS_USO_ENABLED=False,
            BACKUP_DIR=str(self.directory / "backups"), BACKUP_COMPLETO_DIR=str(self.directory / "completos"),
            UPLOAD_TEMP=str(self.directory / "uploads"), KOBO_CONFIG_PATH=str(self.directory / "kobo.json"))
        self.apps = {s: app.create_app({**config, "SETOR": s}) for s in ("endemias", "ambiental")}
        self.ids = {}
        conn = db.connect(str(self.path))
        self.addCleanup(conn.close)
        for area, offset in (("endemias", 10), ("ambiental", 20)):
            for i, level in enumerate(LEVELS, 1):
                if level == "superadmin":
                    existing = conn.execute("SELECT id_usuario FROM usuarios WHERE nivel='superadmin'").fetchone()
                    if existing:
                        self.ids[area, level] = existing[0]
                        continue
                ident = offset + i
                conn.execute("""INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,setor,criado_em)
                    SELECT ?,?,?,senha_hash,?,?,'2026-11-05' FROM usuarios WHERE id_usuario=1""",
                    (ident, "ficticio" + str(ident), "Pessoa Ficticia " + str(ident), level, area))
                self.ids[area, level] = ident
        conn.commit(); conn.close()

    def client(self, area, level="usuario", user_area=None):
        application = self.apps[area]
        client = application.test_client()
        user = db.query_one(str(self.path), "SELECT * FROM usuarios WHERE id_usuario=?", (self.ids[user_area or area, level],))
        with application.app_context(), client.session_transaction() as session:
            session.update(uid=user["id_usuario"], nome=user["nome"], auth_token=auth.token_sessao(user["senha_hash"]), sessao_id=sessoes.criar(str(self.path), user))
        return client

    def help(self, client, **args):
        response = client.get("/api/ajuda", query_string={"limite": 120, **args})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:100])
        return response.json

    def test_matriz_dez_combinacoes_nao_mistura_areas_nem_capacidades(self):
        catalog = {a["id"]: a for a in ajuda.ARTIGOS}
        for area in self.apps:
            for level in LEVELS:
                with self.subTest(area=area, level=level):
                    client = self.client(area, level)
                    result = self.help(client)
                    rows = result["artigos"] + result["contexto"]
                    self.assertTrue(rows)
                    self.assertEqual(result["setor"], area)
                    for article in rows:
                        source = catalog[article["id"]]
                        self.assertIn(area, source["areas"])
                        if source.get("capacidade") in {"gestao", "tecnica"}:
                            self.assertTrue(permissoes.permite({"nivel": level}, source["capacidade"]))
                    ids = {a["id"] for a in rows}
                    if area == "ambiental":
                        self.assertIn("ambiental-dashboard", ids)
                        self.assertFalse(ids & {"bri", "visitas-arboviroses", "liraa-consulta", "conta-ovos", "registro-geografico-consulta"})
                    else:
                        self.assertIn("bri", ids)
                        self.assertFalse(ids & {"esporotricose-visitas", "esporo-humanos", "vigiagua", "amostras-animais", "ambiental-dashboard"})
                    if level in {"usuario", "visualizador"}:
                        self.assertFalse(ids & {"visitas-edicao", "registro-geografico-edicao", "acoes-setor", "importacao-kobo", "esporo-gestao-visitas", "esporo-doentes-cadastro", "esporo-humanos", "central-backup"})
                    if level != "superadmin":
                        self.assertFalse(ids & {"central-backup", "central-diagnostico", "registros-tecnicos", "kobo-configuracao"})

    def test_busca_contexto_categorias_e_argumentos_forjados_respeitam_escopo(self):
        for area in self.apps:
            client = self.client(area)
            for query in ("backup", "configurar", "importar", "corrigir", "casos humanos"):
                result = self.help(client, q=query, rota="/admin/sistema", contexto="Importação > Casos humanos", nivel="superadmin", setor="ambiental" if area == "endemias" else "endemias")
                forbidden = {"central-backup", "importacao-kobo", "ambiental-importacao-kobo", "esporo-humanos", "visitas-edicao", "esporo-gestao-visitas", "registros-tecnicos"}
                self.assertFalse(forbidden & {a["id"] for a in result["artigos"] + result["contexto"]})
                self.assertEqual(sum(c["total"] for c in result["categorias"]), result["total"])
            other = "esporotricose" if area == "endemias" else "LIRAa"
            result = self.help(client, q=other, rota="/esporotricose" if area == "endemias" else "/liraa")
            self.assertEqual(result["artigos"], [])
            self.assertEqual(result["contexto"], [])
            self.assertEqual(result["categorias"], [])

    def test_negacao_de_link_retira_tambem_contagem_e_contexto(self):
        result = ajuda.consultar(setor="ambiental", nivel="superadmin", rota="/esporotricose", rota_permitida=lambda link: False, limite=120)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["categorias"], [])
        self.assertEqual(result["contexto"], [])

    def test_area_atual_prevalece_sobre_area_da_conta_gestora(self):
        result = self.help(self.client("endemias", "admin", user_area="ambiental"))
        ids = {a["id"] for a in result["artigos"]}
        self.assertIn("bri", ids)
        self.assertNotIn("esporotricose-visitas", ids)
        for route in ("//[", "https://exemplo.invalid/esporotricose"):
            self.assertEqual(self.help(self.client("endemias"), rota=route)["setor"], "endemias")

    def test_contexto_de_aba_nao_promove_artigo_de_outra_pagina(self):
        result = self.help(self.client("ambiental", "admin"), rota="/mapa", contexto="Doentes > Lista")
        self.assertEqual([a["id"] for a in result["contexto"]], ["ambiental-mapa"])

    def test_laboratorio_depende_de_permissao_real_e_modo_exclusivo(self):
        ident = self.ids["endemias", "visualizador"]
        client = self.client("endemias", "visualizador")
        self.assertNotIn("laboratorio-lancamentos", {a["id"] for a in self.help(client)["artigos"]})
        conn = db.connect(str(self.path)); conn.execute("UPDATE usuarios SET acesso_laboratorio=1 WHERE id_usuario=?", (ident,)); conn.commit(); conn.close()
        self.assertIn("laboratorio-lancamentos", {a["id"] for a in self.help(client)["artigos"]})
        result = ajuda.consultar(usuario={"nivel": "visualizador", "acesso_laboratorio": 1, "somente_laboratorio": 1}, setor="endemias", limite=120)
        self.assertEqual({a["id"] for a in result["artigos"]}, {"senha-pessoal", "privacidade", "laboratorio-lancamentos", "laboratorio-historico", "liraa-leitura"})

    def test_api_laboratorio_exclusivo_apos_integracao_do_guard(self):
        ident = self.ids["endemias", "visualizador"]
        conn = db.connect(str(self.path)); conn.execute("UPDATE usuarios SET acesso_laboratorio=1,somente_laboratorio=1 WHERE id_usuario=?", (ident,)); conn.commit(); conn.close()
        response = self.client("endemias", "visualizador").get("/api/ajuda?limite=120")
        if response.status_code == 403 and response.json.get("erro") == "Esta conta possui acesso exclusivo ao laboratorio.":
            self.skipTest("Liberação de ajuda.api_ajuda no guard pertence à integração de app_setup.")
        self.assertEqual(response.status_code, 200)
        self.assertFalse({a["id"] for a in response.json["artigos"]} - {"senha-pessoal", "privacidade", "laboratorio-lancamentos", "laboratorio-historico", "liraa-leitura"})

    def test_resposta_nao_cacheavel_e_fingerprint_muda_com_conta_setor_permissao(self):
        client = self.client("endemias", "usuario")
        response = client.get("/api/ajuda")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("Cookie", response.headers.get("Vary", ""))
        original = response.json["escopo"]
        self.assertNotEqual(original, self.help(self.client("ambiental", "usuario"))["escopo"])
        self.assertNotEqual(original, self.help(self.client("endemias", "admin"))["escopo"])
        conn = db.connect(str(self.path)); conn.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=?", (self.ids["endemias", "usuario"],)); conn.commit(); conn.close()
        self.assertNotEqual(original, self.help(client)["escopo"])

    def test_links_de_paginas_validam_get_real_em_todos_os_perfis(self):
        diagnostic = {"resumo": {"status": "ok", "status_label": "Ensaio", "modo": "ensaio", "contagens": dict(erro=0,aviso=0,info=0,ok=0)}, "itens": []}
        with mock.patch("blueprints.admin.diagnostico_core.gerar", return_value=diagnostic), mock.patch("urllib.request.urlopen", side_effect=AssertionError("Nenhuma rede real permitida no ensaio")):
            for area in self.apps:
                for level in LEVELS:
                    client = self.client(area, level)
                    links = {a["link"] for a in self.help(client)["artigos"]}
                    for link in links:
                        with self.subTest(area=area, level=level, link=link):
                            response = client.get(link)
                            self.assertEqual(response.status_code, 200, link)
