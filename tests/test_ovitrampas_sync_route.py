import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from blueprints import ovitrampas as ovitrampas_blueprint


class OvitrampasSyncRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app.config["DB_PATH"] = str(Path(self.temp_dir.name) / "teste.db")
        self.view = (
            ovitrampas_blueprint.api_sincronizar_conta_ovos
            .__wrapped__
            .__wrapped__
        )

    def test_sincroniza_cadastro_e_contagens_somente_por_get(self):
        cadastro = {
            "ok": True,
            "id_execucao": 10,
            "registros": 343,
            "paginas": 4,
            "inseridos": 12,
            "atualizados": 2,
            "sem_alteracao": 329,
        }
        contagens = {
            "ok": True,
            "id_execucao": 11,
            "inseridos": 4,
            "atualizados": 8,
            "sem_alteracao": 20,
            "registros": 32,
        }
        with self.app.test_request_context(
            "/api/ovitrampas/sincronizar-conta-ovos", method="POST"
        ):
            with mock.patch.object(
                ovitrampas_blueprint.contaovos_credencial,
                "configured",
                return_value=True,
            ), mock.patch.object(
                ovitrampas_blueprint.contaovos_credencial,
                "read_key",
                return_value="chave-de-teste",
            ), mock.patch.object(
                ovitrampas_blueprint.contaovos_registro,
                "synchronize",
                return_value=cadastro,
            ) as sync_cadastro, mock.patch.object(
                ovitrampas_blueprint.contaovos_sync,
                "synchronize_countings",
                return_value=contagens,
            ) as sync_contagens, mock.patch.object(
                ovitrampas_blueprint.audit, "registrar_evento"
            ) as audit_evento:
                response = self.view()

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(343, data["cadastro"]["registros"])
        self.assertEqual(4, data["contagens"]["inseridos"])
        sync_cadastro.assert_called_once_with(
            mock.ANY, max_pages=100
        )
        sync_contagens.assert_called_once()
        chamada = sync_contagens.call_args.kwargs
        self.assertEqual("chave-de-teste", chamada["key"])
        self.assertEqual(100, chamada["max_pages"])
        self.assertRegex(chamada["date_start"], r"^20\d\d-\d\d-\d\d$")
        self.assertRegex(chamada["date_end"], r"^20\d\d-\d\d-\d\d$")
        audit_evento.assert_called_once()
        self.assertNotIn("chave-de-teste", repr(audit_evento.call_args))

    def test_sem_credencial_atualiza_cadastro_e_retorna_aviso(self):
        with self.app.test_request_context(
            "/api/ovitrampas/sincronizar-conta-ovos", method="POST"
        ):
            with mock.patch.object(
                ovitrampas_blueprint.contaovos_credencial,
                "configured",
                return_value=False,
            ), mock.patch.object(
                ovitrampas_blueprint.contaovos_registro,
                "synchronize",
                return_value={"registros": 343},
            ), mock.patch.object(
                ovitrampas_blueprint.contaovos_sync,
                "synchronize_countings",
            ) as sync_contagens, mock.patch.object(
                ovitrampas_blueprint.audit, "registrar_evento"
            ):
                response = self.view()

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(343, data["cadastro"]["registros"])
        self.assertIsNone(data["contagens"])
        self.assertTrue(any("credencial" in aviso for aviso in data["avisos"]))
        sync_contagens.assert_not_called()


if __name__ == "__main__":
    unittest.main()
