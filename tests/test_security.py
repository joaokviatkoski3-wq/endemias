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
from unittest import mock

import openpyxl
from flask import session as flask_session
from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
import etl
from app_core import audit as audit_core
from app_core import auth as auth_core
from app_core import backup as backup_core
from app_core import amostras_animais as amostras_animais_core
from app_core import esporotricose as esporotricose_core
from app_core import db as db_core
from app_core import modules as modules_core
from app_core import bri as bri_core
from app_core import pontos_estrategicos as pe_core
from app_core import recolhimentos as recolhimentos_core
from app_core import sispncd as sispncd_core
from app_core import sispncd_indice as sispncd_indice_core
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


def _agente_relatorio_teste():
    conn = sqlite3.connect(endemias_app.DB_PATH)
    try:
        row = conn.execute(
            """SELECT ag.nome
               FROM agentes ag
               JOIN esporotricose_visita_agentes va ON va.id_agente=ag.id_agente
               LIMIT 1"""
        ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT a.nome
                   FROM agentes a
                   JOIN visita_agentes va ON va.id_agente=a.id_agente
                   LIMIT 1"""
            ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("Nenhum agente encontrado para os testes do relatorio.")
    return row[0]


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

    def test_senha_minima_centralizada(self):
        self.assertFalse(auth_core.senha_valida("123456"))
        self.assertTrue(auth_core.senha_valida("1234567890"))
        self.assertIn(str(auth_core.PASSWORD_MIN_LENGTH), auth_core.mensagem_senha_invalida())

    def test_chave_login_ignora_x_forwarded_for_sem_proxy_confiavel(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
            "TRUST_PROXY_HEADERS": False,
        })
        with app_temp.test_request_context(
            "/login",
            environ_base={"REMOTE_ADDR": "10.0.0.5"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        ):
            self.assertEqual(auth_core.chave_login("Admin"), "10.0.0.5:admin")

    def test_chave_login_usa_x_forwarded_for_quando_proxy_confiavel(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
            "TRUST_PROXY_HEADERS": True,
        })
        with app_temp.test_request_context(
            "/login",
            environ_base={"REMOTE_ADDR": "10.0.0.5"},
            headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.5"},
        ):
            self.assertEqual(auth_core.chave_login("Admin"), "203.0.113.9:admin")


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

    def test_restaura_backup_sqlite_validado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "origem.db"
            destino = Path(tmpdir) / "backups"
            self._criar_db_minimo(db_path)
            info = backup_core.criar_backup_sqlite(db_path, destino_dir=destino, manter=10)

            conn = sqlite3.connect(db_path)
            try:
                conn.execute("UPDATE dados SET nome='alterado' WHERE id=1")
                conn.commit()
            finally:
                conn.close()

            restore = backup_core.restaurar_backup_sqlite(db_path, info["arquivo"])

            self.assertEqual(restore["integridade"], "ok")
            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(conn.execute("SELECT nome FROM dados").fetchone()[0], "registro")
            finally:
                conn.close()

    def test_resolver_backup_rejeita_caminho_fora_da_pasta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                backup_core.resolver_backup(Path(tmpdir) / "backups", "../origem.db")

    def test_operacao_exclusiva_rejeita_concorrencia(self):
        with backup_core.operacao_exclusiva():
            with self.assertRaises(RuntimeError):
                with backup_core.operacao_exclusiva():
                    pass


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


class AdminBackupRoutesTests(unittest.TestCase):
    def _app_e_cliente_admin(self, tmpdir):
        db_path = _executar_criar_banco_em(tmpdir)
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": db_path,
            "WTF_CSRF_ENABLED": False,
        })
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            usuario = conn.execute(
                "SELECT id_usuario, nome, nivel FROM usuarios WHERE usuario='admin'"
            ).fetchone()
        finally:
            conn.close()
        client = app_temp.test_client()
        _login_client_com_usuario(client, dict(usuario))
        return app_temp, client, Path(db_path)

    def test_admin_cria_backup_pela_central_do_sistema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_temp, client, db_path = self._app_e_cliente_admin(tmpdir)
            with app_temp.app_context():
                resp = client.post("/admin/sistema/backups/criar")

            self.assertEqual(resp.status_code, 302)
            backups = list((db_path.parent / "backups").glob("endemias_*.db"))
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].with_suffix(".db.json").exists())

    def test_admin_restaura_backup_pela_central_do_sistema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_temp, client, db_path = self._app_e_cliente_admin(tmpdir)
            backup_dir = db_path.parent / "backups"
            info = backup_core.criar_backup_sqlite(db_path, destino_dir=backup_dir, manter=10)
            nome_backup = Path(info["arquivo"]).name

            conn = sqlite3.connect(db_path)
            try:
                conn.execute("UPDATE usuarios SET nome='Depois' WHERE usuario='admin'")
                conn.commit()
            finally:
                conn.close()

            with app_temp.app_context():
                resp = client.post("/admin/sistema/backups/restaurar", data={"backup": nome_backup})

            self.assertEqual(resp.status_code, 302)
            conn = sqlite3.connect(db_path)
            try:
                nome = conn.execute("SELECT nome FROM usuarios WHERE usuario='admin'").fetchone()[0]
            finally:
                conn.close()
            self.assertNotEqual(nome, "Depois")
            self.assertTrue(list(backup_dir.glob("pre_restore_*.db")))

    def test_admin_baixa_backup_pela_central_do_sistema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_temp, client, db_path = self._app_e_cliente_admin(tmpdir)
            backup_dir = db_path.parent / "backups"
            info = backup_core.criar_backup_sqlite(db_path, destino_dir=backup_dir, manter=10)
            nome_backup = Path(info["arquivo"]).name

            with app_temp.app_context():
                resp = client.get(f"/admin/sistema/backups/baixar/{nome_backup}")

            self.assertEqual(resp.status_code, 200)
            self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
            data = resp.get_data()
            resp.close()
            self.assertGreater(len(data), 0)

    def test_admin_exclui_backup_pela_central_do_sistema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_temp, client, db_path = self._app_e_cliente_admin(tmpdir)
            backup_dir = db_path.parent / "backups"
            info = backup_core.criar_backup_sqlite(db_path, destino_dir=backup_dir, manter=10)
            backup_path = Path(info["arquivo"])

            with app_temp.app_context():
                resp = client.post("/admin/sistema/backups/excluir", data={"backup": backup_path.name})

            self.assertEqual(resp.status_code, 302)
            self.assertFalse(backup_path.exists())
            self.assertFalse(backup_path.with_suffix(".db.json").exists())

    def test_confirmar_importacao_cria_backup_pre_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_temp, client, db_path = self._app_e_cliente_admin(tmpdir)
            upload_temp = Path(tmpdir) / "uploads"
            app_temp.config["UPLOAD_TEMP"] = str(upload_temp)
            job_id = str(uuid.uuid4())
            job_dir = upload_temp / job_id
            job_dir.mkdir(parents=True)
            (job_dir / "TB_teste.xlsx").write_bytes(b"teste")

            with mock.patch("etl.processar_upload", return_value=(True, [])):
                with app_temp.app_context():
                    resp = client.post(f"/processar/confirmar/{job_id}")
                    data = resp.get_data(as_text=True)
                    resp.close()

            self.assertEqual(resp.status_code, 200)
            self.assertIn("Backup de seguranca criado antes da importacao", data)
            self.assertIn('"done": true, "ok": true', data)
            self.assertNotIn("backup_pre_import", data)
            self.assertNotIn("Erro inesperado ao gravar no banco", data)
            backups = list((db_path.parent / "backups").glob("pre_import_*.db"))
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].with_suffix(".db.json").exists())


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


class RecolhimentosTests(unittest.TestCase):
    def test_schema_cria_tabelas_de_recolhimentos(self):
        with sqlite3.connect(":memory:") as conn:
            recolhimentos_core.ensure_schema(conn)
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'recolhimento%'"
                )
            }

        self.assertIn("recolhimentos", tabelas)
        self.assertIn("recolhimento_agentes", tabelas)

    def test_parse_recolhimentos_kobo_e_legado(self):
        novo = ROOT / "PAGINA_RECOLHIMENTOS" / "RECOLHIMENTO_2026_05_05-21.xlsx"
        legado = ROOT / "PAGINA_RECOLHIMENTOS" / "RECOLHIMENTO_LEGADO.xlsx"
        if not novo.exists() or not legado.exists():
            self.skipTest("Planilhas temporarias de recolhimento nao estao presentes.")

        registros_novos = recolhimentos_core.parse_workbook(novo)
        registros_legados = recolhimentos_core.parse_workbook(legado)

        self.assertGreaterEqual(len(registros_novos), 1)
        self.assertGreaterEqual(len(registros_legados), 1)
        self.assertEqual(registros_novos[0]["localidade"], "Lamenha")
        self.assertIn("Atagil", registros_novos[0]["agentes_texto"])
        self.assertIn("total_materiais", registros_novos[0])
        self.assertIn("total_materiais", registros_legados[0])

    def test_split_agentes_recolhimento_reconhece_legado_sem_separador(self):
        nomes = recolhimentos_core._split_agentes("Adriana Ana Beatriz Atagil Evaldo Henrique Pedro")

        self.assertEqual(
            nomes,
            ["Adriana", "Ana Beatriz", "Atagil", "Evaldo", "Henrique", "Pedro"],
        )


class AmostrasAnimaisTests(unittest.TestCase):
    def test_schema_cria_tabelas_de_amostras_animais(self):
        with sqlite3.connect(":memory:") as conn:
            amostras_animais_core.ensure_schema(conn)
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'amostra%'"
                )
            }

        self.assertIn("amostras_animais", tabelas)
        self.assertIn("amostra_animais_agentes", tabelas)

    def test_parse_amostras_animais_kobo_e_legado(self):
        novo = ROOT / "AMOSTRA_ANIMAIS_NOVA_PAGINA" / "AMOSTRA_ANIMAIS_KOBO.xlsx"
        legado = ROOT / "AMOSTRA_ANIMAIS_NOVA_PAGINA" / "AMOSTRA_ANIMAIS_LEGADO.xlsx"
        if not novo.exists() or not legado.exists():
            self.skipTest("Planilhas temporarias de amostra de animais nao estao presentes.")

        registros_novos = amostras_animais_core.parse_workbook(novo)
        registros_legados = amostras_animais_core.parse_workbook(legado)

        self.assertGreaterEqual(len(registros_novos), 1)
        self.assertGreaterEqual(len(registros_legados), 1)
        self.assertIn("Atagil", registros_novos[0]["agentes_texto"])
        self.assertEqual(registros_novos[0]["tipo_animal"], "Escorpião")
        self.assertIn("quantidade", registros_novos[0])

    def test_split_agentes_amostras_corrige_fernado(self):
        nomes = amostras_animais_core._split_agentes("Adriana Ana Beatriz Fernado Pedro")

        self.assertEqual(nomes, ["Adriana", "Ana Beatriz", "Fernando", "Pedro"])


class BriTests(unittest.TestCase):
    def test_schema_cria_tabelas_de_bri(self):
        with sqlite3.connect(":memory:") as conn:
            bri_core.ensure_schema(conn)
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bri%'"
                )
            }

        self.assertIn("bri_registros", tabelas)
        self.assertIn("bri_agentes", tabelas)

    def test_parse_bri_kobo_e_legado(self):
        novo = ROOT / "BRI_NOVA_PAGINA" / "BRI_KOBO.xlsx"
        legado = ROOT / "BRI_NOVA_PAGINA" / "BRI_LEGADO.xlsx"
        if not novo.exists() or not legado.exists():
            self.skipTest("Planilhas temporarias de BRI nao estao presentes.")

        registros_novos = bri_core.parse_workbook(novo)
        registros_legados = bri_core.parse_workbook(legado)

        self.assertGreaterEqual(len(registros_novos), 1)
        self.assertGreaterEqual(len(registros_legados), 1)
        self.assertEqual(registros_novos[0]["destino_tratamento"], "Ponto Estratégico")
        self.assertEqual(registros_novos[1]["destino_tratamento"], "Ovitrampa")
        self.assertEqual(registros_legados[0]["sispncd"], "0065/2026")
        self.assertIn("quantidade_carga", registros_novos[0])

    def test_bri_de_ponto_estrategico_vincula_por_alias(self):
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)")
            conn.execute("CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
            pe_core.ensure_schema(conn)
            bri_core.ensure_schema(conn)
            pe_core.inserir(conn, {
                "codigo_pe": "PE-0009",
                "nome": "Meio Ambiente",
                "localidade": "Paraíso",
                "quarteirao": 481,
            })
            pe_core.ensure_schema(conn)
            conn.execute(
                """INSERT INTO bri_registros (
                       id_bri, data, destino_tratamento, localidade, id_localidade,
                       quarteirao, local_tratamento, logradouro, processado_em
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    "bri-pe",
                    "2026-06-01",
                    "Ponto Estratégico",
                    "Paraíso",
                    1,
                    129,
                    "Meio Ambiente",
                    "Trav. Rio Cachoeirinha",
                    "agora",
                ),
            )

            resultado = bri_core.vincular_registros_pe_por_alias(conn)
            bri = conn.execute("SELECT codigo_pe FROM bri_registros WHERE id_bri='bri-pe'").fetchone()
            row = conn.execute(
                """SELECT pe.codigo_pe,
                          (SELECT COUNT(*) FROM bri_registros b
                            WHERE b.destino_tratamento='Ponto Estratégico'
                              AND (
                                  b.id_pe=pe.id_pe
                                  OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                              )) AS bri_total
                     FROM pontos_estrategicos pe
                    WHERE pe.codigo_pe='PE-0009'"""
            ).fetchone()

        self.assertEqual(resultado["atualizados"], 1)
        self.assertEqual(bri["codigo_pe"], "PE-0009")
        self.assertEqual(row["bri_total"], 1)


