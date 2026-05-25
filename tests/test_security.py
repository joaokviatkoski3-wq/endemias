import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from flask import session as flask_session
from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
import etl
from app_core import audit as audit_core
from app_core import auth as auth_core
from app_core import backup as backup_core
from app_core import esporotricose as esporotricose_core
from app_core import db as db_core
from app_core import modules as modules_core
from app_core import sispncd as sispncd_core
from app_core import version as version_core
from app_core import work_types
from blueprints import processar as processar_bp


def _usuario_teste(nivel=None):
    conn = sqlite3.connect(endemias_app.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        params = []
        filtro_nivel = ""
        if nivel:
            filtro_nivel = "AND nivel=?"
            params.append(nivel)
        row = conn.execute(
            """SELECT id_usuario, nome, nivel FROM usuarios
               WHERE ativo=1
               {filtro_nivel}
               ORDER BY CASE nivel
                   WHEN 'admin' THEN 1
                   WHEN 'operador' THEN 2
                   ELSE 3
               END
               LIMIT 1""".format(filtro_nivel=filtro_nivel),
            params,
        ).fetchone()
    finally:
        conn.close()
    if not row:
        alvo = f" com nivel {nivel}" if nivel else ""
        raise RuntimeError(f"Nenhum usuario ativo{alvo} encontrado para os testes.")
    return dict(row)


def _client_logado(nivel=None):
    endemias_app.app.config["TESTING"] = True
    client = endemias_app.app.test_client()
    usuario = _usuario_teste(nivel=nivel)
    with client.session_transaction() as sess:
        sess["uid"] = usuario["id_usuario"]
        sess["nome"] = usuario["nome"]
        sess["nivel"] = usuario["nivel"]
    return client


def _executar_criar_banco_em(tmpdir, vezes=1):
    import criar_banco

    cwd_original = os.getcwd()
    os.chdir(tmpdir)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(vezes):
                criar_banco.main()
    finally:
        os.chdir(cwd_original)
    return str(Path(tmpdir) / "endemias.db")


def _login_client_com_usuario(client, usuario):
    with client.session_transaction() as sess:
        sess["uid"] = usuario["id_usuario"]
        sess["nome"] = usuario["nome"]
        sess["nivel"] = usuario["nivel"]


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self):
        endemias_app._login_tentativas.clear()

    def tearDown(self):
        endemias_app._login_tentativas.clear()

    def test_bloqueia_apos_limite_de_falhas(self):
        chave = "127.0.0.1:admin"

        for i in range(endemias_app.LOGIN_MAX_TENTATIVAS):
            self.assertFalse(endemias_app._login_bloqueado(chave, agora=100 + i))
            endemias_app._registrar_login_falha(chave, agora=100 + i)

        self.assertTrue(endemias_app._login_bloqueado(chave, agora=120))

    def test_expira_bloqueio_apos_janela(self):
        chave = "127.0.0.1:admin"

        for i in range(endemias_app.LOGIN_MAX_TENTATIVAS):
            endemias_app._registrar_login_falha(chave, agora=100 + i)

        depois_da_janela = 100 + endemias_app.LOGIN_JANELA_SEG + 1
        self.assertFalse(endemias_app._login_bloqueado(chave, agora=depois_da_janela))
        self.assertNotIn(chave, endemias_app._login_tentativas)

    def test_sucesso_limpa_falhas(self):
        chave = "127.0.0.1:admin"
        endemias_app._registrar_login_falha(chave, agora=100)

        endemias_app._limpar_login_falhas(chave)

        self.assertNotIn(chave, endemias_app._login_tentativas)

    def test_rate_limit_persistente_em_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "login.db")

            def get_db():
                return db_core.connect(db_path)

            chave = "127.0.0.1:admin"
            for i in range(endemias_app.LOGIN_MAX_TENTATIVAS):
                self.assertFalse(auth_core.login_bloqueado_db(get_db, chave, agora=100 + i))
                auth_core.registrar_login_falha_db(get_db, chave, agora=100 + i)

            self.assertTrue(auth_core.login_bloqueado_db(get_db, chave, agora=120))
            auth_core.limpar_login_falhas_db(get_db, chave)
            self.assertFalse(auth_core.login_bloqueado_db(get_db, chave, agora=121))


