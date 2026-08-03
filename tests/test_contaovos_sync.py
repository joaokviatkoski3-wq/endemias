import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from app_core import contaovos_integracao
from app_core import contaovos_sync
from app_core import ovitrampas
from scripts import sincronizar_contagens_contaovos
from scripts import testar_contaovos_sync_postgresql


def _remote_row(counting_id=101, **overrides):
    row = {
        "municipality": "Almirante Tamandaré",
        "municipality_code": "4100400",
        "state_code": "PR",
        "counting_id": counting_id,
        "ovitrap_id": " 00097 ",
        "year": 2026,
        "week": 31,
        "eggs": 12,
        "time": "2026-08-03 14:30:00",
        "date": "2026-07-27",
        "date_collect": "2026-08-03",
        "counting_observation_id": 6,
        "counting_observation": "Ovitrampa seca",
        "latitude": -25.31,
        "longitude": -49.29,
    }
    row.update(overrides)
    return row


class ContaOvosNormalizationTests(unittest.TestCase):
    def test_normaliza_payload_e_reaproveita_mapa_de_ocorrencias(self):
        result = contaovos_sync.normalize_counting(
            _remote_row(), imported_at="2026-08-03T15:00:00"
        )

        self.assertEqual("101", result["id_contagem"])
        self.assertEqual("00097", result["ovitrampa_id"])
        self.assertEqual("2026-08-03", result["data"])
        self.assertEqual(6, result["codigo_conta_ovos"])
        self.assertEqual(
            ovitrampas.CONTA_OVOS_OCORRENCIAS[6], result["ocorrencia_codigo"]
        )
        self.assertEqual("-25.31,-49.29", result["lat_lng"])

    def test_comparacao_remove_zeros_sem_mudar_id_persistido(self):
        self.assertEqual("0097-A", ovitrampas.normalizar_ovitrampa_id("0097/A"))
        self.assertEqual(
            "97-A", ovitrampas.chave_comparacao_ovitrampa_id("0097/A")
        )

    def test_recusa_escopo_divergente(self):
        with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
            contaovos_sync.normalize_counting(
                _remote_row(municipality_code="9999999")
            )
        self.assertEqual("scope_mismatch", ctx.exception.kind)

    def test_recusa_id_remoto_ou_semana_invalidos(self):
        for changes in ({"counting_id": "abc"}, {"week": 54}):
            with self.subTest(changes=changes):
                with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
                    contaovos_sync.normalize_counting(_remote_row(**changes))
                self.assertEqual("invalid_payload", ctx.exception.kind)

    def test_paginacao_deduplica_e_para_na_lista_vazia(self):
        calls = []

        def fetcher(key, **params):
            calls.append(params["page"])
            if params["page"] in (1, 2):
                return [_remote_row()]
            return []

        result = contaovos_sync.fetch_countings(
            "segredo-teste", page_fetcher=fetcher
        )

        self.assertEqual([1, 2, 3], calls)
        self.assertEqual(3, result["pages"])
        self.assertEqual(1, len(result["records"]))

    def test_paginacao_recusa_avancar_no_limite(self):
        with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
            contaovos_sync.fetch_countings(
                "segredo-teste",
                max_pages=1,
                page_fetcher=lambda key, **params: [_remote_row()],
            )
        self.assertEqual("pagination_limit", ctx.exception.kind)

    def test_duplicate_divergente_e_recusado(self):
        def fetcher(key, **params):
            if params["page"] == 1:
                return [_remote_row(), _remote_row(eggs=99)]
            return []

        with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
            contaovos_sync.fetch_countings(
                "segredo-teste", page_fetcher=fetcher
            )
        self.assertEqual("conflicting_duplicate", ctx.exception.kind)

    def test_recusa_intervalo_de_datas_invalido(self):
        with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
            contaovos_sync.fetch_countings(
                "segredo-teste",
                date_start="2026-08-04",
                date_end="2026-08-03",
                page_fetcher=mock.Mock(),
            )
        self.assertEqual("invalid_date_filter", ctx.exception.kind)