class PontosEstrategicosTests(unittest.TestCase):
    def test_schema_cria_tabela_de_pontos_estrategicos(self):
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)")
            pe_core.ensure_schema(conn)
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='pontos_estrategicos'"
                )
            }

        self.assertIn("pontos_estrategicos", tabelas)

    def test_importa_csv_inicial_com_codigo_sequencial(self):
        csv_path = ROOT / "PONTOS_ESTRATEGICOS.csv"
        if not csv_path.exists():
            self.skipTest("CSV temporario de pontos estrategicos nao esta presente.")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "pe.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)")
            finally:
                conn.close()

            resultado = pe_core.importar_csv_inicial(csv_path, str(db_path))

            self.assertGreaterEqual(resultado["inseridos"], 1)
            conn = sqlite3.connect(db_path)
            try:
                primeiro = conn.execute(
                    "SELECT codigo_pe, nome FROM pontos_estrategicos ORDER BY id_pe LIMIT 1"
                ).fetchone()
                total = conn.execute("SELECT COUNT(*) FROM pontos_estrategicos").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(primeiro[0], "PE-0001")
        self.assertEqual(total, resultado["inseridos"])

    def test_exporta_pontos_estrategicos_filtrados_xlsx_e_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _executar_criar_banco_em(tmpdir)
            pe_core.salvar(str(db_path), {
                "nome": "Ferro Velho Central",
                "localidade": "Centro",
                "quarteirao": 10,
                "logradouro": "Rua A",
                "numero": "123",
                "tipo": "Ferro velho",
                "telefone": "41999990000",
                "situacao": 1,
            })
            pe_core.salvar(str(db_path), {
                "nome": "Borracharia Norte",
                "localidade": "Norte",
                "quarteirao": 20,
                "tipo": "Borracharia",
                "situacao": 1,
            })
            app_temp = endemias_app.create_app({"TESTING": True, "DB_PATH": db_path})
            client = app_temp.test_client()
            _login_client_com_usuario(client, {"id_usuario": 1, "nome": "Administrador", "nivel": "admin"})

            resp_xlsx = client.get("/api/pontos-estrategicos/exportar?localidade=Sede&formato=xlsx")
            resp_pdf = client.get("/api/pontos-estrategicos/exportar?localidade=Sede&formato=pdf")

        self.assertEqual(resp_xlsx.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resp_xlsx.content_type,
        )
        self.assertTrue(resp_xlsx.data.startswith(b"PK"))
        wb = openpyxl.load_workbook(io.BytesIO(resp_xlsx.data))
        ws = wb.active
        valores = [cell.value for cell in ws["B"]]
        self.assertIn("Ferro Velho Central", valores)
        self.assertNotIn("Borracharia Norte", valores)

        self.assertEqual(resp_pdf.status_code, 200)
        html = resp_pdf.data.decode("utf-8")
        self.assertIn("Ferro Velho Central", html)
        self.assertNotIn("Borracharia Norte", html)

    def test_aliases_de_pe_resolvem_logradouros_antigos(self):
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)")
            pe_core.ensure_schema(conn)
            for codigo, nome, localidade in (
                ("PE-0007", "Borracharia Mauricio", "Tranqueira"),
                ("PE-0042", "Cemiterio Prado", "Rosana"),
                ("PE-0043", "Condominio Jersey City - LYX", "Rosana"),
            ):
                pe_core.inserir(conn, {"codigo_pe": codigo, "nome": nome, "localidade": localidade})
            pe_core.ensure_schema(conn)

            self.assertEqual(
                pe_core.resolver_alias_visita(
                    conn,
                    "Borracharia (prox celeste) -  Rodovia Dos Minérios",
                    "Tranqueira",
                )["codigo_pe"],
                "PE-0007",
            )
            self.assertEqual(pe_core.resolver_alias_visita(conn, "CEMITERIO", "Rosana")["codigo_pe"], "PE-0042")
            self.assertEqual(pe_core.resolver_alias_visita(conn, "CONDOMINIO", "Rosana")["codigo_pe"], "PE-0043")
            self.assertEqual(pe_core.resolver_alias_visita(conn, "LYX", "Rosana")["codigo_pe"], "PE-0043")
            self.assertIsNone(pe_core.resolver_alias_visita(conn, "cemitério", "São Venâncio"))

    def test_listagem_de_pe_prioriza_vinculo_direto_da_visita(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _executar_criar_banco_em(tmpdir)
            pe_core.salvar(str(db_path), {
                "codigo_pe": "PE-9001",
                "nome": "PE Principal",
                "localidade": "Centro",
                "quarteirao": 10,
                "situacao": 1,
            })
            pe_core.salvar(str(db_path), {
                "codigo_pe": "PE-9002",
                "nome": "PE Mesmo Quarteirao",
                "localidade": "Centro",
                "quarteirao": 10,
                "situacao": 1,
            })
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                pe_core.ensure_schema(conn)
                pe1 = conn.execute("SELECT id_pe FROM pontos_estrategicos WHERE codigo_pe='PE-9001'").fetchone()["id_pe"]
                conn.execute(
                    """INSERT INTO visitas (
                           id_visita, kobo_uuid, tipo, data, id_localidade, localidade,
                           quarteirao, logradouro, processado_em, id_pe, codigo_pe
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    ("v-pe", "uuid-pe", "PE", "2026-06-01", 1, "Centro", 10, "Alias", "agora", pe1, "PE-9001"),
                )
                conn.commit()
            finally:
                conn.close()

            dados = pe_core.listar(str(db_path), limite=None)["registros"]
            por_codigo = {row["codigo_pe"]: row for row in dados if row["codigo_pe"] in ("PE-9001", "PE-9002")}

        self.assertEqual(por_codigo["PE-9001"]["visitas_pe_total"], 1)
        self.assertEqual(por_codigo["PE-9002"]["visitas_pe_total"], 0)

    def test_vincula_visitas_antigas_de_pe_por_alias(self):
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)")
            conn.execute(
                """CREATE TABLE visitas (
                       id_visita TEXT PRIMARY KEY,
                       tipo TEXT,
                       data TEXT,
                       localidade TEXT,
                       logradouro TEXT
                   )"""
            )
            pe_core.ensure_schema(conn)
            pe_core.inserir(conn, {"codigo_pe": "PE-0007", "nome": "Borracharia Mauricio", "localidade": "Tranqueira"})
            pe_core.ensure_schema(conn)
            conn.execute(
                """INSERT INTO visitas(id_visita, tipo, data, localidade, logradouro)
                   VALUES ('v1', 'PE', '2026-06-01', 'Tranqueira',
                           'Borracharia (prox celeste) -  Rodovia Dos Minérios')"""
            )

            resultado = pe_core.vincular_visitas_existentes_por_alias(conn)
            visita = conn.execute("SELECT codigo_pe FROM visitas WHERE id_visita='v1'").fetchone()

        self.assertEqual(resultado["atualizadas"], 1)
        self.assertEqual(visita["codigo_pe"], "PE-0007")


class SispncdIndiceTests(unittest.TestCase):
    def _criar_planilha_indice(self, path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "indice"
        ws.append(["TIPO", "SISPNCD", "DATA", "LOCALIDADE"])
        ws.append(["PE", "0000/0000", "2026-02-06", "Lamenha"])
        ws.append(["PE", "0006/2006", "2026-01-06", "São João Batista"])
        ws.append(["TBO", "0163/2026", "2026-04-13", "Graziela"])
        wb.save(path)

    def _criar_banco_visitas(self, path):
        conn = sqlite3.connect(path)
        try:
            conn.executescript("""
                CREATE TABLE localidades (
                    id_localidade INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL
                );
                CREATE TABLE visitas (
                    id_visita TEXT PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    data TEXT NOT NULL,
                    localidade TEXT,
                    id_localidade INTEGER,
                    SISPNCD TEXT
                );
                INSERT INTO localidades(id_localidade, nome) VALUES
                    (1, 'Lamenha'),
                    (2, 'São João Batista'),
                    (3, 'Graziela');
                INSERT INTO visitas(id_visita, tipo, data, localidade, id_localidade, SISPNCD) VALUES
                    ('v1', 'PE', '2026-02-06', 'Lamenha', 1, NULL),
                    ('v2', 'PE', '2026-01-06', 'São João Batista', 2, NULL),
                    ('v3', 'TBO', '2026-04-13', 'Graziela', 3, NULL),
                    ('v4', 'TB', '2026-04-13', 'Graziela', 3, NULL);
            """)
            conn.commit()
        finally:
            conn.close()

    def test_indice_corrige_codigo_e_aplica_0000(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "endemias.db"
            xlsx_path = Path(tmpdir) / "INDICE_SISPNCD.xlsx"
            self._criar_banco_visitas(db_path)
            self._criar_planilha_indice(xlsx_path)

            previa = sispncd_indice_core.previsualizar(str(db_path), str(xlsx_path))
            resultado = sispncd_indice_core.aplicar(str(db_path), str(xlsx_path))

            conn = sqlite3.connect(db_path)
            try:
                valores = dict(conn.execute("SELECT id_visita, SISPNCD FROM visitas").fetchall())
            finally:
                conn.close()

        self.assertEqual(previa["visitas_atualizaveis"], 3)
        self.assertEqual(previa["correcoes"][0]["de"], "0006/2006")
        self.assertEqual(previa["correcoes"][0]["para"], "0006/2026")
        self.assertEqual(resultado["atualizados"], 3)
        self.assertEqual(valores["v1"], "0000/0000")
        self.assertEqual(valores["v2"], "0006/2026")
        self.assertEqual(valores["v3"], "0163/2026")
        self.assertIsNone(valores["v4"])


class ProtectedRouteTests(unittest.TestCase):
    def test_home_sem_login_redireciona_para_login(self):
        endemias_app.app.config["TESTING"] = True
        with endemias_app.app.test_client() as client:
            resp = client.get("/")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_sessao_com_usuario_inexistente_redireciona_para_login(self):
        endemias_app.app.config["TESTING"] = True
        with endemias_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["uid"] = 999999999
                sess["nome"] = "Usuario removido"
                sess["nivel"] = "admin"

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

    def test_csp_pode_remover_inline_quando_configurada(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
            "CSP_ALLOW_INLINE": False,
        })
        with app_temp.test_client() as client:
            resp = client.get("/login")

        csp = resp.headers["Content-Security-Policy-Report-Only"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

    def test_cookie_secure_pode_ser_ativado_por_config(self):
        app_temp = endemias_app.create_app({
            "TESTING": True,
            "DB_PATH": endemias_app.DB_PATH,
            "SESSION_COOKIE_SECURE": True,
        })

        self.assertTrue(app_temp.config["SESSION_COOKIE_SECURE"])

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

    def test_visualizador_nao_gera_consolidados(self):
        client = _client_logado("visualizador")
        original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
        endemias_app.app.config["WTF_CSRF_ENABLED"] = False
        try:
            resp = client.post("/saida/gerar-consolidados", json={"tipo": "PE"})
        finally:
            endemias_app.app.config["WTF_CSRF_ENABLED"] = original

        self.assertEqual(resp.status_code, 403)

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
            "/recolhimentos",
            "/amostras-animais",
            "/bri",
            "/notificacoes",
            "/mapa",
            "/pontos-estrategicos",
            "/agenda",
            "/admin/agentes",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/html", resp.content_type)

    def test_dashboard_integrado_exibe_esporotricose(self):
        client = _client_logado()
        resp = client.get("/dashboard")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Dashboard Integrado", html)
        self.assertIn("Esporotricose", html)
        self.assertIn("Pendências de Pontos Estratégicos", html)
        self.assertIn("chComparativo", html)
        self.assertIn("chAtividade", html)
        self.assertIn("chEspEvolucao", html)

    def test_relatorio_agente_exibe_esporotricose_e_aviso_de_privacidade(self):
        client = _client_logado()
        resp = client.get("/relatorio-agente")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Central do agente", html)
        self.assertIn("agent-workspace", html)
        self.assertIn("agente_busca", html)
        self.assertIn("function escapeHtml", html)
        self.assertIn("Agente de Combate a Endemias", html)
        self.assertIn("Produção operacional integrada", html)
        self.assertIn("Relatório do setor", html)
        self.assertIn("gerarPDFSetor", html)
        self.assertIn("Produção de esporotricose", html)
        self.assertIn("médias agregadas dos demais agentes", html)
        self.assertNotIn("pend. SisPNCD", html)

    def test_pdf_relatorio_agente_inclui_esporotricose_sem_identificar_demais(self):
        client = _client_logado()
        agente = _agente_relatorio_teste()
        resp = client.get(
            "/relatorio-agente/pdf",
            query_string={"agente": agente, "d_ini": "2020-01-01", "d_fim": "2030-12-31"},
        )

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Agente de Combate a Endemias", html)
        self.assertIn("Produção operacional integrada", html)
        self.assertIn("Rua Bertolina Kendrik de Oliveira, 681", html)
        self.assertIn("break-inside:avoid", html)
        self.assertIn("page-break-inside:avoid", html)
        self.assertGreaterEqual(html.count('class="bloco-relatorio"'), 6)
        self.assertIn("Produção de esporotricose", html)
        self.assertIn("Comparação agregada de esporotricose", html)
        self.assertIn("Outros agentes não são listados nem identificados", html)
        self.assertNotIn("SisPNCD", html)

    def test_pdf_relatorio_setor_inclui_producao_geral_e_por_agente(self):
        client = _client_logado()
        resp = client.get(
            "/relatorio-agente/setor/pdf",
            query_string={"d_ini": "2020-01-01", "d_fim": "2030-12-31"},
        )

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Relatorio Geral do Setor", html)
        self.assertIn("Resumo do setor", html)
        self.assertIn("Producao por frente de trabalho", html)
        self.assertIn("Ranking geral de producao por agente", html)
        self.assertIn("Producao individual por agente", html)
        self.assertIn("Visitas vetoriais: situacao e tipo de trabalho", html)
        self.assertIn("Tempo das visitas", html)
        self.assertIn("Depositos e laboratorio", html)
        self.assertIn("Graficos analiticos", html)
        self.assertIn("chDuracaoTipo", html)
        self.assertIn("chAgentes", html)
        self.assertIn("Vetores", html)
        self.assertIn("Esporotricose", html)
        self.assertIn("BRI", html)
        self.assertIn("bloco-relatorio", html)
        self.assertNotIn("SisPNCD", html)

    def test_controle_pessoal_exibe_cadastro_e_historico(self):
        client = _client_logado("admin")
        resp = client.get("/admin/agentes")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Controle de Pessoal", html)
        self.assertIn("Novo agente", html)
        self.assertIn("Historico de trabalho", html)
        self.assertIn("/api/agentes/", html)

    def test_central_do_sistema_admin_responde_200(self):
        client = _client_logado("admin")
        resp = client.get("/admin/sistema")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Central do Sistema", html)
        self.assertIn("Saude do ambiente", html)
        self.assertIn("Backups gerenciados", html)
        self.assertIn("/admin/sistema/backups/criar", html)
        self.assertIn("/admin/sistema/backups/excluir", html)
        self.assertIn('id="sidebarToggle"', html)
        self.assertIn("data-confirm=", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("onsubmit=", html)

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
        html = resp.data.decode("utf-8")
        self.assertIn("Ultimas importacoes", html)
        self.assertIn("LARVAS_ Resultados de Laborat\u00f3rio", html)
        self.assertIn("data-gerar-consolidado", html)
        self.assertIn('id="processar-work-types"', html)
        self.assertIn('src="/static/js/processar.js"', html)
        self.assertNotIn("configurarAcoesProcessamento()", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("onchange=", html)
        proibidos = (
            "\u00c3\u00a7",
            "\u00c3\u00a3",
            "\u00c3\u00a1",
            "\u00c3\u00a9",
            "\u00c3\u00b3",
            "\u00c3\u00ba",
            "\u00c3\u00ad",
            "\u00c3\u00aa",
            "\u00c3\u2021",
            "\u00c3\u0192",
            "\u00e2\u0153",
            "\u00e2\u2020",
            "\u00e2\u20ac\u00a6",
            "\u00f0\u0178",
        )
        self.assertFalse(any(c in html for c in proibidos), html[:500])

        js_resp = client.get("/static/js/processar.js")
        js = js_resp.data.decode("utf-8")
        js_resp.close()
        self.assertFalse(any(c in js for c in proibidos), js[:500])

    def test_assets_compartilhados_respondem_200(self):
        client = _client_logado()
        for rota in (
            "/static/css/app.css",
            "/static/js/app.js",
            "/static/js/processar.js",
            "/static/js/agenda.js",
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
        self.assertNotIn("style.setProperty('background-color', bg, 'important')", html)
        js_resp = client.get("/static/js/agenda.js")
        js = js_resp.data.decode("utf-8")
        js_resp.close()
        self.assertIn("style.setProperty('background-color', bg, 'important')", js)
        self.assertIn('id="btn-agenda-novo"', html)
        self.assertIn('id="agenda-config"', html)
        self.assertIn('src="/static/js/agenda.js"', html)
        self.assertNotIn("addEventListener('click', abrirModalNovo)", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("onchange=", html)


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

    def test_api_dashboard_inclui_esporotricose_e_comparativo(self):
        client = _client_logado()
        resp = client.get("/api/dashboard")

        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertIn("comparativo_mensal", dados)
        self.assertIn("esporotricose", dados)
        self.assertIn("pontos_estrategicos", dados)
        self.assertIn("producao_operacional", dados)
        self.assertIn("resumo", dados["esporotricose"])
        self.assertIn("dashboard", dados["esporotricose"])
        self.assertIn("evolucao", dados["esporotricose"]["dashboard"])
        self.assertIn("totais", dados["pontos_estrategicos"])
        self.assertIn("por_atividade", dados["producao_operacional"])

    def test_api_producao_operacional_retorna_central_integrada(self):
        client = _client_logado()
        resp = client.get("/api/producao-operacional?d_ini=2026-05-01&d_fim=2026-05-31")

        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertIn("totais", dados)
        self.assertIn("por_atividade", dados)
        self.assertIn("por_localidade", dados)
        self.assertIn("por_agente", dados)
        codigos = {item["codigo"] for item in dados["por_atividade"]}
        self.assertIn("VETORES", codigos)
        self.assertIn("ESPOROTRICOSE", codigos)
        self.assertIn("RECOLHIMENTO", codigos)
        self.assertIn("AMOSTRA_ANIMAIS", codigos)
        self.assertIn("BRI", codigos)

    def test_api_relatorio_agente_inclui_esporotricose_sem_expor_outros_agentes(self):
        client = _client_logado()
        agente = _agente_relatorio_teste()
        resp = client.get(
            "/api/relatorio-agente",
            query_string={"agente": agente, "d_ini": "2020-01-01", "d_fim": "2030-12-31"},
        )

        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertIn("esporotricose", dados)
        self.assertIn("producao_operacional", dados)
        self.assertIn("por_atividade", dados["producao_operacional"])
        self.assertIn("totais", dados["esporotricose"])
        self.assertIn("animais", dados["esporotricose"])
        self.assertIn("comparacao_esporotricose", dados)
        self.assertNotIn("recentes", dados["esporotricose"])
        self.assertNotIn(
            "sispncd",
            json.dumps(dados["producao_operacional"], ensure_ascii=False).lower(),
        )

        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            outros = [
                row[0]
                for row in conn.execute(
                    "SELECT nome FROM agentes WHERE nome <> ? ORDER BY nome LIMIT 5",
                    (agente,),
                )
            ]
        finally:
            conn.close()
        payload = json.dumps(dados, ensure_ascii=False)
        for outro in outros:
            self.assertNotIn(outro, payload)

    def test_api_historico_agente_retorna_frentes_operacionais(self):
        client = _client_logado("admin")
        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            row = conn.execute(
                """SELECT a.id_agente
                   FROM agentes a
                   LEFT JOIN visita_agentes va ON va.id_agente=a.id_agente
                   LEFT JOIN esporotricose_visita_agentes ea ON ea.id_agente=a.id_agente
                   WHERE va.id_agente IS NOT NULL OR ea.id_agente IS NOT NULL
                   LIMIT 1"""
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

        resp = client.get(
            f"/api/agentes/{row[0]}/historico",
            query_string={"d_ini": "2020-01-01", "d_fim": "2030-12-31"},
        )

        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertIn("agente", dados)
        self.assertIn("dias", dados)
        self.assertIn("por_origem", dados)
        self.assertGreaterEqual(dados["total"], 1)

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

    def test_pagina_recolhimentos_exibe_controles_principais(self):
        client = _client_logado()
        resp = client.get("/recolhimentos")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Recolhimento de Materiais", html)
        self.assertIn("rec-registros", html)
        self.assertIn("rec-body", html)

    def test_api_recolhimentos_retorna_json(self):
        client = _client_logado()
        resp = client.get("/api/recolhimentos?d_ini=2099-01-01&d_fim=2099-01-02")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("totais", dados)
        self.assertIn("por_localidade", dados)

    def test_pagina_amostras_animais_exibe_controles_principais(self):
        client = _client_logado()
        resp = client.get("/amostras-animais")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Amostra de Animais", html)
        self.assertIn("am-registros", html)
        self.assertIn("am-body", html)

    def test_api_amostras_animais_retorna_json(self):
        client = _client_logado()
        resp = client.get("/api/amostras-animais?d_ini=2099-01-01&d_fim=2099-01-02")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("totais", dados)
        self.assertIn("por_tipo", dados)
        self.assertIn("por_localidade", dados)

    def test_pagina_bri_exibe_controles_principais(self):
        client = _client_logado()
        resp = client.get("/bri")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Borrifamento Residual Intradomiciliar", html)
        self.assertIn("bri-registros", html)
        self.assertIn("bri-body", html)

    def test_api_bri_retorna_json(self):
        client = _client_logado()
        resp = client.get("/api/bri?d_ini=2099-01-01&d_fim=2099-01-02")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("totais", dados)
        self.assertIn("por_destino", dados)
        self.assertIn("por_localidade", dados)
        self.assertIn("vinculados_pe", dados["totais"])
        self.assertIn("ambiguos_pe", dados["totais"])

    def test_pagina_pontos_estrategicos_exibe_controles_principais(self):
        client = _client_logado()
        resp = client.get("/pontos-estrategicos")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Pontos Estratégicos", html)
        self.assertIn("pe-total", html)
        self.assertIn("pe-body", html)

    def test_api_pontos_estrategicos_retorna_json(self):
        client = _client_logado()
        resp = client.get("/api/pontos-estrategicos")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("totais", dados)
        self.assertIn("registros", dados)

    def test_api_pontos_estrategicos_filtra_pendencias(self):
        client = _client_logado()
        resp = client.get("/api/pontos-estrategicos?pendencias=1")
        dados = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("totais", dados)
        for registro in dados["registros"]:
            self.assertTrue(registro.get("visita_atrasada") or registro.get("pendencias_cadastro"))

    def test_api_pontos_estrategicos_situacao_invalida_retorna_400(self):
        client = _client_logado("admin")
        original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
        endemias_app.app.config["WTF_CSRF_ENABLED"] = False
        try:
            resp = client.post("/api/pontos-estrategicos/1/situacao", json={"situacao": "abc"})
        finally:
            endemias_app.app.config["WTF_CSRF_ENABLED"] = original

        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.is_json)

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
                if esperado_salvar == 0:
                    self.skipTest("Banco atual nao possui pendencias TBO para salvar status de conta ovos.")

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
                        WHERE SISPNCD IS NULL OR TRIM(SISPNCD)=''
                        ORDER BY data DESC
                        LIMIT 1"""
                ).fetchone()
                conn.close()
                self.assertIsNotNone(row)
                ano, semana = sispncd_core.epidemiological_week_for_date(row[0])

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
                    pendentes_restantes_no_codigo = conn.execute(
                        "SELECT COUNT(*) FROM visitas WHERE SISPNCD IS NULL OR TRIM(SISPNCD)=''"
                    ).fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(gravados, atualizados)
                self.assertGreaterEqual(pendentes_restantes_no_codigo, 0)
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
        self.assertGreaterEqual(dados["sispncd"]["total"], 0)
        for grupo in dados["sispncd"]["grupos"]:
            self.assertIn("ano", grupo)
            self.assertIn("semana", grupo)
            self.assertIn("id_localidade", grupo)
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

    def test_sispncd_0000_nao_conta_como_pendente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sispncd.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript("""
                    CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
                    CREATE TABLE visitas (
                        id_visita TEXT PRIMARY KEY,
                        tipo TEXT,
                        data TEXT,
                        quarteirao INTEGER,
                        localidade TEXT,
                        id_localidade INTEGER,
                        SISPNCD TEXT,
                        CONTAOVOS_STATUS INTEGER
                    );
                    INSERT INTO localidades(id_localidade, nome) VALUES (1, 'Centro');
                    INSERT INTO visitas VALUES
                        ('a', 'PE', '2026-05-03', 1, 'Centro', 1, '0000/0000', NULL),
                        ('b', 'PE', '2026-05-04', 1, 'Centro', 1, NULL, NULL),
                        ('c', 'PE', '2026-05-05', 1, 'Centro', 1, '', NULL);
                """)
                conn.commit()
            finally:
                conn.close()

            pendencias = sispncd_core.pendencias_envio(str(db_path))
            resultado = sispncd_core.salvar_sispncd(str(db_path), 2026, 18, ["PE"], "0123/2026", id_localidade=1)

            conn = sqlite3.connect(db_path)
            try:
                valores = dict(conn.execute("SELECT id_visita, SISPNCD FROM visitas").fetchall())
            finally:
                conn.close()

        self.assertEqual(pendencias["sispncd"]["total"], 2)
        self.assertEqual(resultado["atualizados"], 2)
        self.assertEqual(valores["a"], "0000/0000")
        self.assertEqual(valores["b"], "0123/2026")
        self.assertEqual(valores["c"], "0123/2026")

    def test_sispncd_usa_semana_epidemiologica_domingo_sabado(self):
        self.assertEqual(
            sispncd_core.epidemiological_week_range(2026, 1),
            ("2026-01-04", "2026-01-10"),
        )
        self.assertEqual(
            sispncd_core.epidemiological_week_range(2026, 18),
            ("2026-05-03", "2026-05-09"),
        )
        self.assertEqual(
            sispncd_core.epidemiological_week_range(2026, 52),
            ("2026-12-27", "2027-01-02"),
        )
        self.assertEqual(
            sispncd_core.epidemiological_week_for_date("2026-01-03"),
            (2025, 53),
        )
        self.assertEqual(
            sispncd_core.epidemiological_week_for_date("2026-01-04"),
            (2026, 1),
        )

    def test_sispncd_inclui_bri_pendente_e_salva_codigo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sispncd_bri.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.executescript("""
                    CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
                    CREATE TABLE visitas (
                        id_visita TEXT PRIMARY KEY,
                        tipo TEXT,
                        data TEXT,
                        quarteirao INTEGER,
                        localidade TEXT,
                        id_localidade INTEGER,
                        tipo_imovel TEXT,
                        visita TEXT,
                        SISPNCD TEXT,
                        CONTAOVOS_STATUS INTEGER
                    );
                    CREATE TABLE depositos_inspecionados (
                        id_visita TEXT,
                        tipo_deposito TEXT,
                        inspecionado INTEGER,
                        eliminado INTEGER,
                        tratado INTEGER,
                        qtd_carga REAL
                    );
                    CREATE TABLE tratamentos (
                        id INTEGER PRIMARY KEY,
                        id_visita TEXT,
                        tipo TEXT,
                        quantidade_carga REAL
                    );
                    CREATE TABLE coletas (
                        id_coleta TEXT PRIMARY KEY,
                        id_visita TEXT,
                        tipo_deposito TEXT
                    );
                    CREATE TABLE resultados_laboratorio (
                        id_coleta TEXT,
                        aegypt_larvas INTEGER,
                        aegypt_pupas INTEGER,
                        aegypt_exuvias INTEGER,
                        aegypt_adulto INTEGER,
                        albopictus_larvas INTEGER,
                        albopictus_pupas INTEGER,
                        albopictus_exuvias INTEGER,
                        albopictus_adulto INTEGER,
                        outra_larvas INTEGER,
                        outra_pupas INTEGER,
                        outra_exuvias INTEGER,
                        outra_adulto INTEGER
                    );
                    CREATE TABLE visita_agentes (
                        id_visita TEXT,
                        id_agente INTEGER
                    );
                    INSERT INTO localidades(id_localidade, nome) VALUES (1, 'Centro');
                """)
                bri_core.ensure_schema(conn)
                conn.executescript("""
                    INSERT INTO bri_registros (
                        id_bri, sispncd, data, id_localidade, localidade, destino_tratamento,
                        quantidade_carga, quantidade_carga_extra, origem_estrutura, processado_em
                    ) VALUES
                        ('bri1', NULL, '2026-05-24', 1, 'Centro', 'Ovitrampa', 10, 0, 'nova', '2026-05-24T08:00:00'),
                        ('bri2', '', '2026-05-25', 1, 'Centro', 'Ponto Estratégico', 20, 5, 'nova', '2026-05-25T08:00:00'),
                        ('bri3', '0000/0000', '2026-05-26', 1, 'Centro', 'Outro', 30, 0, 'nova', '2026-05-26T08:00:00');
                """)
                conn.commit()
            finally:
                conn.close()

            pendencias = sispncd_core.pendencias_envio(str(db_path))
            consulta = sispncd_core.sispncd(str(db_path), 2026, 21, ["BRI"], id_localidade=1)
            resultado = sispncd_core.salvar_sispncd(str(db_path), 2026, 21, ["BRI"], "0456/2026", id_localidade=1)

            conn = sqlite3.connect(db_path)
            try:
                valores = dict(conn.execute("SELECT id_bri, sispncd FROM bri_registros").fetchall())
            finally:
                conn.close()

        grupos_bri = [g for g in pendencias["sispncd"]["grupos"] if g["tipo"] == "BRI"]
        self.assertEqual(pendencias["sispncd"]["total"], 2)
        self.assertEqual(grupos_bri[0]["semana"], 21)
        self.assertEqual(consulta["dados_gerais"]["bri"]["registros"], 3)
        self.assertEqual(consulta["dados_gerais"]["bri"]["pendentes_sispncd"], 2)
        self.assertEqual(resultado["atualizados"], 2)
        self.assertEqual(resultado["bri_atualizados"], 2)
        self.assertEqual(valores["bri1"], "0456/2026")
        self.assertEqual(valores["bri2"], "0456/2026")
        self.assertEqual(valores["bri3"], "0000/0000")

    def test_conta_ovos_pendencias_sao_clicaveis_para_filtrar(self):
        client = _client_logado()
        resp = client.get("/conta-ovos-sispncd")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("selecionarPendenciaContaOvos", html)
        self.assertIn("selecionarPendenciaSisPNCD", html)
        self.assertIn("data-localidade-id", html)
        self.assertIn("sis-bri", html)
        self.assertIn("await buscarContaOvos()", html)
        self.assertIn("await buscarSisPNCD()", html)

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
            self.assertIn("esporo_visitas", primeiro)
            self.assertIn("esporo_animais", primeiro)
            self.assertIn("esporo_feridas", primeiro)
            self.assertIn("pes_ativos", primeiro)
            self.assertIn("pes_atrasados", primeiro)

    def test_mapa_exibe_camadas_de_esporotricose(self):
        client = _client_logado()
        resp = client.get("/mapa")

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn('data-modo="esporotricose"', html)
        self.assertIn('data-modo="pes"', html)
        self.assertIn('data-modo="atencao"', html)
        self.assertIn("kpi-esporo-visitas", html)
        self.assertIn("kpi-pes", html)
        self.assertIn("kpi-esporo-feridas", html)

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
                "/saida/consolidados/status",
                "/saida/gerar-consolidados",
                "/saida/download/<tipo>",
            }
        }

        self.assertEqual(endpoints["/api/visitas/exportar"], "exportacoes.exportar_visitas")
        self.assertEqual(endpoints["/api/notificacoes/exportar"], "exportacoes.exportar_notificacoes")
        self.assertEqual(endpoints["/api/laboratorio/exportar"], "exportacoes.exportar_laboratorio")
        self.assertEqual(endpoints["/saida/consolidados/status"], "exportacoes.consolidados_status")
        self.assertEqual(endpoints["/saida/gerar-consolidados"], "exportacoes.gerar_consolidados")
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

    def test_exportacao_xlsx_escapa_formulas(self):
        rows = [{"campo": "=HYPERLINK(\"http://exemplo\")"}]
        with endemias_app.app.test_request_context("/"):
            from blueprints.exportacoes import _gerar_xlsx

            resposta = _gerar_xlsx(["Campo"], rows, "teste")
            resposta.direct_passthrough = False
            data = resposta.get_data()

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        try:
            self.assertEqual(wb.active["A2"].value, "'=HYPERLINK(\"http://exemplo\")")
        finally:
            wb.close()

    def test_status_consolidados_retorna_tipos(self):
        client = _client_logado()
        resp = client.get("/saida/consolidados/status")
        data = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertIn("tipos", data)
        self.assertEqual({item["tipo"] for item in data["tipos"]}, set(work_types.WORK_TYPE_CODES))

    def test_gerar_consolidados_chama_gerador_sob_demanda(self):
        client = _client_logado("admin")
        csrf_original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
        endemias_app.app.config["WTF_CSRF_ENABLED"] = False
        try:
            with mock.patch("gerar_consolidado.gerar_todos", return_value=[
                {"tipo": "PE", "caminho": "saida/PE_consolidado.xlsx", "visitas": 1, "coletas": 2}
            ]) as gerar:
                resp = client.post("/saida/gerar-consolidados", json={"tipo": "PE"})
        finally:
            endemias_app.app.config["WTF_CSRF_ENABLED"] = csrf_original

        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        gerar.assert_called_once()
        self.assertEqual(gerar.call_args.kwargs["tipos"], ["PE"])

    def test_gerador_consolidado_cria_abas_visitas_e_coletas(self):
        import gerar_consolidado

        with tempfile.TemporaryDirectory() as tmpdir:
            conn = sqlite3.connect(endemias_app.DB_PATH)
            try:
                cur = conn.cursor()
                caminho, visitas, coletas = gerar_consolidado.gerar_xlsx_tipo(cur, "PE", tmpdir)
            finally:
                conn.close()

            if caminho is None:
                self.skipTest("Banco de teste sem dados PE para consolidado.")

            wb = openpyxl.load_workbook(caminho, read_only=True)
            try:
                self.assertIn("Visitas", wb.sheetnames)
                self.assertIn("Coletas", wb.sheetnames)
                self.assertGreaterEqual(visitas, 1)
                self.assertGreaterEqual(coletas, 1)
            finally:
                wb.close()

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

    def test_api_agenda_lembrete_invalido_retorna_400(self):
        client = _client_logado("admin")
        original = endemias_app.app.config.get("WTF_CSRF_ENABLED", True)
        endemias_app.app.config["WTF_CSRF_ENABLED"] = False
        try:
            resp = client.post(
                "/api/agenda/eventos",
                json={"titulo": "Teste", "data_inicio": "2026-06-01", "lembrete_min": "abc"},
            )
        finally:
            endemias_app.app.config["WTF_CSRF_ENABLED"] = original

        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.is_json)


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
