import unittest
from datetime import date
from unittest import mock

from app_core import db, kobo_api, kobo_auto


class KoboAutoTests(unittest.TestCase):
    def test_periodo_inclusivo_de_sete_dias(self):
        self.assertEqual(kobo_auto.periodo_7_dias(date(2026, 9, 25)), ("2026-09-19", "2026-09-25"))

    def test_resposta_truncada_interrompe_antes_da_gravacao(self):
        cfg = {"assets": {"PVE": "uid"}}
        with mock.patch.object(kobo_auto.kobo_api, "fetch_submissions", return_value=(
            [{"_uuid": "a"}], {"count": 2, "next": "pagina-2"}
        )):
            with self.assertRaisesRegex(kobo_auto.ImportacaoAutomaticaErro, "incompleta"):
                kobo_auto._buscar_novos(cfg, "banco", "2026-09-19", "2026-09-25")

    def test_filtra_uuids_existentes_sem_reescrever(self):
        cfg = {"assets": {"PVE": "uid"}}
        registros = [{"_uuid": "a"}, {"_uuid": "b"}]
        with (
            mock.patch.object(kobo_auto.kobo_api, "fetch_submissions", return_value=(registros, {"count": 2, "next": None})),
            mock.patch.object(kobo_auto, "_uuids_existentes", return_value={"a"}),
        ):
            novos, totais = kobo_auto._buscar_novos(cfg, "banco", "2026-09-19", "2026-09-25")
        self.assertEqual(novos["PVE"], [{"_uuid": "b"}])
        self.assertEqual(totais["PVE"], {"recebidos": 2, "novos": 1})

    def test_limite_sem_total_verificavel_falha_fechada(self):
        cfg = {"assets": {"PVE": "uid"}}
        with mock.patch.object(kobo_auto.kobo_api, "fetch_submissions", return_value=(
            [{"_uuid": str(i)} for i in range(5000)], {"results": []}
        )):
            with self.assertRaisesRegex(kobo_auto.ImportacaoAutomaticaErro, "total verificável"):
                kobo_auto._buscar_novos(cfg, "banco", "2026-09-19", "2026-09-25")

    def test_sem_uuid_falha_fechada(self):
        with self.assertRaisesRegex(kobo_auto.ImportacaoAutomaticaErro, "sem UUID"):
            kobo_auto._uuids_existentes("banco", "PVE", [{"_id": 123}])

    def test_exige_token_antes_de_consultar(self):
        with (
            mock.patch.object(kobo_auto, "_exigir_migracoes"),
            mock.patch.object(kobo_api, "load_config", return_value={"server_url": "https://kobo", "api_token": "", "assets": {"PVE": "uid"}}),
        ):
            with self.assertRaisesRegex(kobo_auto.ImportacaoAutomaticaErro, "não configurado"):
                kobo_auto.executar(target="banco", config_path="config", kobo_config_path="kobo", migracoes_dir="migracoes")

    def test_sem_novos_registra_execucao_sem_chamar_etl(self):
        target = db.DatabaseTarget("postgresql", "endemias_teste")
        with (
            mock.patch.object(kobo_auto, "_exigir_migracoes"),
            mock.patch.object(kobo_api, "load_config", return_value={"server_url": "https://kobo", "api_token": "token", "assets": {"PVE": "uid"}}),
            mock.patch.object(kobo_auto, "_buscar_novos", return_value=({"PVE": []}, {"PVE": {"recebidos": 2, "novos": 0}})),
            mock.patch.object(kobo_auto, "_aviso_lacuna", return_value=None),
            mock.patch.object(kobo_auto.import_history, "registrar_importacao") as registrar,
            mock.patch.object(kobo_auto.import_history, "atualizar_importacao") as atualizar,
            mock.patch.object(kobo_auto.etl, "processar_upload") as processar,
        ):
            resultado = kobo_auto.executar(
                target=target, config_path="config", kobo_config_path="kobo",
                migracoes_dir="migracoes", hoje=date(2026, 9, 25), aplicar=True,
            )
        self.assertEqual(resultado["novos"], 0)
        registrar.assert_called_once()
        self.assertEqual(atualizar.call_args.args[2], "auto_sem_novos")
        processar.assert_not_called()

    def test_verificacao_falha_sem_gravar(self):
        target = db.DatabaseTarget("postgresql", "endemias_teste")
        with (
            mock.patch.object(kobo_auto, "_exigir_migracoes"),
            mock.patch.object(kobo_api, "load_config", return_value={"server_url": "https://kobo", "api_token": "token", "assets": {"PVE": "uid"}}),
            mock.patch.object(kobo_auto, "_buscar_novos", return_value=({"PVE": [{"_uuid": "novo"}]}, {"PVE": {"recebidos": 1, "novos": 1}})),
            mock.patch.object(kobo_auto, "_aviso_lacuna", return_value=None),
            mock.patch.object(kobo_auto.import_history, "registrar_importacao"),
            mock.patch.object(kobo_auto.import_history, "atualizar_importacao") as atualizar,
            mock.patch.object(kobo_api, "write_etl_workbooks", return_value=["PVE_teste.xlsx"]),
            mock.patch.object(kobo_auto.etl, "processar_upload", return_value=(False, [])) as processar,
        ):
            with self.assertRaisesRegex(kobo_auto.ImportacaoAutomaticaErro, "Verificação"):
                kobo_auto.executar(
                    target=target, config_path="config", kobo_config_path="kobo",
                    migracoes_dir="migracoes", aplicar=True,
                )
        processar.assert_called_once()
        self.assertTrue(processar.call_args.kwargs["dry_run"])
        self.assertEqual(atualizar.call_args.args[2], "auto_erro")


if __name__ == "__main__":
    unittest.main()
