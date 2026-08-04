import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import contaovos_client
from app_core import contaovos_registro
from app_core import db as db_core
from scripts import sincronizar_registro_ovitrampas_contaovos as cli_registro
from scripts import testar_registro_ovitrampas_postgresql


def _remote_row(group_id="97", **overrides):
    row = {
        "ovitrap_id": 4471,
        "ovitrap_group_id": group_id,
        "ovitrap_datetime": "2026-08-02 14:32:10",
        "ovitrap_lat": -25.31,
        "ovitrap_lng": -49.29,
        "ovitrap_lat_lng_error": 0,
        "group_id": 12,
        "user_id": 348,
        "ovitrap_eggs_mean": 7.5,
        "ovitrap_block_id": 4521,
        "municipality": "Almirante Tamandaré",
        "municipality_code": "4100400",
        "state_code": "PR",
    }
    row.update(overrides)
    return row


class ContaOvosRegistroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "registro.db"

    def tearDown(self):
        self.temp.cleanup()

    def _fetcher(self, rows):
        def fetcher(**params):
            return rows if params["page"] == 1 else []
        return fetcher

    def test_fetch_registro_pagina_e_deduplica_ate_lista_vazia(self):
        calls = []

        def fetcher(**params):
            calls.append(params["page"])
            if params["page"] in (1, 2):
                return [_remote_row()]
            return []

        result = contaovos_registro.fetch_registro(page_fetcher=fetcher)
        self.assertEqual([1, 2, 3], calls)
        self.assertEqual(3, result["pages"])
        self.assertEqual(1, len(result["records"]))

    def test_fetch_registro_recusa_paginacao_sem_limite(self):
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError) as ctx:
            contaovos_registro.fetch_registro(
                max_pages=1, page_fetcher=lambda **params: [_remote_row()]
            )
        self.assertEqual("pagination_limit", ctx.exception.kind)

    def test_fetch_registro_recusa_municipio_divergente(self):
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError) as ctx:
            contaovos_registro.fetch_registro(
                page_fetcher=self._fetcher([_remote_row(municipality_code="9999999")])
            )
        self.assertEqual("scope_mismatch", ctx.exception.kind)

    def test_fetch_registro_recusa_sem_group_id(self):
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError) as ctx:
            contaovos_registro.fetch_registro(
                page_fetcher=self._fetcher([_remote_row(ovitrap_group_id=None)])
            )
        self.assertEqual("invalid_payload", ctx.exception.kind)

    def test_synchronize_e_idempotente_insere_atualiza_e_nao_altera(self):
        first = contaovos_registro.synchronize(
            self.db_path, page_fetcher=self._fetcher([_remote_row()])
        )
        self.assertEqual(1, first["inseridos"])
        self.assertTrue(first["ok"])

        second = contaovos_registro.synchronize(
            self.db_path, page_fetcher=self._fetcher([_remote_row()])
        )
        self.assertEqual(1, second["sem_alteracao"])

        third = contaovos_registro.synchronize(
            self.db_path,
            page_fetcher=self._fetcher([_remote_row(ovitrap_eggs_mean=99.0)]),
        )
        self.assertEqual(1, third["atualizados"])

        conn = db_core.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM contaovos_registro_ovitrampas WHERE ovitrampa_id_remoto='97'"
            ).fetchone()
            execucoes = conn.execute(
                "SELECT tipo, status FROM contaovos_execucoes"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(99.0, row["ovos_media"])
        self.assertEqual(3, len(execucoes))
        self.assertTrue(all(e["tipo"] == "sincronizacao_registro_ovitrampas" for e in execucoes))
        self.assertTrue(all(e["status"] == "concluido" for e in execucoes))

    def test_synchronize_nao_grava_nada_quando_paginacao_falha(self):
        with self.assertRaises(contaovos_registro.ContaOvosRegistroError):
            contaovos_registro.synchronize(
                self.db_path,
                max_pages=1,
                page_fetcher=lambda **params: [_remote_row()],
            )
        conn = db_core.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM contaovos_registro_ovitrampas"
            ).fetchone()[0]
            execucao = conn.execute(
                "SELECT status FROM contaovos_execucoes"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(0, count)
        self.assertEqual("erro", execucao["status"])

    def test_public_ovitraps_page_usa_get_sem_chave(self):
        seen = {}

        def opener(req, timeout):
            seen["method"] = req.get_method()
            seen["url"] = req.full_url
            from tests.test_contaovos_api import _Response
            return _Response([_remote_row()])

        rows = contaovos_client.public_ovitraps_page(page=1, opener=opener)
        self.assertEqual([_remote_row()], rows)
        self.assertEqual("GET", seen["method"])
        self.assertNotIn("key=", seen["url"])
        self.assertIn("municipality=", seen["url"])

    def test_public_ovitraps_page_bloqueia_rede_real_na_suite(self):
        with self.assertRaises(contaovos_client.ContaOvosError) as ctx:
            contaovos_client.public_ovitraps_page(page=1)
        self.assertEqual("test_network_blocked", ctx.exception.kind)


class ContaOvosRegistroScriptTests(unittest.TestCase):
    def test_cli_exige_confirmacao_de_leitura_antes_de_qualquer_consulta(self):
        with mock.patch.object(
            cli_registro.contaovos_registro, "fetch_registro"
        ) as fetch:
            result = cli_registro.main([])
        self.assertEqual(2, result)
        fetch.assert_not_called()

    def test_cli_aplicar_exige_autorizacao_explicita(self):
        with mock.patch.object(cli_registro.contaovos_registro, "synchronize") as sync:
            result = cli_registro.main([
                "--confirmar-leitura", cli_registro.READ_CONFIRMATION,
                "--aplicar",
            ])
        self.assertEqual(2, result)
        sync.assert_not_called()

    def test_cli_fora_de_endemias_teste_exige_confirmar_banco(self):
        with mock.patch.object(cli_registro.contaovos_registro, "synchronize") as sync:
            result = cli_registro.main([
                "--confirmar-leitura", cli_registro.READ_CONFIRMATION,
                "--aplicar",
                "--autorizar-atualizacao-local", cli_registro.APPLY_CONFIRMATION,
                "--database", "endemias",
            ])
        self.assertEqual(2, result)
        sync.assert_not_called()

    def test_cli_leitura_nao_grava_nada(self):
        with mock.patch.object(
            cli_registro.contaovos_registro, "fetch_registro",
            return_value={"records": [], "pages": 1},
        ) as fetch, mock.patch.object(
            cli_registro.contaovos_registro, "synchronize"
        ) as sync:
            result = cli_registro.main([
                "--confirmar-leitura", cli_registro.READ_CONFIRMATION,
            ])
        self.assertEqual(0, result)
        fetch.assert_called_once()
        sync.assert_not_called()

    def test_ensaio_postgresql_recusa_banco_oficial(self):
        with mock.patch.object(
            testar_registro_ovitrampas_postgresql.postgresql, "connect"
        ) as connect:
            result = testar_registro_ovitrampas_postgresql.main(["--database", "endemias"])
        self.assertEqual(2, result)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
