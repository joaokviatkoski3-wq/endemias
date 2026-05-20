import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
import etl
from app_core import modules as modules_core
from app_core import sispncd as sispncd_core
from app_core import version as version_core
from app_core import work_types


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


class UploadValidationTests(unittest.TestCase):
    def test_aceita_xlsx_com_assinatura_zip(self):
        arquivo = FileStorage(
            stream=io.BytesIO(b"PK\x03\x04conteudo"),
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

    def test_rejeita_extensao_diferente(self):
        arquivo = FileStorage(
            stream=io.BytesIO(b"PK\x03\x04conteudo"),
            filename="TB_exemplo.csv",
        )

        valido, nome, motivo = endemias_app._validar_arquivo_xlsx(arquivo)

        self.assertFalse(valido)
        self.assertEqual(nome, "")
        self.assertIn("Extens", motivo)


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


class ProtectedRouteTests(unittest.TestCase):
    def test_home_sem_login_redireciona_para_login(self):
        endemias_app.app.config["TESTING"] = True
        with endemias_app.app.test_client() as client:
            resp = client.get("/")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


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

    def test_processar_exibe_historico_de_importacoes(self):
        client = _client_logado("admin")
        resp = client.get("/processar")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Ultimas importacoes", resp.data)

    def test_assets_compartilhados_respondem_200(self):
        client = _client_logado()
        for rota in ("/static/css/app.css", "/static/js/app.js"):
            with self.subTest(rota=rota):
                resp = client.get(rota)
                try:
                    self.assertEqual(resp.status_code, 200)
                finally:
                    resp.close()

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


class MainApisSmokeTests(unittest.TestCase):
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
            "/admin/usuarios",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                resp = client.get(rota)
                self.assertEqual(resp.status_code, 403)

    def test_admin_acessa_areas_admin(self):
        client = _client_logado("admin")
        rotas = [
            "/processar",
            "/admin/usuarios",
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