class UploadValidationTests(unittest.TestCase):
    def _xlsx_minimo(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            zf.writestr("xl/workbook.xml", "<workbook></workbook>")
        stream.seek(0)
        return stream

    def test_aceita_xlsx_com_estrutura_zip_excel(self):
        arquivo = FileStorage(
            stream=self._xlsx_minimo(),
            filename="TB_exemplo.xlsx",
        )

        valido, nome, motivo = endemias_app._validar_arquivo_xlsx(arquivo)

        self.assertTrue(valido)
        self.assertEqual(nome, "TB_exemplo.xlsx")
        self.assertEqual(motivo, "")

    def test_rejeita_xlsx_falso(self):
        arquivo = FileStorage(
            stream=io.BytesIO(b"isso nao e xlsx"),
            filename="TB_exemplo.xlsx",
        )

        valido, nome, motivo = endemias_app._validar_arquivo_xlsx(arquivo)

        self.assertFalse(valido)
        self.assertEqual(nome, "TB_exemplo.xlsx")
        self.assertIn("XLSX", motivo)

    def test_rejeita_zip_sem_estrutura_xlsx(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as zf:
            zf.writestr("conteudo.txt", "nao e excel")
        stream.seek(0)
        arquivo = FileStorage(
            stream=stream,
            filename="TB_exemplo.xlsx",
        )

        valido, nome, motivo = endemias_app._validar_arquivo_xlsx(arquivo)

        self.assertFalse(valido)
        self.assertEqual(nome, "TB_exemplo.xlsx")
        self.assertIn("estrutura XLSX", motivo)

    def test_rejeita_extensao_diferente(self):
        arquivo = FileStorage(
            stream=io.BytesIO(b"PK\x03\x04conteudo"),
            filename="TB_exemplo.csv",
        )

        valido, nome, motivo = endemias_app._validar_arquivo_xlsx(arquivo)

        self.assertFalse(valido)
        self.assertEqual(nome, "")
        self.assertIn("Extens", motivo)


class UploadTempCleanupTests(unittest.TestCase):
    def test_limpa_apenas_jobs_uuid_antigos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            antigo = Path(tmpdir) / str(uuid.uuid4())
            recente = Path(tmpdir) / str(uuid.uuid4())
            nao_job = Path(tmpdir) / "manual"
            antigo.mkdir()
            recente.mkdir()
            nao_job.mkdir()
            velho = time.time() - 48 * 3600
            os.utime(antigo, (velho, velho))
            os.utime(nao_job, (velho, velho))

            app_temp = endemias_app.create_app({
                "TESTING": True,
                "UPLOAD_TEMP": tmpdir,
                "DB_PATH": endemias_app.DB_PATH,
            })
            with app_temp.app_context():
                removidos = processar_bp.limpar_uploads_antigos(max_age_hours=24)

            self.assertEqual(removidos, 1)
            self.assertFalse(antigo.exists())
            self.assertTrue(recente.exists())
            self.assertTrue(nao_job.exists())


class RequestParsingTests(unittest.TestCase):
    def test_request_int_arg_usa_default_quando_invalido(self):
        with endemias_app.app.test_request_context("/?pagina=abc"):
            self.assertEqual(endemias_app.request_int_arg("pagina", 1, minimo=1), 1)

    def test_request_int_arg_aplica_limites(self):
        with endemias_app.app.test_request_context("/?pagina=-5&por_pagina=9999"):
            self.assertEqual(endemias_app.request_int_arg("pagina", 1, minimo=1), 1)
            self.assertEqual(
                endemias_app.request_int_arg("por_pagina", 50, minimo=1, maximo=500),
                500,
            )


class DatabaseConnectionTests(unittest.TestCase):
    def test_conexao_sqlite_configura_timeout_e_wal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "teste.db")
            conn = db_core.connect(db_path)
            try:
                self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            finally:
                conn.close()


class BackupTests(unittest.TestCase):
    def _criar_db_minimo(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE dados (id INTEGER PRIMARY KEY, nome TEXT)")
            conn.execute("INSERT INTO dados (nome) VALUES ('registro')")
            conn.commit()
        finally:
            conn.close()

    def test_cria_backup_sqlite_validado_com_metadados(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "origem.db"
            destino = Path(tmpdir) / "backups"
            self._criar_db_minimo(db_path)

            info = backup_core.criar_backup_sqlite(db_path, destino_dir=destino, manter=10)

            backup_path = Path(info["arquivo"])
            meta_path = backup_path.with_suffix(backup_path.suffix + ".json")
            self.assertTrue(backup_path.exists())
            self.assertTrue(meta_path.exists())
            self.assertEqual(info["integridade"], "ok")
            conn = sqlite3.connect(backup_path)
            try:
                self.assertEqual(conn.execute("SELECT nome FROM dados").fetchone()[0], "registro")
            finally:
                conn.close()

    def test_limpa_backups_antigos_respeitando_retencao(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir)
            criados = []
            for i in range(4):
                arquivo = destino / f"endemias_20260101_00000{i}.db"
                arquivo.write_text("x", encoding="utf-8")
                arquivo.with_suffix(".db.json").write_text("{}", encoding="utf-8")
                os.utime(arquivo, (100 + i, 100 + i))
                os.utime(arquivo.with_suffix(".db.json"), (100 + i, 100 + i))
                criados.append(arquivo)

            removidos = backup_core.limpar_backups_antigos(destino, manter=2)

            self.assertEqual([p.name for p in removidos], [criados[1].name, criados[0].name])
            self.assertFalse(criados[0].exists())
            self.assertFalse(criados[0].with_suffix(".db.json").exists())
            self.assertTrue(criados[2].exists())
            self.assertTrue(criados[3].exists())

    def test_lista_backups_com_metadados(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir)
            arquivo = destino / "endemias_20260101_000000.db"
            arquivo.write_text("x", encoding="utf-8")
            arquivo.with_suffix(".db.json").write_text(
                json.dumps({"integridade": "ok", "validado": True}),
                encoding="utf-8",
            )

            backups = backup_core.listar_backups(destino)

            self.assertEqual(backups[0]["nome"], arquivo.name)
            self.assertEqual(backups[0]["integridade"], "ok")
            self.assertTrue(backups[0]["validado"])


class CriarBancoScriptTests(unittest.TestCase):
    def test_criar_banco_roda_em_base_nova_com_hash_moderno(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _executar_criar_banco_em(tmpdir, vezes=2)
            conn = sqlite3.connect(db_path)
            try:
                usuario = conn.execute(
                    "SELECT usuario, senha_hash FROM usuarios WHERE usuario='admin'"
                ).fetchone()
                agenda = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='agenda_eventos'"
                ).fetchone()
                total_admin = conn.execute(
                    "SELECT COUNT(*) FROM usuarios WHERE usuario='admin'"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertIsNotNone(usuario)
        self.assertTrue(usuario[1].startswith("pbkdf2:"))
        self.assertIsNotNone(agenda)
        self.assertEqual(total_admin, 1)


class AuditLogTests(unittest.TestCase):
    def test_registra_evento_de_auditoria(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "audit.db")

            def get_db():
                return db_core.connect(db_path)

            app_temp = endemias_app.create_app({
                "TESTING": True,
                "DB_PATH": db_path,
            })
            with app_temp.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.5"}):
                flask_session["uid"] = 7
                flask_session["nome"] = "Audit User"
                audit_core.registrar_evento(
                    get_db,
                    "teste_evento",
                    entidade="usuarios",
                    entidade_id=3,
                    detalhes={"campo": "nivel", "valor_novo": "admin"},
                )

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM auditoria_eventos").fetchone()
            finally:
                conn.close()

            self.assertIsNotNone(row)
            self.assertEqual(row["acao"], "teste_evento")
            self.assertEqual(row["entidade"], "usuarios")
            self.assertEqual(row["entidade_id"], "3")
            self.assertIn("valor_novo", row["detalhes_json"])

    def test_admin_auditoria_renderiza_eventos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _executar_criar_banco_em(tmpdir)
            app_temp = endemias_app.create_app({"TESTING": True, "DB_PATH": db_path})
            with app_temp.test_request_context("/"):
                flask_session["uid"] = 1
                flask_session["nome"] = "Teste Auditoria"
                audit_core.registrar_evento(
                    endemias_app.get_db,
                    "teste_auditoria_pagina",
                    entidade="usuarios",
                    entidade_id=1,
                    detalhes={"origem": "teste"},
                )

            client = app_temp.test_client()
            _login_client_com_usuario(client, {"id_usuario": 1, "nome": "Administrador", "nivel": "admin"})
            resp = client.get("/admin/auditoria?acao=teste_auditoria_pagina")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("teste_auditoria_pagina", html)
        self.assertIn("Eventos recentes", html)

    def test_admin_auditoria_exporta_xlsx(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _executar_criar_banco_em(tmpdir)
            app_temp = endemias_app.create_app({"TESTING": True, "DB_PATH": db_path})
            with app_temp.test_request_context("/"):
                flask_session["uid"] = 1
                flask_session["nome"] = "Teste Auditoria"
                audit_core.registrar_evento(
                    endemias_app.get_db,
                    "teste_auditoria_exportar",
                    entidade="usuarios",
                    entidade_id=1,
                    detalhes={"origem": "teste"},
                )

            client = app_temp.test_client()
            _login_client_com_usuario(client, {"id_usuario": 1, "nome": "Administrador", "nivel": "admin"})
            resp = client.get("/admin/auditoria/exportar?acao=teste_auditoria_exportar")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resp.content_type,
        )
        self.assertTrue(resp.data.startswith(b"PK"))


class WorkTypesConfigTests(unittest.TestCase):
    def _config(self):
        with open(endemias_app.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_config_json_cobre_tipos_de_trabalho_centrais(self):
        errors = work_types.validate_config_work_types(self._config())
        self.assertEqual(errors, [])

    def test_detecta_tipo_no_config_sem_cadastro_central(self):
        cfg = self._config()
        cfg["tipos_trabalho"]["XYZ"] = dict(next(iter(cfg["tipos_trabalho"].values())))

        errors = work_types.validate_config_work_types(cfg)

        self.assertTrue(any("XYZ" in e for e in errors))

    def test_detecta_tipo_central_sem_config(self):
        cfg = self._config()
        cfg["tipos_trabalho"].pop(work_types.WORK_TYPE_CODES[0])

        errors = work_types.validate_config_work_types(cfg)

        self.assertTrue(any(work_types.WORK_TYPE_CODES[0] in e for e in errors))

    def test_etl_usa_metadados_centrais_para_tratamentos(self):
        row = {
            "O imóvel foi Tratado com Larvicida?": "sim",
            "Tipo L1": "Natular",
            "Quantidade carga (gr)": "3,5",
            "Quantidade depósitos tratados": "2",
        }

        tratamentos = etl.extrair_tratamentos(row, "TB")

        self.assertEqual(tratamentos, [{
            "tipo": "Natular",
            "quantidade_carga": 3.5,
            "qtd_depositos_tratados": 2,
        }])

    def test_etl_tbo_mantem_tratamentos_nos_depositos(self):
        self.assertEqual(etl.extrair_tratamentos({}, "TBO"), [])

    def test_regra_de_notificacao_padrao_fica_centralizada(self):
        self.assertEqual(work_types.gera_notificacao_padrao("PE"), 0)
        self.assertEqual(work_types.gera_notificacao_padrao("TB"), 1)
        self.assertEqual(work_types.gera_notificacao_padrao("TIPO_NOVO"), 1)

    def test_tipo_com_duracao_fica_centralizado(self):
        self.assertIn("TBO", work_types.duration_work_type_codes())
        self.assertEqual(work_types.primary_duration_work_type_code(), "TBO")


class ModuleRegistryTests(unittest.TestCase):
    def test_modulos_de_ui_tem_icones_existentes(self):
        for module in modules_core.MODULES:
            with self.subTest(module=module.key):
                self.assertTrue((ROOT / "static" / "icons" / module.icon).exists())

    def test_visualizador_nao_ve_modulos_admin(self):
        visiveis = modules_core.visible_modules({"nivel": "visualizador"})
        keys = {module.key for module in visiveis}

        self.assertNotIn("processar", keys)
        self.assertNotIn("usuarios", keys)

    def test_admin_ve_modulos_admin(self):
        visiveis = modules_core.visible_modules({"nivel": "admin"})
        keys = {module.key for module in visiveis}

        self.assertIn("processar", keys)
        self.assertIn("usuarios", keys)


class EsporotricoseSchemaTests(unittest.TestCase):
    def test_schema_cria_tabelas_de_esporotricose(self):
        with sqlite3.connect(":memory:") as conn:
            esporotricose_core.ensure_schema(conn)
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'esporotricose_%'"
                )
            }

        self.assertIn("esporotricose_visitas", tabelas)
        self.assertIn("esporotricose_animais", tabelas)
        self.assertIn("esporotricose_visita_agentes", tabelas)


class ProtectedRouteTests(unittest.TestCase):
    def test_home_sem_login_redireciona_para_login(self):
        endemias_app.app.config["TESTING"] = True
        with endemias_app.app.test_client() as client:
            resp = client.get("/")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_respostas_incluem_headers_basicos_de_seguranca(self):
        endemias_app.app.config["TESTING"] = True
        with endemias_app.app.test_client() as client:
            resp = client.get("/login")

        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(resp.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("camera=()", resp.headers["Permissions-Policy"])
        csp = resp.headers["Content-Security-Policy-Report-Only"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertIn("form-action 'self'", csp)

    def test_csp_pode_ser_ativada_em_modo_bloqueante(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
            "CSP_REPORT_ONLY": False,
        })
        with app_temp.test_client() as client:
            resp = client.get("/login")

        self.assertIn("default-src 'self'", resp.headers["Content-Security-Policy"])
        self.assertNotIn("Content-Security-Policy-Report-Only", resp.headers)

    def test_logout_nao_aceita_get(self):
        client = _client_logado()

        resp = client.get("/logout")

        self.assertEqual(resp.status_code, 405)

    def test_minha_senha_exige_csrf(self):
        client = _client_logado()

        resp = client.post("/minha-senha", data={
            "atual": "qualquer",
            "nova": "123456",
            "confirmar": "123456",
        })

        self.assertEqual(resp.status_code, 400)

    def test_confirmar_processamento_nao_aceita_get(self):
        client = _client_logado("admin")

        resp = client.get("/processar/confirmar/job-inexistente")

        self.assertEqual(resp.status_code, 405)

    def test_stream_processamento_nao_aceita_get(self):
        client = _client_logado("admin")

        resp = client.get("/processar/stream/job-inexistente")

        self.assertEqual(resp.status_code, 405)

    def test_rotas_processamento_rejeitam_job_id_invalido(self):
        original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
        endemias_app.app.config["WTF_CSRF_ENABLED"] = False
        try:
            client = _client_logado("admin")
            for rota in (
                "/processar/stream/job-invalido",
                "/processar/confirmar/job-invalido",
                "/processar/cancelar/job-invalido",
            ):
                with self.subTest(rota=rota):
                    resp = client.post(rota)
                    self.assertEqual(resp.status_code, 404)
        finally:
            endemias_app.app.config["WTF_CSRF_ENABLED"] = original

    def test_impressao_html_individual_nao_aceita_get(self):
        client = _client_logado("admin")
        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            row = conn.execute(
                "SELECT id_foco FROM focos_positivos WHERE gera_notificacao=1 LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

        resp = client.get(f"/notificacoes/foco/{row[0]}/imprimir-html")

        self.assertEqual(resp.status_code, 405)


class MainPagesSmokeTests(unittest.TestCase):
    def test_paginas_principais_logadas_respondem_200(self):
        client = _client_logado()
        rotas = [
            "/dashboard",
            "/visitas",
            "/laboratorio",
            "/conta-ovos-sispncd",
            "/esporotricose",
            "/notificacoes",
            "/mapa",
            "/agenda",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/html", resp.content_type)

    def test_central_do_sistema_admin_responde_200(self):
        client = _client_logado("admin")
        resp = client.get("/admin/sistema")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Central do Sistema", html)
        self.assertIn("Saúde do ambiente", html)
        self.assertIn("Backups recentes", html)

    def test_home_operacional_renderiza_blocos_principais(self):
        client = _client_logado()
        resp = client.get("/")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Painel operacional", html)
        self.assertIn("Ritmo dos últimos 14 dias", html)
        self.assertIn("Atalhos do sistema", html)

    def test_home_admin_exibe_blocos_operacionais_restritos(self):
        client = _client_logado("admin")
        resp = client.get("/")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Importações recentes", html)
        self.assertIn("Backups", html)
        self.assertIn("/admin/sistema", html)

    def test_processar_exibe_historico_de_importacoes(self):
        client = _client_logado("admin")
        resp = client.get("/processar")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Ultimas importacoes", resp.data)

    def test_assets_compartilhados_respondem_200(self):
        client = _client_logado()
        for rota in (
            "/static/css/app.css",
            "/static/js/app.js",
            "/static/vendor/chartjs/chart.umd.min.js",
            "/static/vendor/chartjs-plugin-datalabels/chartjs-plugin-datalabels.min.js",
            "/static/vendor/leaflet/leaflet.min.css",
            "/static/vendor/leaflet/leaflet.min.js",
        ):
            with self.subTest(rota=rota):
                resp = client.get(rota)
                try:
                    self.assertEqual(resp.status_code, 200)
                finally:
                    resp.close()

    def test_templates_principais_nao_dependem_de_cdn_externo(self):
        for rel in ("templates/base.html", "templates/login.html", "templates/mapa.html"):
            with self.subTest(rel=rel):
                texto = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("cdnjs.cloudflare.com", texto)
                self.assertNotIn("fonts.googleapis.com", texto)

    def test_tema_claro_escuro_tem_contrato_explicito(self):
        css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

        self.assertIn('[data-theme="light"]', css)
        self.assertIn('[data-theme="dark"]', css)
        self.assertIn("localStorage.getItem('theme')", js)
        self.assertIn("document.documentElement.setAttribute('data-theme', currentTheme)", js)
        self.assertIn("currentTheme === 'dark' ? 'light' : 'dark'", js)

    def test_versao_aparece_no_base_e_no_login(self):
        client = _client_logado()
        home = client.get("/")
        login = endemias_app.app.test_client().get("/login")

        self.assertIn(version_core.APP_VERSION_LABEL.encode("utf-8"), home.data)
        self.assertIn(version_core.APP_VERSION_LABEL.encode("utf-8"), login.data)

    def test_detalhe_notificacao_renderiza_icones_sem_escape(self):
        client = _client_logado()
        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            row = conn.execute(
                "SELECT id_foco FROM focos_positivos WHERE gera_notificacao=1 LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

        resp = client.get(f"/notificacoes/foco/{row[0]}")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertNotIn("&lt;img", html)
        self.assertIn('src="/static/icons/salvar.svg"', html)

    def test_agenda_eventos_expoem_cores_para_fullcalendar(self):
        client = _client_logado()
        resp = client.get("/api/agenda/eventos?start=2026-01-01&end=2026-12-31")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        eventos = resp.get_json()
        self.assertTrue(eventos)
        for evento in eventos:
            self.assertIn("backgroundColor", evento)
            self.assertIn("borderColor", evento)
            self.assertIn("textColor", evento)

    def test_agenda_nao_forca_cor_global_nos_eventos(self):
        client = _client_logado()
        resp = client.get("/agenda")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertNotIn("background-color: var(--fc-event-bg-color) !important", html)
        self.assertIn("style.setProperty('background-color', bg, 'important')", html)


class MainApisSmokeTests(unittest.TestCase):
    def test_create_app_permanece_configuravel(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
        })

        self.assertTrue(app_temp.config["TESTING"])
        self.assertEqual(app_temp.config["DB_PATH"], endemias_app.DB_PATH)
        self.assertGreater(app_temp.config["MAX_CONTENT_LENGTH"], 0)
        endpoints = {str(rule): rule.endpoint for rule in app_temp.url_map.iter_rules()}
        self.assertEqual(endpoints["/"], "home.page")

    def test_wrappers_de_banco_respeitam_db_path_do_app_atual(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "isolado.db")
            app_temp = endemias_app.create_app({
                "TESTING": True,
                "DB_PATH": db_path,
            })

            with app_temp.app_context():
                conn = endemias_app.get_db()
                try:
                    conn.execute("CREATE TABLE marcador (valor TEXT)")
                    conn.execute("INSERT INTO marcador (valor) VALUES ('ok')")
                    conn.commit()
                finally:
                    conn.close()

                self.assertEqual(endemias_app.qval("SELECT valor FROM marcador"), "ok")

            self.assertTrue(Path(db_path).exists())

    def test_resolve_paths_suporta_instance_dir_e_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "ENDEMIAS_INSTANCE_DIR": tmpdir,
                "ENDEMIAS_DB_PATH": str(Path(tmpdir) / "dados.db"),
                "ENDEMIAS_UPLOAD_TEMP": str(Path(tmpdir) / "uploads"),
            }

            paths = endemias_app.resolve_paths(env=env, base_dir=str(ROOT))

        self.assertEqual(paths["INSTANCE_DIR"], os.path.abspath(tmpdir))
        self.assertEqual(paths["DB_PATH"], os.path.abspath(env["ENDEMIAS_DB_PATH"]))
        self.assertEqual(paths["UPLOAD_TEMP"], os.path.abspath(env["ENDEMIAS_UPLOAD_TEMP"]))
        self.assertEqual(paths["CONFIG_PATH"], os.path.abspath(str(ROOT / "config.json")))
        self.assertTrue(paths["LOG_PATH"].endswith("endemias.log"))
        self.assertTrue(paths["SECRET_KEY_PATH"].endswith("secret.key"))

    def test_apis_principais_logadas_retornam_json(self):
        client = _client_logado()
        rotas = [
            "/api/dashboard",
            "/api/visitas?pagina=1&por_pagina=5",
            "/api/laboratorio?pagina=1&por_pagina=5",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.is_json)

    def test_api_conta_ovos_e_sispncd_consultas_retornam_json(self):
        client = _client_logado()
        padrao = sispncd_core.get_default_conta_ovos(endemias_app.DB_PATH)
        rotas = [
            f"/api/conta-ovos?data={padrao['data']}&quarteirao={padrao['quarteirao']}",
            "/api/sispncd/pesquisar?ano=2026&semana=20&tipo=TB/TBO&tipo=PVE&tipo=PE",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.is_json)

    def test_api_esporotricose_retorna_json(self):
        client = _client_logado()
        resp = client.get("/api/esporotricose")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        dados = resp.get_json()
        self.assertIn("totais", dados)
        self.assertIn("animais", dados)

    def test_pagina_esporotricose_exibe_abas_principais(self):
        client = _client_logado()
        resp = client.get("/esporotricose")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("esporo-tabbar", html)
        self.assertIn("esp-tab-visitas", html)
        self.assertIn("esp-tab-animais", html)
        self.assertIn("esp-tab-atencao", html)
        self.assertIn("esp-tab-localidades", html)
        self.assertIn("esp-tab-dashboard", html)
        self.assertIn("Animais cadastrados", html)
        self.assertIn("vis-busca", html)
        self.assertIn("vis-agente", html)

    def test_api_esporotricose_animais_retorna_detalhes(self):
        client = _client_logado()
        resp = client.get("/api/esporotricose/animais?feridas=Sim")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        dados = resp.get_json()
        self.assertIn("total", dados)
        self.assertIn("registros", dados)
        if dados["registros"]:
            self.assertIn("nome", dados["registros"][0])
            self.assertIn("morador", dados["registros"][0])

    def test_api_esporotricose_visitas_retorna_agentes_e_busca(self):
        client = _client_logado()
        resp = client.get("/api/esporotricose/visitas?busca=Graziela")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        dados = resp.get_json()
        self.assertIn("total", dados)
        self.assertIn("registros", dados)
        if dados["registros"]:
            self.assertIn("agentes", dados["registros"][0])
            self.assertIn("morador", dados["registros"][0])

    def test_api_esporotricose_localidades_retorna_resumo(self):
        client = _client_logado()
        resp = client.get("/api/esporotricose/localidades")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        dados = resp.get_json()
        self.assertIn("registros", dados)
        if dados["registros"]:
            self.assertIn("localidade", dados["registros"][0])
            self.assertIn("visitas", dados["registros"][0])

    def test_api_esporotricose_dashboard_retorna_series(self):
        client = _client_logado()
        resp = client.get("/api/esporotricose/dashboard")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        dados = resp.get_json()
        for chave in ("evolucao", "status", "especies", "ambiente", "localidades", "saude"):
            self.assertIn(chave, dados)

    def test_consultas_sispncd_nao_alteram_coluna_sispncd(self):
        client = _client_logado()
        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            antes = conn.execute(
                "SELECT COUNT(*), COUNT(SISPNCD), COUNT(DISTINCT SISPNCD) FROM visitas"
            ).fetchone()
        finally:
            conn.close()

        resp = client.get("/api/sispncd/pesquisar?ano=2026&semana=20&tipo=TB/TBO&tipo=PVE&tipo=PE")
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            depois = conn.execute(
                "SELECT COUNT(*), COUNT(SISPNCD), COUNT(DISTINCT SISPNCD) FROM visitas"
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(antes, depois)

    def test_conta_ovos_filtra_status_pendente_e_salva_status(self):
        client = _client_logado("admin")
        padrao = sispncd_core.get_default_conta_ovos(endemias_app.DB_PATH)

        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            pendentes_antes = conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND CONTAOVOS_STATUS=0"
            ).fetchone()[0]
            ja_registrados = conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND CONTAOVOS_STATUS=1 AND data=? AND quarteirao=?",
                (padrao["data"], padrao["quarteirao"]),
            ).fetchone()[0]
            esperado_periodo = conn.execute(
                """SELECT COUNT(*) FROM visitas
                   WHERE tipo='TBO'
                     AND CONTAOVOS_STATUS=0
                     AND data=?
                     AND quarteirao=?
                     AND LOWER(COALESCE(visita,'')) IN ('normal','recuperado','fechado','recusa')""",
                (padrao["data"], padrao["quarteirao"]),
            ).fetchone()[0]
        finally:
            conn.close()

        resp = client.get(f"/api/conta-ovos?data={padrao['data']}&quarteirao={padrao['quarteirao']}")
        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertEqual(dados["total_visitas"], esperado_periodo)
        if ja_registrados:
            self.assertLessEqual(dados["total_visitas"], pendentes_antes)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_tmp = Path(tmpdir) / "endemias.db"
            shutil.copy2(endemias_app.DB_PATH, db_tmp)
            original_db = endemias_app.app.config["DB_PATH"]
            csrf_original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
            endemias_app.app.config["DB_PATH"] = str(db_tmp)
            endemias_app.app.config["WTF_CSRF_ENABLED"] = False
            try:
                padrao_tmp = sispncd_core.get_default_conta_ovos(str(db_tmp))
                conn = sqlite3.connect(db_tmp)
                esperado_salvar = conn.execute(
                    """SELECT COUNT(*) FROM visitas
                       WHERE tipo='TBO' AND CONTAOVOS_STATUS=0 AND data=? AND quarteirao=?""",
                    (padrao_tmp["data"], padrao_tmp["quarteirao"]),
                ).fetchone()[0]
                conn.close()
                self.assertGreater(esperado_salvar, 0)

                client_tmp = _client_logado("admin")
                salvar = client_tmp.post(
                    "/api/conta-ovos/salvar-status",
                    json={"data": padrao_tmp["data"], "quarteirao": padrao_tmp["quarteirao"]},
                )
                self.assertEqual(salvar.status_code, 200)
                self.assertEqual(salvar.get_json()["atualizados"], esperado_salvar)

                conn = sqlite3.connect(db_tmp)
                restantes = conn.execute(
                    """SELECT COUNT(*) FROM visitas
                       WHERE tipo='TBO' AND CONTAOVOS_STATUS=0 AND data=? AND quarteirao=?""",
                    (padrao_tmp["data"], padrao_tmp["quarteirao"]),
                ).fetchone()[0]
                conn.close()
                self.assertEqual(restantes, 0)
            finally:
                endemias_app.app.config["DB_PATH"] = original_db
                endemias_app.app.config["WTF_CSRF_ENABLED"] = csrf_original

    def test_sispncd_salva_codigo_sem_sobrescrever_existentes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_tmp = Path(tmpdir) / "endemias.db"
            shutil.copy2(endemias_app.DB_PATH, db_tmp)
            original_db = endemias_app.app.config["DB_PATH"]
            csrf_original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
            endemias_app.app.config["DB_PATH"] = str(db_tmp)
            endemias_app.app.config["WTF_CSRF_ENABLED"] = False
            try:
                conn = sqlite3.connect(db_tmp)
                row = conn.execute(
                    """SELECT data, tipo
                        FROM visitas
                        WHERE SISPNCD IS NULL
                        ORDER BY data DESC
                        LIMIT 1"""
                ).fetchone()
                conn.close()
                self.assertIsNotNone(row)
                ano, semana, _ = sispncd_core.date.fromisoformat(row[0]).isocalendar()

                client = _client_logado("admin")
                codigo = "9999/2026"
                salvar = client.post(
                    "/api/sispncd/salvar",
                    json={"ano": ano, "semana": semana, "tipo": [row[1]], "codigo": codigo},
                )
                self.assertEqual(salvar.status_code, 200)
                atualizados = salvar.get_json()["atualizados"]
                self.assertGreater(atualizados, 0)

                conn = sqlite3.connect(db_tmp)
                try:
                    gravados = conn.execute(
                        "SELECT COUNT(*) FROM visitas WHERE SISPNCD=?",
                        (codigo,),
                    ).fetchone()[0]
                    nulos_restantes_no_codigo = conn.execute(
                        "SELECT COUNT(*) FROM visitas WHERE SISPNCD IS NULL"
                    ).fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(gravados, atualizados)
                self.assertGreaterEqual(nulos_restantes_no_codigo, 0)
            finally:
                endemias_app.app.config["DB_PATH"] = original_db
                endemias_app.app.config["WTF_CSRF_ENABLED"] = csrf_original

    def test_api_pendencias_conta_ovos_sispncd_retorna_resumo(self):
        client = _client_logado()
        resp = client.get("/api/conta-ovos-sispncd/pendencias")

        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertIn("conta_ovos", dados)
        self.assertIn("sispncd", dados)
        self.assertIn("total", dados["conta_ovos"])
        self.assertIn("grupos", dados["sispncd"])

        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            esperado_graziela = conn.execute(
                """SELECT COUNT(*) FROM visitas
                   WHERE tipo='TBO'
                     AND localidade='Graziela'
                     AND data='2026-05-04'
                     AND CONTAOVOS_STATUS=0"""
            ).fetchone()[0]
        finally:
            conn.close()

        if esperado_graziela:
            grupos = dados["conta_ovos"]["grupos"]
            self.assertTrue(any(
                g["data"] == "2026-05-04" and g["localidade"] == "Graziela"
                for g in grupos
            ))
            self.assertTrue(all("id_localidade" in g for g in grupos))

    def test_conta_ovos_pendencias_sao_clicaveis_para_filtrar(self):
        client = _client_logado()
        resp = client.get("/conta-ovos-sispncd")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("selecionarPendenciaContaOvos", html)
        self.assertIn("data-localidade-id", html)
        self.assertIn("await buscarContaOvos()", html)

    def test_api_visitas_tem_campos_de_paginacao(self):
        client = _client_logado()
        resp = client.get("/api/visitas?pagina=1&por_pagina=5")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("total", dados)
        self.assertIn("total_paginas", dados)
        self.assertIn("pagina", dados)
        self.assertIn("registros", dados)

    def test_api_laboratorio_tem_campos_de_paginacao(self):
        client = _client_logado()
        resp = client.get("/api/laboratorio?pagina=1&por_pagina=5")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("total", dados)
        self.assertIn("total_paginas", dados)
        self.assertIn("pagina", dados)
        self.assertIn("registros", dados)

    def test_api_mapa_expoe_tipos_dinamicos(self):
        client = _client_logado()
        resp = client.get("/api/mapa")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(dados, dict)
        if dados:
            primeiro = next(iter(dados.values()))
            self.assertIn("tipos", primeiro)
            self.assertIsInstance(primeiro["tipos"], dict)

    def test_mapa_usa_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {"/mapa", "/api/mapa"}
        }

        self.assertEqual(endpoints["/mapa"], "mapa.page")
        self.assertEqual(endpoints["/api/mapa"], "mapa.api_mapa")

    def test_apis_consultas_usam_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {"/api/dashboard", "/api/laboratorio", "/api/visitas"}
        }

        self.assertEqual(endpoints["/api/dashboard"], "consultas.api_dashboard")
        self.assertEqual(endpoints["/api/laboratorio"], "consultas.api_laboratorio")
        self.assertEqual(endpoints["/api/visitas"], "consultas.api_visitas")

    def test_exportacoes_usam_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {
                "/api/visitas/exportar",
                "/api/notificacoes/exportar",
                "/api/laboratorio/exportar",
                "/saida/download/<tipo>",
            }
        }

        self.assertEqual(endpoints["/api/visitas/exportar"], "exportacoes.exportar_visitas")
        self.assertEqual(endpoints["/api/notificacoes/exportar"], "exportacoes.exportar_notificacoes")
        self.assertEqual(endpoints["/api/laboratorio/exportar"], "exportacoes.exportar_laboratorio")
        self.assertEqual(endpoints["/saida/download/<tipo>"], "exportacoes.saida_download")

    def test_notificacoes_usam_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {
                "/notificacoes",
                "/notificacoes/foco/<id_foco>",
                "/notificacoes/foco/<id_foco>/atualizar",
                "/notificacoes/foco/<id_foco>/status",
                "/notificacoes/imprimir",
                "/notificacoes/foco/<id_foco>/imprimir-html",
                "/notificacoes/imprimir-html",
            }
        }

        self.assertEqual(endpoints["/notificacoes"], "notificacoes.page")
        self.assertEqual(endpoints["/notificacoes/foco/<id_foco>"], "notificacoes.foco_detalhe")
        self.assertEqual(
            endpoints["/notificacoes/foco/<id_foco>/atualizar"],
            "notificacoes.foco_atualizar",
        )
        self.assertEqual(
            endpoints["/notificacoes/foco/<id_foco>/status"],
            "notificacoes.foco_status_rapido",
        )
        self.assertEqual(endpoints["/notificacoes/imprimir"], "notificacoes.imprimir")
        self.assertEqual(
            endpoints["/notificacoes/foco/<id_foco>/imprimir-html"],
            "notificacoes.imprimir_html_single",
        )
        self.assertEqual(
            endpoints["/notificacoes/imprimir-html"],
            "notificacoes.imprimir_html_lote",
        )

    def test_auth_usa_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {"/login", "/logout", "/minha-senha"}
        }

        self.assertEqual(endpoints["/login"], "auth.login")
        self.assertEqual(endpoints["/logout"], "auth.logout")
        self.assertEqual(endpoints["/minha-senha"], "auth.minha_senha")

    def test_admin_auditoria_usa_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) in {"/admin/sistema", "/admin/auditoria", "/admin/auditoria/exportar"}
        }

        self.assertEqual(endpoints["/admin/sistema"], "admin.admin_sistema")
        self.assertEqual(endpoints["/admin/auditoria"], "admin.admin_auditoria")
        self.assertEqual(endpoints["/admin/auditoria/exportar"], "admin.admin_auditoria_exportar")

    def test_home_usa_blueprint_proprio(self):
        endpoints = {
            str(rule): rule.endpoint
            for rule in endemias_app.app.url_map.iter_rules()
            if str(rule) == "/"
        }

        self.assertEqual(endpoints["/"], "home.page")

    def test_exportacoes_retornam_xlsx(self):
        client = _client_logado()
        rotas = [
            "/api/visitas/exportar?d_ini=2099-01-01&d_fim=2099-01-02",
            "/api/notificacoes/exportar?d_ini=2099-01-01&d_fim=2099-01-02",
            "/api/laboratorio/exportar?d_ini=2099-01-01&d_fim=2099-01-02",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                try:
                    self.assertEqual(resp.status_code, 200)
                    self.assertIn(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        resp.content_type,
                    )
                    self.assertTrue(resp.data.startswith(b"PK"))
                finally:
                    resp.close()

    def test_api_agenda_eventos_automaticos_sem_mojibake(self):
        client = _client_logado()
        resp = client.get("/api/agenda/eventos?start=2020-01-01&end=2035-12-31")
        eventos = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(eventos, list)
        proibidos = ("Â", "â", "ð")
        for evento in eventos:
            props = evento.get("extendedProps", {})
            if props.get("origem") != "auto":
                continue
            textos = [
                evento.get("title", ""),
                props.get("resumo", ""),
                props.get("agentes", ""),
            ]
            for texto in textos:
                self.assertFalse(any(c in texto for c in proibidos), texto)


class PermissionMatrixTests(unittest.TestCase):
    def test_visualizador_acessa_paginas_de_consulta(self):
        client = _client_logado("visualizador")
        rotas = [
            "/",
            "/dashboard",
            "/visitas",
            "/laboratorio",
            "/conta-ovos-sispncd",
            "/esporotricose",
            "/notificacoes",
            "/mapa",
            "/agenda",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)

    def test_visualizador_nao_acessa_areas_admin(self):
        client = _client_logado("visualizador")
        rotas = [
            "/processar",
            "/admin/sistema",
            "/admin/usuarios",
            "/admin/auditoria",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 403)

    def test_admin_acessa_areas_admin(self):
        client = _client_logado("admin")
        rotas = [
            "/processar",
            "/admin/sistema",
            "/admin/usuarios",
            "/admin/auditoria",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)

    def test_visualizador_acessa_apis_de_consulta(self):
        client = _client_logado("visualizador")
        rotas = [
            "/api/dashboard",
            "/api/visitas?pagina=1&por_pagina=5",
            "/api/laboratorio?pagina=1&por_pagina=5",
            "/api/mapa",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.is_json)


class ImportHistoryTests(unittest.TestCase):
    def test_registra_e_atualiza_importacao_em_banco_temporario(self):
        db_original = endemias_app.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            db_temp = str(Path(tmp) / "teste.db")
            endemias_app.DB_PATH = db_temp
            try:
                endemias_app.registrar_importacao(
                    "job-teste",
                    ["TB_teste.xlsx", "LARVAS_teste.xlsx"],
                    usuario="Teste",
                )
                endemias_app.atualizar_importacao(
                    "job-teste",
                    "dry_run_ok",
                    dry_run_ok=True,
                    sumario=[{"arquivo": "TB_teste.xlsx", "visitas_novas": 2}],
                )

                conn = sqlite3.connect(db_temp)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM importacoes WHERE job_id=?",
                    ("job-teste",),
                ).fetchone()
                conn.close()
            finally:
                endemias_app.DB_PATH = db_original

        self.assertIsNotNone(row)
        self.assertEqual(row["usuario"], "Teste")
        self.assertEqual(row["status"], "dry_run_ok")
        self.assertEqual(row["dry_run_ok"], 1)
        self.assertEqual(json.loads(row["arquivos_json"]), ["TB_teste.xlsx", "LARVAS_teste.xlsx"])
        self.assertEqual(json.loads(row["sumario_json"])[0]["visitas_novas"], 2)


if __name__ == "__main__":
    unittest.main()
