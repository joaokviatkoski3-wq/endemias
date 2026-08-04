import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error

from app_core import contaovos_client
from app_core import contaovos_credencial
from app_core import contaovos_health
from app_core import contaovos_integracao
from app_core import diagnostico
from app_core import postgresql_schema_compare
from app_core import schema_metadata
from app_core import sqlite_inventory
from scripts import verificar_contaovos


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    status = 200


def _http_error(code):
    return error.HTTPError(
        "https://contaovos.com/en-us/api/lastcounting?[REMOVIDO]",
        code,
        "erro",
        {},
        None,
    )


class ContaOvosClientTests(unittest.TestCase):
    def test_consulta_publica_de_ovitrampas_filtra_municipio_sem_chave(self):
        seen = {}

        def opener(req, timeout):
            seen["url"] = req.full_url
            seen["method"] = req.get_method()
            return _Response([{"ovitrap_group_id": "97"}])

        rows = contaovos_client.public_ovitraps_page(page=2, opener=opener)
        self.assertEqual([{"ovitrap_group_id": "97"}], rows)
        self.assertEqual("GET", seen["method"])
        self.assertIn("getmunicipalityovitrapspublic", seen["url"])
        self.assertIn("municipality=Almirante+Tamandar", seen["url"])
        self.assertIn("page=2", seen["url"])
        self.assertNotIn("key=", seen["url"])

    def test_post_unitario_exige_autorizacao_e_usa_formulario(self):
        payload = {
            "ovitrap_group_id": "97",
            "ovitrap_lat": -25.1,
            "ovitrap_lng": -49.2,
            "date": "2026-08-02",
            "counting_observation_id": 6,
            "counting_observation": "",
            "counting_eggs": 7,
        }
        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.post_counting("segredo", payload)
        self.assertEqual("write_not_authorized", ctx.exception.kind)

        seen = {}

        def opener(req, timeout):
            seen["method"] = req.get_method()
            seen["url"] = req.full_url
            seen["body"] = req.data.decode("utf-8")
            return _Response({"ok": True})

        result = contaovos_client.post_counting(
            "segredo-teste",
            payload,
            allow_remote_write=True,
            opener=opener,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual("POST", seen["method"])
        self.assertIn("key=segredo-teste", seen["url"])
        self.assertIn("counting_observation=", seen["body"])
        self.assertIn("counting_eggs=7", seen["body"])

    def test_post_nao_repete_erro_e_bloqueia_rede_real_na_suite(self):
        payload = {field: "1" for field in (
            "ovitrap_group_id", "ovitrap_lat", "ovitrap_lng", "date",
            "counting_observation_id", "counting_observation", "counting_eggs",
        )}
        attempts = []

        def opener(req, timeout):
            attempts.append(1)
            raise _http_error(500)

        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.post_counting(
                "segredo", payload, allow_remote_write=True, opener=opener
            )
        self.assertEqual(1, len(attempts))
        self.assertTrue(ctx.exception.outcome_uncertain)
        with self.assertRaises(contaovos_client.ContaOvosError) as blocked:
            contaovos_client.post_counting(
                "nao-usar", payload, allow_remote_write=True
            )
        self.assertEqual("test_network_blocked", blocked.exception.kind)

    def test_consulta_privada_usa_get_query_string_e_formato_lista(self):
        seen = {}

        def opener(req, timeout):
            seen["url"] = req.full_url
            seen["method"] = req.get_method()
            seen["timeout"] = timeout
            return _Response([{"counting_id": 1}])

        rows = contaovos_client.private_counts_page(
            "segredo-teste", opener=opener, sleep=lambda _: None
        )

        self.assertEqual([{"counting_id": 1}], rows)
        self.assertEqual("GET", seen["method"])
        self.assertIn("key=segredo-teste", seen["url"])
        self.assertIn("page=1", seen["url"])
        self.assertEqual(60, seen["timeout"])

    def test_suite_bloqueia_rede_real(self):
        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.private_counts_page("nao-usar")
        self.assertEqual("test_network_blocked", ctx.exception.kind)

    def test_http_500_repete_com_teto(self):
        attempts = []
        waits = []

        def opener(req, timeout):
            attempts.append(req.full_url)
            raise _http_error(500)

        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.private_counts_page(
                "segredo",
                opener=opener,
                sleep=waits.append,
                max_attempts=3,
            )
        self.assertEqual(3, len(attempts))
        self.assertEqual([1, 2], waits)
        self.assertTrue(ctx.exception.retriable)

    def test_http_404_nao_repete_e_nao_expoe_chave(self):
        attempts = []

        def opener(req, timeout):
            attempts.append(1)
            raise _http_error(404)

        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.private_counts_page(
                "segredo-que-nao-pode-vazar", opener=opener, sleep=lambda _: None
            )
        self.assertEqual(1, len(attempts))
        self.assertNotIn("segredo", str(ctx.exception))
        self.assertEqual(404, ctx.exception.status_code)
        self.assertFalse(ctx.exception.retriable)

    def test_erros_de_dados_e_escopo_nao_repetem(self):
        for status_code in (400, 403, 409):
            with self.subTest(status_code=status_code):
                attempts = []

                def opener(req, timeout):
                    attempts.append(1)
                    raise _http_error(status_code)

                with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
                    contaovos_client.private_counts_page(
                        "segredo", opener=opener, sleep=lambda _: None
                    )
                self.assertEqual(1, len(attempts))
                self.assertEqual(status_code, ctx.exception.status_code)
                self.assertFalse(ctx.exception.retriable)

    def test_http_200_string_nao_e_colecao(self):
        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.private_counts_page(
                "segredo",
                opener=lambda req, timeout: _Response("Maximum pagination is 100"),
            )
        self.assertEqual("unexpected_payload", ctx.exception.kind)

    def test_validacao_confirma_municipio_e_formato_nao_documentado(self):
        rows = [
            {
                "municipality": "Almirante Tamandare",
                "municipality_code": "4100400",
                "state_code": "PR",
            }
        ]
        result = contaovos_client.validate_private_access(
            "a" * 40,
            opener=lambda req, timeout: _Response(rows),
        )
        self.assertTrue(result["ok"])
        self.assertEqual("accepted_non_documented_format", result["credential_format"])

    def test_validacao_recusa_escopo_divergente(self):
        rows = [
            {
                "municipality": "Outro municipio",
                "municipality_code": "9999999",
                "state_code": "PR",
            }
        ]
        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.validate_private_access(
                "a" * 45,
                opener=lambda req, timeout: _Response(rows),
            )
        self.assertEqual("scope_mismatch", ctx.exception.kind)

    def test_sanitizador_remove_chave_explicita_e_query_string(self):
        key = "valor-secreto"
        text = f"falha em https://exemplo/?key={key}&page=1: {key}"
        safe = contaovos_client.sanitize_message(text, key)
        self.assertNotIn(key, safe)
        self.assertIn("key=[CHAVE_REMOVIDA]", safe)


class ContaOvosCredentialAndHealthTests(unittest.TestCase):
    def test_credencial_e_status_sao_lidos_sem_expor_valor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            key_path = base / "contaovos.key"
            status_path = base / "status.json"
            key_path.write_text("segredo-local", encoding="utf-8")
            env = {
                "ENDEMIAS_CONTAOVOS_KEY_FILE": str(key_path),
                "ENDEMIAS_CONTAOVOS_STATUS_FILE": str(status_path),
            }
            self.assertEqual("segredo-local", contaovos_credencial.read_key(env))
            contaovos_health.write_status(
                {
                    "ok": True,
                    "page_items": 2,
                    "scopes": [{"municipality_code": "4100400"}],
                    "credential_format": "accepted_non_documented_format",
                    "ignored": "segredo-local",
                },
                env,
            )
            health = contaovos_health.read_status(env)
            self.assertTrue(health["configured"])
            self.assertTrue(health["verified"])
            self.assertTrue(health["ok"])
            self.assertNotIn("ignored", health)
            self.assertNotIn("segredo-local", status_path.read_text(encoding="utf-8"))

    def test_credencial_ausente_retorna_estado_publico(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "ENDEMIAS_CONTAOVOS_KEY_FILE": str(Path(tmpdir) / "ausente.key"),
                "ENDEMIAS_CONTAOVOS_STATUS_FILE": str(Path(tmpdir) / "ausente.json"),
            }
            health = contaovos_health.read_status(env)
            self.assertFalse(health["configured"])
            self.assertFalse(health["verified"])

    def test_diagnostico_distingue_nao_configurado_pendente_e_validado(self):
        cases = (
            ({"configured": False}, "info"),
            ({"configured": True, "verified": False}, "aviso"),
            (
                {
                    "configured": True,
                    "verified": True,
                    "ok": True,
                    "checked_at": "2026-08-03T12:00:00",
                    "credential_format": "documented",
                    "scopes": [{"municipality": "Almirante Tamandare"}],
                },
                "ok",
            ),
        )
        for status, expected_level in cases:
            with self.subTest(expected_level=expected_level):
                items = []
                diagnostico._check_contaovos(items, status)
                self.assertEqual(expected_level, items[0]["nivel"])
                self.assertEqual("Conta Ovos", items[0]["categoria"])

    def test_diagnostico_avisa_sobre_formato_aceito_nao_documentado(self):
        items = []
        diagnostico._check_contaovos(
            items,
            {
                "configured": True,
                "verified": True,
                "ok": True,
                "checked_at": "2026-08-03T12:00:00",
                "credential_format": "accepted_non_documented_format",
                "scopes": [{"municipality": "Almirante Tamandare"}],
            },
        )
        self.assertEqual("aviso", items[0]["nivel"])
        self.assertIn("diferente do documentado", items[0]["titulo"])


class ContaOvosSchemaAndScriptsTests(unittest.TestCase):
    def test_schema_sqlite_cria_cursor_e_execucoes(self):
        conn = sqlite3.connect(":memory:")
        try:
            contaovos_integracao.ensure_schema(conn)
            status = contaovos_integracao.schema_status(conn)
            self.assertEqual({"cursor": True, "execucoes": True}, status)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO contaovos_execucoes "
                    "(tipo,iniciado_em,status) VALUES (?,?,?)",
                    ("validacao", "2026-08-03", "invalido"),
                )
        finally:
            conn.close()

    def test_migracao_postgresql_e_especifica_e_sem_filas(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "migrations/postgresql/0002_integracao_contaovos.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE contaovos_sync_cursor", sql)
        self.assertIn("CREATE TABLE contaovos_execucoes", sql)
        self.assertNotIn("fila_contagens", sql)
        self.assertNotIn("fila_visitas", sql)

    def test_tabelas_de_integracao_sao_internas_na_comparacao_do_snapshot(self):
        excluded = postgresql_schema_compare.INTERNAL_TABLES_SQL
        self.assertIn("contaovos_sync_cursor", excluded)
        self.assertIn("contaovos_execucoes", excluded)
        self.assertIn("endemias_schema_migrations", excluded)
        self.assertIn("contaovos_sync_cursor", schema_metadata.INTERNAL_TABLES)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventario.db"
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE dominio (id INTEGER PRIMARY KEY)")
                contaovos_integracao.ensure_schema(conn)
                conn.commit()
            finally:
                conn.close()
            inventory = sqlite_inventory.build_inventory(path)
        self.assertEqual(["dominio"], [table["name"] for table in inventory["tables"]])

    def test_consultas_de_comparacao_interpolam_tabelas_internas(self):
        statements = []

        def connection(*, fetchone=None, fetchall=None):
            cursor = mock.MagicMock()
            cursor.__enter__.return_value = cursor
            cursor.execute.side_effect = lambda sql: statements.append(sql)
            if fetchone is not None:
                cursor.fetchone.side_effect = fetchone
            if fetchall is not None:
                cursor.fetchall.side_effect = fetchall
            conn = mock.MagicMock()
            conn.cursor.return_value = cursor
            return conn

        postgresql_schema_compare._actual_columns(connection(fetchall=[[]]))
        postgresql_schema_compare._actual_summary(
            connection(
                fetchone=[(59,), (691,), (34,)],
                fetchall=[[('p', 59)]],
            )
        )
        postgresql_schema_compare._actual_constraint_names(
            connection(fetchall=[[]])
        )
        postgresql_schema_compare._actual_explicit_index_names(
            connection(fetchall=[[]])
        )

        self.assertEqual(7, len(statements))
        for sql in statements:
            normalized = sql.strip()
            self.assertIn("'contaovos_sync_cursor'", normalized)
            self.assertIn("'contaovos_execucoes'", normalized)
            self.assertNotIn("{INTERNAL_TABLES_SQL}", normalized)
            self.assertFalse(normalized.endswith("\nf"))

    def test_scripts_nao_recebem_chave_em_argumento(self):
        root = Path(__file__).resolve().parents[1]
        config = (root / "scripts/configurar_credencial_contaovos_system.ps1").read_text(
            encoding="utf-8"
        )
        test = (root / "scripts/testar_credencial_contaovos_system.ps1").read_text(
            encoding="utf-8"
        )
        wrapper = (root / "configurar_contaovos.bat").read_text(encoding="utf-8")
        self.assertIn("Read-Host", config)
        self.assertIn("-AsSecureString", config)
        self.assertIn('"S-1-5-18"', config)
        self.assertIn('"S-1-5-32-544"', config)
        self.assertNotIn("[string]$Key", config)
        self.assertIn('-UserId "SYSTEM"', test)
        self.assertIn("verificar_contaovos.py", test)
        self.assertIn("uma unica consulta privada", wrapper)

    def test_verificador_exige_frase_literal(self):
        root = Path(__file__).resolve().parents[1]
        verifier = (root / "scripts/verificar_contaovos.py").read_text(encoding="utf-8")
        self.assertIn("CONSULTAR API CONTA OVOS SEM ALTERAR DADOS", verifier)
        self.assertNotIn("postcounting", verifier.lower())
        self.assertNotIn("postaction", verifier.lower())

        with (
            mock.patch.object(contaovos_credencial, "read_key") as read_key,
            mock.patch("builtins.print"),
        ):
            result = verificar_contaovos.main(["--confirmar-leitura", "ERRADA"])
        self.assertEqual(2, result)
        read_key.assert_not_called()


if __name__ == "__main__":
    unittest.main()
