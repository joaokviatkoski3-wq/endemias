import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from app_core import contaovos_consultas
from app_core import db as db_core
from app_core import ovitrampas
from blueprints import conta_ovos


class ContaOvosCentralTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "central.db"
        conn = db_core.connect(self.db_path)
        try:
            ovitrampas.ensure_schema(conn)
            conn.execute(
                """INSERT INTO ovitrampas_armadilhas
                   (ovitrampa_id,rua,numero,localidade,responsavel,quarteirao,ativo,atualizado_em)
                   VALUES ('00097','Rua A','10','Sede','Maria','0042',1,'2026-08-04T10:00:00')"""
            )
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem,ovitrampa_id,ano,semana,data,ovos,resultado,ocorrencia_codigo,importado_em)
                   VALUES ('101','00097',2026,31,'2026-08-03',12,'Ovitrampa seca',5,'2026-08-04T10:00:00')"""
            )
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem,ovitrampa_id,ano,semana,data,ovos,resultado,importado_em)
                   VALUES ('102','00097',2026,30,'2026-07-27',0,'Normal','2026-08-03T10:00:00')"""
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_resumo_usa_espelho_local_e_historico_de_execucoes(self):
        data = contaovos_consultas.resumo(self.db_path)

        self.assertEqual(1, data["totais"]["armadilhas"])
        self.assertEqual(2, data["totais"]["contagens"])
        self.assertEqual(12, data["totais"]["ovos"])
        self.assertEqual(1, data["totais"]["positivas"])
        self.assertEqual(31, data["semanas"][0]["semana"])

    def test_contagens_filtra_sem_qualquer_escrita_no_historico(self):
        antes = db_core.scalar(self.db_path, "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos")
        data = contaovos_consultas.listar_contagens(
            self.db_path, {"ano": "2026", "positivas": "1", "busca": "sede"}
        )
        depois = db_core.scalar(self.db_path, "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos")

        self.assertEqual(antes, depois)
        self.assertEqual(1, data["total"])
        self.assertEqual("101", data["registros"][0]["id_contagem"])
        self.assertEqual("Sede", data["registros"][0]["localidade"])

    def test_cadastro_e_detalhe_agregam_contagens_sem_mudar_cadastro(self):
        lista = contaovos_consultas.listar_ovitrampas(self.db_path, {"busca": "maria"})
        detalhe = contaovos_consultas.detalhes_ovitrampa(self.db_path, "00097")

        self.assertEqual(1, lista["total"])
        self.assertEqual(2, lista["registros"][0]["contagens"])
        self.assertEqual(12, lista["registros"][0]["ovos_total"])
        self.assertEqual("Maria", detalhe["armadilha"]["responsavel"])
        self.assertEqual(["101", "102"], [row["id_contagem"] for row in detalhe["contagens"]])

    def test_rejeita_filtro_numerico_invalido(self):
        with self.assertRaisesRegex(ValueError, "numeros inteiros"):
            contaovos_consultas.listar_contagens(self.db_path, {"semana": "trinta"})

    def test_rotas_retorna_503_quando_espelho_nao_esta_preparado(self):
        app = Flask(__name__)
        app.config["DB_PATH"] = str(self.db_path)
        erro = contaovos_consultas.EspelhoContaOvosIndisponivel("Espelho indisponivel")
        cases = (
            ("/api/conta-ovos/central/resumo", conta_ovos.api_resumo, (), "resumo"),
            ("/api/conta-ovos/central/contagens", conta_ovos.api_contagens, (), "listar_contagens"),
            ("/api/conta-ovos/central/ovitrampas", conta_ovos.api_ovitrampas, (), "listar_ovitrampas"),
            ("/api/conta-ovos/central/ovitrampas/97", conta_ovos.api_ovitrampa, ("97",), "detalhes_ovitrampa"),
        )
        for path, view, args, service in cases:
            with self.subTest(path=path), app.test_request_context(path), mock.patch.object(
                contaovos_consultas, service, side_effect=erro
            ):
                response, status = view.__wrapped__(*args)
                self.assertEqual(503, status)
                self.assertEqual("Espelho indisponivel", response.get_json()["erro"])
