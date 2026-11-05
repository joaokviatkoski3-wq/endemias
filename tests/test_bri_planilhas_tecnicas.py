"""BRI em XLSX rotulado/tecnico/agrupado, com respostas inventadas."""
import tempfile
import unittest
import sqlite3
from pathlib import Path

import pandas as pd

from app_core import bri, kobo_api, pontos_estrategicos


ROOT = Path(__file__).resolve().parents[1]


class BriPlanilhasTecnicasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "BRI_ficticio.xlsx"

    def parse(self, records):
        pd.DataFrame(records).to_excel(self.path, index=False)
        return bri.preparar_arquivo(self.path)

    def technical(self, destino="outro", pos=1):
        row = {"_uuid": "uuid-ficticio-" + str(pos), "_id": 1000 + pos,
            "Digite_a_data": "2026-10-03", "Digite_a_hora": "08:30",
            "Onde_vai_ser_realizado_o_trata": destino,
            "Quantidade_de_carga": 2.75, "Quantidade_carga": 1.25,
            "Foi_tratado_algum_im_vel_al_m_": "sim", "Qual_im_vel": "Imovel ficticio adicional",
            "Quantidade_dep_sitos_tratados": 3,
            "Nome_do_s_agente_s/AgenteFicticio": 1,
            "Nome_do_s_agente_s/OutroFicticio": 0}
        groups = {"ponto_estrat_gico": ("localidade", "logradouro", "quarteirao", "numero"),
            "ovitrampa": ("localidade_001_002", "Logradouro_002", "Quarteir_o_001", "N_mero_001"),
            "outro": ("localidade_001", "Logradouro_001", "Quarteir_o", "N_mero")}
        for names in groups.values():
            row.update(dict.fromkeys(names))
        row.update(dict(zip(groups[destino], ("Localidade Ficticia", "Rua Ficticia", "123", "10"))))
        if destino == "ovitrampa":
            row["N_mero_da_Ovitrampa"] = "FIC-99"
        if destino == "outro":
            row["Onde_foi_realizado_o_tratamento"] = "Local ficticio"
        return row

    def test_exportacao_tecnica_com_treze_linhas_preserva_uuid_campos_e_decimal(self):
        records = [self.technical(("ponto_estrat_gico", "ovitrampa", "outro")[i % 3], i) for i in range(13)]
        estrutura, parsed = self.parse(records)
        self.assertEqual(estrutura, "nova")
        self.assertEqual(len(parsed), 13)
        self.assertEqual([r["kobo_uuid"] for r in parsed], [r["_uuid"] for r in records])
        for pos, row in enumerate(parsed):
            self.assertEqual(row["kobo_id"], 1000 + pos)
            self.assertEqual(row["quantidade_carga"], 2.75)
            self.assertEqual(row["quantidade_carga_extra"], 1.25)
            self.assertEqual(row["depositos_tratados_extra"], 3)
            self.assertEqual(row["localidade"], "Localidade Ficticia")
            self.assertEqual(row["logradouro"], "Rua Ficticia")
            self.assertEqual(row["quarteirao"], 123)
            self.assertEqual(row["numero"], "10")
            self.assertEqual(row["tratou_imovel_extra"], "Sim")
            self.assertEqual(row["qual_imovel_extra"], "Imovel ficticio adicional")
            self.assertEqual(row["agentes_texto"], "AgenteFicticio")
        self.assertEqual([r["destino_tratamento"] for r in parsed[:3]], ["Ponto Estratégico", "Ovitrampa", "Outro"])
        self.assertEqual(parsed[1]["numero_ovitrampa"], "FIC-99")

    def test_cabecalhos_group_paths_tem_mesma_identidade_e_endereco(self):
        for destino, group in (("ponto_estrat_gico", "group_zn1kq42"), ("ovitrampa", "group_cu8sh31"), ("outro", "group_pt6ft99")):
            with self.subTest(destino=destino):
                raw = self.technical(destino)
                flat = {k: v for k, v in raw.items() if v is not None}
                original = self.parse([flat])[1][0]
                grouped = {}
                for key, value in flat.items():
                    if key in {"_uuid", "_id", "Onde_vai_ser_realizado_o_trata"} or "/" in key:
                        grouped[key] = value
                    elif key in {"Digite_a_data", "Digite_a_hora"}:
                        grouped["Dados/" + key] = value
                    elif key in {"Quantidade_de_carga", "Quantidade_carga", "Foi_tratado_algum_im_vel_al_m_", "Qual_im_vel", "Quantidade_dep_sitos_tratados"}:
                        grouped["group_rb5ho54/" + key] = value
                    else:
                        grouped[group + "/" + key] = value
                parsed = self.parse([grouped])[1][0]
                for name in ("id_bri", "kobo_uuid", "data", "hora", "localidade", "logradouro", "quarteirao", "numero", "quantidade_carga", "quantidade_carga_extra"):
                    self.assertEqual(parsed[name], original[name], name)

    def test_formato_rotulado_sem_start_end_preserva_uuid_e_equivale_ao_tecnico(self):
        for destino in ("ponto_estrat_gico", "ovitrampa", "outro"):
            with self.subTest(destino=destino):
                raw = self.technical(destino)
                technical = self.parse([raw])[1][0]
                labels = kobo_api._bri_row(raw)
                labels = {k: v for k, v in labels.items() if "_" not in k and k != "start" and k != "end" or k in {"_uuid", "_id"}}
                labels["Digite a data"] = "2026-10-03"
                if destino == "ovitrampa":
                    labels["Onde vai ser realizado o tratamento?"] = "Local com Ovitrampa"
                parsed = self.parse([labels])[1][0]
                self.assertEqual(parsed["id_bri"], technical["id_bri"])
                self.assertEqual(parsed["kobo_uuid"], raw["_uuid"])
                self.assertEqual(parsed["quantidade_carga"], 2.75)
                self.assertEqual(parsed["quarteirao"], 123)

    def test_rotulo_vazio_nao_esconde_nome_tecnico_populado(self):
        raw = self.technical()
        raw.update({"Digite a data": None, "Digite a hora": None,
            "Quantidade de carga": None, "Quantidade de carga.1": None,
            "Onde vai ser realizado o tratamento?": None, "Localidade": None})
        parsed = self.parse([raw])[1][0]
        self.assertEqual(parsed["data"], "2026-10-03")
        self.assertEqual(parsed["hora"], "08:30")
        self.assertEqual(parsed["quantidade_carga"], 2.75)
        self.assertEqual(parsed["quantidade_carga_extra"], 1.25)
        self.assertEqual(parsed["destino_tratamento"], "Outro")

    def test_carga_principal_extra_zero_e_ausencia_nao_sao_confundidos(self):
        for main, extra in ((None, 0), (0, None), (None, 4.5), (2.75, 1.25)):
            with self.subTest(main=main, extra=extra):
                raw = self.technical()
                raw.update(Quantidade_de_carga=main, Quantidade_carga=extra)
                row = self.parse([raw])[1][0]
                self.assertEqual(row["quantidade_carga"], main)
                self.assertEqual(row["quantidade_carga_extra"], extra)

    def test_endereco_de_grupo_inativo_nao_preenche_destino_sem_endereco(self):
        raw = self.technical("ponto_estrat_gico")
        for key in ("localidade", "logradouro", "quarteirao", "numero"):
            raw[key] = None
        raw.update(Localidade="Outro local ficticio", Logradouro="Rua inativa", Quarteirão=999, Número=999)
        parsed = self.parse([raw])[1][0]
        self.assertIsNone(parsed["localidade"])
        self.assertIsNone(parsed["logradouro"])
        self.assertIsNone(parsed["quarteirao"])
        self.assertIsNone(parsed["numero"])

    def test_legado_rotulado_sem_uuid_conserva_hash_e_texto_da_equipe(self):
        raw = {"SISPNCD": "FIC/2026", "Data": "2026-10-03", "Hora": "08:30",
            "Localidade": "Localidade Ficticia", "Logradouro": "Rua Ficticia", "Número": "10",
            "Agentes": "Equipe Ficticia Integral", "Quantidade de carga": 2.5}
        estrutura, rows = self.parse([raw])
        self.assertEqual(estrutura, "legada")
        row = rows[0]
        self.assertIsNone(row["kobo_uuid"])
        self.assertEqual(row["id_bri"], bri._hash("bri", "legada", "0|FIC/2026|2026-10-03|08:30|Localidade Ficticia|Rua Ficticia|10"))
        self.assertEqual(row["agentes_texto"], "Equipe Ficticia Integral")

    def test_sem_data_da_visita_nao_substitui_pelo_start(self):
        raw = self.technical()
        raw.update(Digite_a_data=None, start="2026-10-03T08:00:00", end="2026-10-03T09:00:00")
        self.assertEqual(self.parse([raw])[1], [])

    def test_prioridade_da_data_e_consistente_com_adaptador_api(self):
        raw = {"Data": "2001-01-01", **self.technical()}
        parsed = self.parse([raw])[1][0]
        adapted = self.parse([kobo_api._bri_row(raw)])[1][0]
        self.assertEqual(parsed["data"], "2026-10-03")
        self.assertEqual(parsed["data"], adapted["data"])

    def test_legado_com_coluna_numerica_parcial_conserva_chave_antiga(self):
        raw = {"SISPNCD": "FIC/2026", "Data": "2026-10-03", "Hora": "08:30",
            "Localidade": "Localidade Ficticia", "Logradouro": "Rua Ficticia", "Número": 70.0}
        rows = self.parse([raw, {**raw, "Número": None}])[1]
        self.assertEqual(rows[0]["numero"], "70.0")
        self.assertEqual(rows[0]["id_bri"], bri._hash("bri", "legada", "0|FIC/2026|2026-10-03|08:30|Localidade Ficticia|Rua Ficticia|70.0"))

    def test_api_json_workbook_processamento_e_banco_preservam_campos_e_idempotencia(self):
        class Log:
            def log(self, *args, **kwargs):
                pass

        records = []
        for pos, (destino, number, key) in enumerate((("ponto_estrat_gico", 70.0, "numero"), ("ovitrampa", "007", "N_mero_001"), ("outro", "SN", "N_mero")), 1):
            row = self.technical(destino, pos)
            row[key] = number
            records.append(row)
        paths = kobo_api.write_etl_workbooks({"BRI": records}, ROOT / "config.json", self.temp.name)
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript("CREATE TABLE localidades(id_localidade INTEGER PRIMARY KEY,nome TEXT UNIQUE,cod_localidade TEXT); CREATE TABLE agentes(id_agente INTEGER PRIMARY KEY,nome TEXT UNIQUE);")
            pontos_estrategicos.ensure_schema(conn)
            bri.ensure_schema(conn)
            result = bri.processar_arquivo(paths[0], conn, Log(), "2026-11-05", schema_ready=True)
            self.assertEqual(result["visitas_novas"], 3)
            rows = conn.execute("SELECT * FROM bri_registros ORDER BY kobo_id").fetchall()
            self.assertEqual([r["numero"] for r in rows], ["70", "007", "SN"])
            self.assertEqual([r["kobo_uuid"] for r in rows], [r["_uuid"] for r in records])
            self.assertEqual([r["quantidade_carga"] for r in rows], [2.75] * 3)
            self.assertEqual([r["quantidade_carga_extra"] for r in rows], [1.25] * 3)
            conn.execute("UPDATE bri_registros SET quantidade_carga=99 WHERE kobo_id=1001")
            repeated = bri.processar_arquivo(paths[0], conn, Log(), "2026-11-05", schema_ready=True)
            self.assertEqual(repeated["visitas_novas"], 0)
            self.assertEqual(repeated["duplicadas"], 3)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM bri_registros").fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT quantidade_carga FROM bri_registros WHERE kobo_id=1001").fetchone()[0], 99)
