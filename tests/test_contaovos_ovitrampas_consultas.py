import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from app_core import contaovos_ovitrampas_consultas as ovi
from app_core import contaovos_registro
from app_core import db as db_core
from app_core import ovitrampas
from blueprints import conta_ovos


API_SOURCE = "API privada Conta Ovos"


class ContaOvosOvitrampasConsultasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "ovi.db"
        conn = db_core.connect(self.db_path)
        try:
            ovitrampas.ensure_schema(conn)
            # contaovos_registro_ovitrampas fica de fora deste setUp de proposito:
            # alguns testes verificam o comportamento antes da primeira sincronizacao.
            conn.execute(
                """INSERT INTO ovitrampas_armadilhas
                   (ovitrampa_id,rua,localidade,responsavel,telefone_responsavel,
                    quarteirao,ativo,latitude,longitude,atualizado_em)
                   VALUES ('97','Rua A','Sede','Maria','41999990000',
                           '0042',1,-25.31,-49.29,'2026-08-04T10:00:00')"""
            )
            # Contagem com proveniencia API (deve aparecer nas telas remotas).
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem,ovitrampa_id,ano,semana,data,ovos,resultado,
                    ocorrencia_codigo,arquivo_origem,importado_em)
                   VALUES ('900','97',2026,31,'2026-08-03',12,'Positiva',5,?,'2026-08-04T10:00:00')""",
                (API_SOURCE,),
            )
            # Contagem legada via CSV (nao deve aparecer nas telas remotas).
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem,ovitrampa_id,ano,semana,data,ovos,resultado,
                    arquivo_origem,importado_em)
                   VALUES ('901','97',2026,30,'2026-07-27',5,'Positiva',
                           'municipality-3918-2026.csv','2026-08-03T10:00:00')"""
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_listar_contagens_api_exclui_proveniencia_csv(self):
        data = ovi.listar_contagens_api(self.db_path)
        self.assertEqual(1, data["total"])
        self.assertEqual("900", data["registros"][0]["id_contagem"])
        self.assertEqual(API_SOURCE, data["registros"][0]["arquivo_origem"])

    def test_listar_contagens_api_aplica_filtros_sem_escrever(self):
        antes = db_core.scalar(
            self.db_path, "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos"
        )
        data = ovi.listar_contagens_api(self.db_path, {"ano": "2026", "semana": "31"})
        depois = db_core.scalar(
            self.db_path, "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos"
        )
        self.assertEqual(antes, depois)
        self.assertEqual(1, data["total"])

        vazio = ovi.listar_contagens_api(self.db_path, {"semana": "1"})
        self.assertEqual(0, vazio["total"])

    def test_listar_contagens_api_rejeita_filtro_nao_numerico(self):
        with self.assertRaisesRegex(ValueError, "numeros inteiros"):
            ovi.listar_contagens_api(self.db_path, {"ano": "dois-mil"})

    def test_monitoramento_api_ignora_contagens_csv(self):
        data = ovi.monitoramento_api(self.db_path)
        self.assertEqual(1, data["totais"]["contagens"])
        self.assertEqual(1, data["totais"]["positivas"])
        self.assertEqual(1, len(data["ranking"]))
        self.assertEqual("97", data["ranking"][0]["ovitrampa_id"])

    def test_cadastro_remoto_indisponivel_sem_tabela(self):
        with self.assertRaises(ovi.EspelhoContaOvosIndisponivel):
            ovi.listar_cadastro_remoto(self.db_path)

    def test_cadastro_remoto_anexa_complemento_local_rotulado(self):
        contaovos_registro.synchronize(
            self.db_path,
            page_fetcher=lambda **params: (
                [{
                    "ovitrap_id": 1, "ovitrap_group_id": "97",
                    "ovitrap_datetime": "2026-08-02", "ovitrap_lat": -25.31,
                    "ovitrap_lng": -49.29, "ovitrap_lat_lng_error": 0,
                    "group_id": 1, "user_id": 1, "ovitrap_eggs_mean": 7.0,
                    "ovitrap_block_id": 1, "municipality": "Almirante Tamandaré",
                    "municipality_code": "4100400", "state_code": "PR",
                }] if params["page"] == 1 else []
            ),
        )
        data = ovi.listar_cadastro_remoto(self.db_path)
        self.assertEqual(1, data["total"])
        registro = data["registros"][0]
        self.assertEqual("97", registro["ovitrampa_id_remoto"])
        self.assertIsNotNone(registro["complemento_local"])
        self.assertEqual("Sede", registro["complemento_local"]["localidade"])
        self.assertEqual("Maria", registro["complemento_local"]["responsavel"])

    def test_mapa_pontos_traz_apenas_coordenadas_com_localidade_local_leitura(self):
        contaovos_registro.synchronize(
            self.db_path,
            page_fetcher=lambda **params: (
                [{
                    "ovitrap_id": 1, "ovitrap_group_id": "97",
                    "ovitrap_datetime": "2026-08-02", "ovitrap_lat": -25.31,
                    "ovitrap_lng": -49.29, "ovitrap_lat_lng_error": 0,
                    "group_id": 1, "user_id": 1, "ovitrap_eggs_mean": 7.0,
                    "ovitrap_block_id": 1, "municipality": "Almirante Tamandaré",
                    "municipality_code": "4100400", "state_code": "PR",
                }] if params["page"] == 1 else []
            ),
        )
        data = ovi.mapa_pontos(self.db_path)
        self.assertEqual(1, len(data["pontos"]))
        ponto = data["pontos"][0]
        self.assertEqual("Sede", ponto["localidade_local"])
        self.assertEqual("0042", ponto["quarteirao_local"])
        self.assertTrue(ponto["cadastro_local_encontrado"])

    def test_divergencias_sem_registro_indica_indisponivel(self):
        data = ovi.divergencias(self.db_path)
        self.assertFalse(data["registro_disponivel"])

    def test_divergencias_identifica_sem_cadastro_local_e_coordenadas(self):
        contaovos_registro.synchronize(
            self.db_path,
            page_fetcher=lambda **params: (
                [
                    {
                        "ovitrap_id": 1, "ovitrap_group_id": "97",
                        "ovitrap_datetime": "2026-08-02", "ovitrap_lat": -25.50,
                        "ovitrap_lng": -49.29, "ovitrap_lat_lng_error": 0,
                        "group_id": 1, "user_id": 1, "ovitrap_eggs_mean": 7.0,
                        "ovitrap_block_id": 1, "municipality": "Almirante Tamandaré",
                        "municipality_code": "4100400", "state_code": "PR",
                    },
                    {
                        "ovitrap_id": 2, "ovitrap_group_id": "555",
                        "ovitrap_datetime": "2026-08-02", "ovitrap_lat": -25.10,
                        "ovitrap_lng": -49.10, "ovitrap_lat_lng_error": 0,
                        "group_id": 1, "user_id": 1, "ovitrap_eggs_mean": 0,
                        "ovitrap_block_id": 1, "municipality": "Almirante Tamandaré",
                        "municipality_code": "4100400", "state_code": "PR",
                    },
                ] if params["page"] == 1 else []
            ),
        )
        data = ovi.divergencias(self.db_path)
        self.assertTrue(data["registro_disponivel"])
        self.assertEqual(["555"], data["sem_cadastro_local"])
        self.assertEqual(1, len(data["coordenadas_divergentes"]))
        self.assertEqual("97", data["coordenadas_divergentes"][0]["ovitrampa_id_remoto"])

    def test_sincronizacao_status_sem_tabela_retorna_vazio(self):
        conn = db_core.connect(self.db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS contaovos_execucoes")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual({"fluxos": []}, ovi.sincronizacao_status(self.db_path))

    def test_rotas_ovitrampas_retornam_503_quando_espelho_indisponivel(self):
        app = Flask(__name__)
        app.config["DB_PATH"] = str(self.db_path)
        erro = ovi.EspelhoContaOvosIndisponivel("Espelho indisponivel")
        cases = (
            ("/api/conta-ovos/ovitrampas/resumo", conta_ovos.api_ovi_resumo, (), "resumo_ovitrampas"),
            ("/api/conta-ovos/ovitrampas/contagens", conta_ovos.api_ovi_contagens, (), "listar_contagens_api"),
            ("/api/conta-ovos/ovitrampas/monitoramento", conta_ovos.api_ovi_monitoramento, (), "monitoramento_api"),
            ("/api/conta-ovos/ovitrampas/cadastro-remoto", conta_ovos.api_ovi_cadastro_remoto, (), "listar_cadastro_remoto"),
            ("/api/conta-ovos/ovitrampas/cadastro-remoto/97", conta_ovos.api_ovi_cadastro_remoto_detalhe, ("97",), "detalhes_cadastro_remoto"),
            ("/api/conta-ovos/ovitrampas/mapa", conta_ovos.api_ovi_mapa, (), "mapa_pontos"),
        )
        for path, view, args, service in cases:
            with self.subTest(path=path), app.test_request_context(path), mock.patch.object(
                ovi, service, side_effect=erro
            ):
                response, status = view.__wrapped__(*args)
                self.assertEqual(503, status)
                self.assertEqual("Espelho indisponivel", response.get_json()["erro"])

    def test_todas_as_rotas_do_blueprint_sao_get(self):
        methods_by_rule = {}
        app = Flask(__name__)
        app.register_blueprint(conta_ovos.bp)
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("conta_ovos."):
                methods_by_rule[rule.rule] = rule.methods
        for rule, methods in methods_by_rule.items():
            with self.subTest(rule=rule):
                self.assertNotIn("POST", methods)
                self.assertNotIn("PUT", methods)
                self.assertNotIn("DELETE", methods)


if __name__ == "__main__":
    unittest.main()
