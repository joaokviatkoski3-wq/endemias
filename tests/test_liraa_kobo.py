import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app_core import db, kobo_api, liraa, liraa_kobo
from blueprints import liraa as liraa_routes


def envio(uuid, quarteirao="408.1", localidade="centro", data="2026-10-06", tubitos=True):
    return {
        "_uuid": uuid, "_id": 100, "_submission_time": "2026-10-06T17:00:00Z",
        "Data": data, "Hora_inicio": "14:45:00", "Agentes": "jo_o pedro",
        "ACS": "ACS-006", "Dados_visita": {
            "Localidade": localidade, "Quarteir_o": quarteirao, "Imovel": "rco",
            "Logradouro": "Rua Teste", "Numero": 48, "Sequencia": "2",
            "Morador": "Morador teste", "Observa_es": ""},
        "group_jr1vc40": ([{"N_mero_do_tubito": 78, "C_digo_do_dep_sito": "B2",
                            "Dep_sito": "Banana"}] if tubitos else []),
    }


class LiraaKoboTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = str(Path(temporary.name) / "liraa.db")
        conn = db.connect(self.target)
        conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT NOT NULL)")
        conn.execute("INSERT INTO localidades VALUES (1,'Sede')")
        liraa._schema(conn)
        liraa_kobo.ensure_schema(conn)
        conn.execute("""INSERT INTO liraa_ciclos
            (id_ciclo,ano,nome,inicio,fim,observacoes,criado_em)
            VALUES (1,2026,'Teste','2026-10-01','2026-10-31','','2026-10-01')""")
        conn.execute("""INSERT INTO liraa_estratos
            (id_estrato,id_ciclo,numero,tipo,imoveis_confirmados,observacoes,criado_em,atualizado_em)
            VALUES (2,1,1,'normal',9000,'','2026-10-01','2026-10-01')""")
        conn.execute("""INSERT INTO liraa_estrato_quarteiroes
            (id_estrato,id_ciclo,id_localidade,quarteirao) VALUES (2,1,1,'408.1')""")
        selected = json.dumps([{"id_localidade": 1, "quarteirao": "408.1"}])
        conn.execute("""INSERT INTO liraa_sorteios
            (id_estrato,criado_em,semente,n,a,q,fracao,intervalo,inicio_casual,
             universo_hash,universo_json,selecionados_json)
            VALUES (2,'2026-10-01','1',1,1,1,0.2,1,0.1,'hash','[]',?)""", (selected,))
        conn.commit()
        conn.close()

    def test_ponto_virgula_e_zero_decimal_sao_o_mesmo_quarteirao(self):
        records = [envio("uuid-ponto", "408.1"), envio("uuid-virgula", "408,1"),
                   envio("uuid-zero", "408,10")]
        preview = liraa_kobo.previa(self.target, 1, records)
        self.assertEqual({x["quarteirao"] for x in preview}, {"408.1"})
        self.assertEqual({x["situacao_vinculo"] for x in preview}, {"sorteado"})
        self.assertEqual(liraa_kobo._quarteirao("408"), "0408")

    def test_zero_a_esquerda_no_cadastro_nao_impede_vinculo_decimal(self):
        conn = db.connect(self.target)
        conn.execute("UPDATE liraa_estrato_quarteiroes SET quarteirao='0408.1'")
        conn.execute("UPDATE liraa_sorteios SET selecionados_json=?", (
            json.dumps([{"id_localidade": 1, "quarteirao": "0408.1"}]),))
        conn.commit()
        conn.close()
        self.assertEqual(liraa_kobo.previa(self.target, 1, [envio("leading", "408,1")])[0]
                         ["situacao_vinculo"], "sorteado")

    def test_importacao_idempotente_tubitos_e_exclusao_impede_retorno(self):
        records = [envio("uuid-um"), envio("uuid-dois", tubitos=False)]
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 2)
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 0)
        visits = liraa_kobo.listar(self.target, 1)
        self.assertEqual(len(visits), 2)
        first = next(v for v in visits if v["kobo_uuid"] == "uuid-um")
        self.assertEqual(first["situacao_vinculo"], "sorteado")
        self.assertEqual(first["total_tubitos"], 1)
        self.assertEqual(liraa_kobo.tubitos(self.target, first["id_visita"])[0]["numero"], "78")
        liraa_kobo.excluir(self.target, first["id_visita"], "Teste")
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 0)
        self.assertEqual([v["kobo_uuid"] for v in liraa_kobo.listar(self.target)], ["uuid-dois"])
        conn = db.connect(self.target)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_visita_tubitos").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT motivo FROM liraa_visitas_excluidas").fetchone()[0], "Teste")
        conn.close()

    def test_fora_sorteio_e_periodo_nao_recebem_vinculo_indevido(self):
        conn = db.connect(self.target)
        conn.execute("INSERT INTO liraa_estrato_quarteiroes VALUES (2,1,1,'0409')")
        conn.commit()
        conn.close()
        cases = [envio("fora-sorteio", "409"), envio("fora-estrato", "410"),
                 envio("fora-periodo", "408,1", data="2026-11-01")]
        preview = liraa_kobo.previa(self.target, 1, cases)
        self.assertEqual([r["situacao_vinculo"] for r in preview],
                         ["fora_do_sorteio", "fora_do_estrato", "fora_do_periodo"])
        self.assertIsNone(preview[-1]["id_estrato"])

    def test_capivara_rural_nao_recebe_vinculo(self):
        item = liraa_kobo._normalizar(envio("rural", "408.1", localidade="Capivara dos Manfron"))
        conn = db.connect(self.target)
        try:
            _, estrato, status = liraa_kobo._vincular(item, liraa_kobo._contexto(conn, 1))
        finally:
            conn.close()
        self.assertIsNone(estrato)
        self.assertEqual(status, "area_rural_fora_liraa")

    def test_lote_invalido_desfaz_tudo(self):
        with self.assertRaises(liraa_kobo.LiraaKoboError):
            liraa_kobo.importar(self.target, 1, [envio("valida"), envio("invalida", "A")])
        self.assertEqual(liraa_kobo.listar(self.target), [])

    def test_ciclo_e_estrato_com_visitas_nao_sao_excluidos(self):
        liraa_kobo.importar(self.target, 1, [envio("permanente")])
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.excluir_estrato(self.target, 2)
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.excluir_ciclo(self.target, 1)

    def test_vinculo_mostrado_reflete_sorteio_atual(self):
        liraa_kobo.importar(self.target, 1, [envio("atual")])
        self.assertEqual(liraa_kobo.listar(self.target)[0]["situacao_vinculo"], "sorteado")
        conn = db.connect(self.target)
        conn.execute("DELETE FROM liraa_sorteios WHERE id_estrato=2")
        conn.commit()
        conn.close()
        self.assertEqual(liraa_kobo.listar(self.target)[0]["situacao_vinculo"], "estrato_sem_sorteio")

    def test_configuracao_liraa_nao_ativa_importador_geral(self):
        self.assertNotIn("LIRAA", kobo_api.ALL_TYPES)
        cfg = kobo_api.default_config()
        self.assertIn("LIRAA", cfg["assets"])
        config_path = Path(self.target).with_suffix(".json")
        kobo_api.save_config(config_path, {"assets": {"LIRAA": "anXWARrB2YkHK5W9YTwDfU"}})
        self.assertEqual(kobo_api.load_config(config_path)["assets"]["LIRAA"],
                         "anXWARrB2YkHK5W9YTwDfU")
        kobo_api.save_config(config_path, {"assets": {"PVE": "pve-teste"}})
        self.assertEqual(kobo_api.load_config(config_path)["assets"]["LIRAA"],
                         "anXWARrB2YkHK5W9YTwDfU")

    def test_consulta_rejeita_resposta_truncada_e_periodo_invalido(self):
        app = Flask(__name__)
        config_path = Path(self.target).with_suffix(".json")
        app.config["KOBO_CONFIG_PATH"] = str(config_path)
        kobo_api.save_config(config_path, {"assets": {"LIRAA": "anXWARrB2YkHK5W9YTwDfU"}})
        with app.app_context():
            with patch.object(liraa_routes.kobo_api, "fetch_submissions",
                              return_value=([envio("um")], {"count": 2, "next": None})):
                with self.assertRaisesRegex(liraa_kobo.LiraaKoboError, "retornou 1 de 2"):
                    liraa_routes._buscar_kobo("2026-10-01", "2026-10-06")
            with self.assertRaisesRegex(liraa_kobo.LiraaKoboError, "período"):
                liraa_routes._buscar_kobo("2026-10-07", "2026-10-06")


if __name__ == "__main__":
    unittest.main()