class ContaOvosSynchronizationTests(unittest.TestCase):
    def _database(self, directory):
        path = Path(directory) / "sync.db"
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            ovitrampas.ensure_schema(conn)
            contaovos_integracao.ensure_schema(conn)
            conn.execute(
                "INSERT INTO ovitrampas_armadilhas "
                "(ovitrampa_id, atualizado_em) VALUES (?, ?)",
                ("97", "2026-08-03T14:00:00"),
            )
            conn.commit()
        finally:
            conn.close()
        return path

    def _fetcher(self, rows):
        def fetcher(key, **params):
            return rows if params["page"] == 1 else []

        return fetcher

    def test_sincroniza_idempotente_e_atualiza_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            first = contaovos_sync.synchronize_countings(
                path,
                key="segredo-teste",
                page_fetcher=self._fetcher([_remote_row()]),
                now=datetime(2026, 8, 3, 15, 0, 0),
            )
            second = contaovos_sync.synchronize_countings(
                path,
                key="segredo-teste",
                page_fetcher=self._fetcher([_remote_row()]),
                now=datetime(2026, 8, 3, 15, 5, 0),
            )
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                stored = conn.execute(
                    "SELECT * FROM ovitrampas_ocorrencias_conta_ovos"
                ).fetchone()
                cursor = conn.execute(
                    "SELECT * FROM contaovos_sync_cursor WHERE fluxo='contagens'"
                ).fetchone()
                executions = conn.execute(
                    "SELECT status FROM contaovos_execucoes ORDER BY id_execucao"
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(1, first["inseridos"])
        self.assertEqual(0, first["ovitrampas_nao_cadastradas"])
        self.assertEqual(1, second["sem_alteracao"])
        self.assertEqual("97", stored["ovitrampa_id"])
        self.assertEqual("101", cursor["ultimo_id_remoto"])
        self.assertIsNone(cursor["execucao_token"])
        self.assertEqual(["concluido", "concluido"], [row[0] for row in executions])

    def test_atualiza_registro_existente_sem_recuar_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "INSERT INTO contaovos_sync_cursor "
                    "(fluxo,ultimo_id_remoto,atualizado_em) VALUES (?,?,?)",
                    ("contagens", "500", "2026-08-03T14:00:00"),
                )
                conn.commit()
            finally:
                conn.close()
            contaovos_sync.synchronize_countings(
                path,
                key="segredo-teste",
                page_fetcher=self._fetcher([_remote_row(eggs=1)]),
                now=datetime(2026, 8, 3, 15, 0, 0),
            )
            result = contaovos_sync.synchronize_countings(
                path,
                key="segredo-teste",
                page_fetcher=self._fetcher([_remote_row(eggs=2)]),
                now=datetime(2026, 8, 3, 15, 5, 0),
            )

        self.assertEqual(1, result["atualizados"])
        self.assertEqual("500", result["cursor_atual"])

    def test_falha_de_paginacao_nao_importa_e_libera_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            with self.assertRaises(contaovos_sync.ContaOvosSyncError):
                contaovos_sync.synchronize_countings(
                    path,
                    key="segredo-que-nao-pode-vazar",
                    max_pages=1,
                    page_fetcher=lambda key, **params: [_remote_row()],
                    now=datetime(2026, 8, 3, 15, 0, 0),
                )
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos"
                ).fetchone()[0]
                cursor = conn.execute(
                    "SELECT * FROM contaovos_sync_cursor WHERE fluxo='contagens'"
                ).fetchone()
                execution = conn.execute(
                    "SELECT * FROM contaovos_execucoes"
                ).fetchone()
            finally:
                conn.close()

        self.assertEqual(0, count)
        self.assertIsNone(cursor["execucao_token"])
        self.assertEqual("erro", execution["status"])
        self.assertNotIn(
            "segredo-que-nao-pode-vazar", execution["resumo_sanitizado"]
        )

    def test_falha_durante_persistencia_desfaz_todos_os_itens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            original = ovitrampas.upsert_ocorrencia_conta_ovos
            calls = []

            def fail_after_first(conn, record):
                calls.append(record["id_contagem"])
                if len(calls) == 2:
                    raise RuntimeError("falha local simulada")
                return original(conn, record)

            with (
                mock.patch.object(
                    ovitrampas,
                    "upsert_ocorrencia_conta_ovos",
                    side_effect=fail_after_first,
                ),
                self.assertRaises(RuntimeError),
            ):
                contaovos_sync.synchronize_countings(
                    path,
                    key="segredo-teste",
                    page_fetcher=self._fetcher(
                        [_remote_row(101), _remote_row(102)]
                    ),
                    now=datetime(2026, 8, 3, 15, 0, 0),
                )
            conn = sqlite3.connect(path)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos"
                ).fetchone()[0]
                status = conn.execute(
                    "SELECT status FROM contaovos_execucoes"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(0, count)
        self.assertEqual("erro", status)

    def test_single_flight_recusa_execucao_recente(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "INSERT INTO contaovos_sync_cursor "
                    "(fluxo,ultimo_id_remoto,atualizado_em,em_execucao_desde,execucao_token) "
                    "VALUES (?,?,?,?,?)",
                    (
                        "contagens",
                        None,
                        "2026-08-03T15:00:00",
                        "2026-08-03T15:00:00",
                        "outro-processo",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            fetcher = mock.Mock()
            with self.assertRaises(contaovos_sync.ContaOvosSyncAlreadyRunning):
                contaovos_sync.synchronize_countings(
                    path,
                    key="segredo-teste",
                    page_fetcher=fetcher,
                    now=datetime(2026, 8, 3, 15, 5, 0),
                )
        fetcher.assert_not_called()

    def test_recusa_ids_locais_ambiguos_sem_fragmentar_historico(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "INSERT INTO ovitrampas_armadilhas "
                    "(ovitrampa_id, atualizado_em) VALUES (?, ?)",
                    ("00097", "2026-08-03T14:00:00"),
                )
                conn.commit()
            finally:
                conn.close()
            with self.assertRaises(contaovos_sync.ContaOvosSyncError) as ctx:
                contaovos_sync.synchronize_countings(
                    path,
                    key="segredo-teste",
                    page_fetcher=self._fetcher([_remote_row()]),
                    now=datetime(2026, 8, 3, 15, 0, 0),
                )
            conn = sqlite3.connect(path)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual("ambiguous_ovitrap_id", ctx.exception.kind)
        self.assertEqual(0, count)

    def test_single_flight_recupera_trava_abandonada(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "INSERT INTO contaovos_sync_cursor "
                    "(fluxo,ultimo_id_remoto,atualizado_em,em_execucao_desde,execucao_token) "
                    "VALUES (?,?,?,?,?)",
                    (
                        "contagens",
                        None,
                        "2026-08-03T14:00:00",
                        "2026-08-03T14:00:00",
                        "processo-interrompido",
                    ),
                )
                conn.execute(
                    "INSERT INTO contaovos_execucoes "
                    "(tipo,iniciado_em,status) VALUES (?,?,?)",
                    (
                        "sincronizacao_contagens",
                        "2026-08-03T14:00:00",
                        "executando",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            result = contaovos_sync.synchronize_countings(
                path,
                key="segredo-teste",
                page_fetcher=self._fetcher([_remote_row()]),
                now=datetime(2026, 8, 3, 15, 0, 0),
            )
            conn = sqlite3.connect(path)
            try:
                statuses = conn.execute(
                    "SELECT status FROM contaovos_execucoes ORDER BY id_execucao"
                ).fetchall()
            finally:
                conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(["erro", "concluido"], [row[0] for row in statuses])


class ContaOvosSyncScriptTests(unittest.TestCase):
    def test_script_exige_confirmacoes_antes_de_ler_credencial(self):
        with (
            mock.patch.object(
                sincronizar_contagens_contaovos.contaovos_credencial,
                "read_key",
            ) as read_key,
            mock.patch("builtins.print"),
        ):
            result = sincronizar_contagens_contaovos.main([])
        self.assertEqual(2, result)
        read_key.assert_not_called()

    def test_migracao_adiciona_colunas_da_trava(self):
        root = Path(__file__).resolve().parents[1]
        sql = (
            root / "migrations/postgresql/0003_contaovos_sync_lock.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("em_execucao_desde", sql)
        self.assertIn("execucao_token", sql)

    def test_wrapper_exige_confirmacao_e_nao_chama_endpoints_de_escrita(self):
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "sincronizar_contaovos.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("choice /C 12", wrapper)
        self.assertIn("AddDays(-45)", wrapper)
        self.assertIn("%ANO_ATUAL%-01-01", wrapper)
        self.assertIn("--confirmar-banco endemias", wrapper)
        self.assertNotIn("postcounting", wrapper.lower())
        self.assertNotIn("postdelete", wrapper.lower())

    def test_ensaio_postgresql_recusa_banco_oficial(self):
        with (
            mock.patch.object(
                testar_contaovos_sync_postgresql.postgresql, "connect"
            ) as connect,
            mock.patch("builtins.print"),
        ):
            result = testar_contaovos_sync_postgresql.main(
                ["--database", "endemias"]
            )
        self.assertEqual(2, result)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
