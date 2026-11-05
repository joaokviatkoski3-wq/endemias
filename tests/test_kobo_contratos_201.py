"""Contratos de importacao com respostas inteiramente ficticias, sem rede."""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import etl
from app_core import amostras_animais, bri, esporotricose, kobo_api
from blueprints import relatorio_agente
from tests import test_visitas_postgresql_compat as visita_fixture


ROOT = Path(__file__).resolve().parents[1]


class Log:
    def log(self, *args, **kwargs):
        pass


class KoboContratos201Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    def workbook(self, tipo, record):
        return kobo_api.write_etl_workbooks(
            {tipo: [record]}, ROOT / "config.json", self.base,
        )[0]

    def test_bri_tres_destinos_preservam_decimal_endereco_e_imovel_extra(self):
        branches = [
            ("ponto_estrat_gico", "Ponto Estratégico", "group_zn1kq42", ("localidade", "logradouro", "quarteirao", "numero")),
            ("ovitrampa", "Ovitrampa", "group_cu8sh31", ("localidade_001_002", "Logradouro_002", "Quarteir_o_001", "N_mero_001")),
            ("outro", "Outro", "group_pt6ft99", ("localidade_001", "Logradouro_001", "Quarteir_o", "N_mero")),
        ]
        for code, label, group, names in branches:
            with self.subTest(destino=code):
                record = {
                    "_uuid": "bri-ficticio-" + code, "Digite_a_data": "2026-06-03",
                    "Digite_a_hora": "08:00", "start": "2026-06-03T08:00:00", "end": "2026-06-03T08:30:00",
                    "Onde_vai_ser_realizado_o_trata": code,
                    "group_rb5ho54/Quantidade_de_carga": "2.5",
                    "group_rb5ho54/Foi_tratado_algum_im_vel_al_m_": "sim",
                    "group_rb5ho54/Qual_im_vel": "Imovel ficticio adicional",
                    "group_zn1kq42/localidade": "Localidade antiga",
                    "group_zn1kq42/logradouro": "Endereco antigo",
                    "group_zn1kq42/quarteirao": 999,
                    "group_zn1kq42/numero": "999",
                }
                record.update({group + "/" + name: value for name, value in zip(names, ("Localidade Ficticia", "Rua Ficticia", "123", "45"))})
                if code == "ovitrampa":
                    record[group + "/N_mero_da_Ovitrampa"] = "99"
                parsed = bri.parse_workbook(self.workbook("BRI", record))[0]
                self.assertEqual(parsed["kobo_uuid"], record["_uuid"])
                self.assertEqual(parsed["destino_tratamento"], label)
                self.assertEqual(parsed["quantidade_carga"], 2.5)
                self.assertEqual(parsed["localidade"], "Localidade Ficticia")
                self.assertEqual(parsed["logradouro"], "Rua Ficticia")
                self.assertEqual(parsed["quarteirao"], 123)
                self.assertEqual(parsed["numero"], "45")
                self.assertEqual(parsed["tratou_imovel_extra"], "Sim")
                self.assertEqual(parsed["qual_imovel_extra"], "Imovel ficticio adicional")
                if code == "ovitrampa":
                    self.assertEqual(parsed["numero_ovitrampa"], "99")

    def test_bri_planilha_por_rotulos_aceita_destino_atual_e_distingue_ausencia_de_zero(self):
        path = self.base / "BRI_rotulos.xlsx"
        records = [{
            "_uuid": "bri-rotulo-" + str(i), "Digite a data": "2026-06-03",
            "Onde vai ser realizado o tratamento?": "Local com Ovitrampa",
            "Localidade.1": "Localidade Ficticia", "Logradouro.1": "Rua Ficticia",
            "Quarteirão.1": 123, "Número.1": "45", "Quantidade de carga": carga,
        } for i, carga in enumerate((None, 0, 2.5))]
        pd.DataFrame(records).to_excel(path, index=False)
        parsed = bri.parse_workbook(path, estrutura="nova")
        self.assertEqual([r["quantidade_carga"] for r in parsed], [None, 0, 2.5])
        self.assertTrue(all(r["destino_tratamento"] == "Ovitrampa" and r["quarteirao"] == 123 for r in parsed))

    def test_visitas_sequencias_sanepar_ciclo_e_horarios_chegam_ao_banco(self):
        fixture = visita_fixture.VisitasPostgresqlCompatTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        conn = fixture.conn
        conn.execute("ALTER TABLE visitas ADD COLUMN kobo_id INTEGER")
        conn.execute("ALTER TABLE visitas ADD COLUMN submission_time TEXT")
        conn.execute("ALTER TABLE visitas ADD COLUMN acs_presente TEXT")
        conn.execute("ALTER TABLE visitas ADD COLUMN acs_nome TEXT")
        from app_core import pontos_estrategicos
        pontos_estrategicos.ensure_schema(conn)
        for tipo in ("PE", "TB", "TBO", "PVE"):
            with self.subTest(tipo=tipo):
                record = {"start": "2026-06-03T07:00:00", "end": "2026-06-03T10:00:00", "_uuid": "visita-ficticia-" + tipo, "Data": "2026-06-03"}
                group = "Dados_visita" if tipo == "TBO" else "group_zn1kq42"
                record.update({group + "/Localidade": "Localidade Ficticia", group + "/Logradouro": "Rua Ficticia", group + "/Quarteir_o": 123, group + "/N_mero": 45})
                record["Digite_a_hora" if tipo == "PE" else "Hora_inicio" if tipo == "TBO" else "Hora"] = "08:00"
                if tipo == "PE":
                    record[group + "/Ciclo"] = 7
                else:
                    record[group + ("/Sequencia" if tipo == "TBO" else "/Sequ_ncia")] = "1,2,3"
                    record[("Agua_sanepar/Sanepar" if tipo == "TBO" else "grupo_ficticio/O_im_vel_possui_gua_rnecida_pela_Sanepar")] = "n_o" if tipo == "PVE" else "sim"
                if tipo == "TBO":
                    record["Hora_fim"] = "09:00"
                preparado = etl.preparar_arquivo(self.workbook(tipo, record), tipo, self.cfg["tipos_trabalho"][tipo], Log())
                rows = preparado["df_visitas"]
                self.assertEqual(len(rows), 1 if tipo == "PE" else 3)
                for _, row in rows.iterrows():
                    seq = etl.val_str(row.get("Sequência"))
                    etl.salvar_visita(conn.cursor(), etl.gerar_id_visita(record["_uuid"], seq), record["_uuid"], row, tipo, self.cfg["tipos_trabalho"][tipo], "2026-06-03", conn)
                saved = conn.execute("SELECT * FROM visitas WHERE kobo_uuid=? ORDER BY sequencia", (record["_uuid"],)).fetchall()
                self.assertEqual(len(saved), len(rows))
                self.assertEqual(saved[0]["hora_inicio"], "08:00")
                if tipo == "PE":
                    self.assertEqual(saved[0]["ciclo"], 7)
                else:
                    self.assertEqual([r["sequencia"] for r in saved], ["1", "2", "3"])
                    # A expansao historica conserva os dados da visita mae.
                    self.assertEqual(saved[0]["agua_sanepar"], 0 if tipo == "PVE" else 1)
                if tipo == "TBO":
                    self.assertEqual(saved[0]["hora_fim"], "09:00")
        legacy = pd.Series({**{f"col{i}": None for i in range(68)}, "Data": "2026-06-04", "Localidade": "Localidade Ficticia"})
        legacy.iloc[1] = "10:00"
        legacy.iloc[67] = "11:00"
        etl.salvar_visita(conn.cursor(), "visita-legada-ficticia", "uuid-legado-ficticio", legacy, "TBO", self.cfg["tipos_trabalho"]["TBO"], "2026-06-04", conn)
        saved = conn.execute("SELECT hora_inicio,hora_fim FROM visitas WHERE id_visita='visita-legada-ficticia'").fetchone()
        self.assertEqual(tuple(saved), ("10:00", "11:00"))

    def test_amostra_separa_motivacao_captura_e_especie_com_nomes_tecnicos(self):
        record = {
            "_uuid": "amostra-ficticia", "Data": "2026-06-03", "Hora": "08:00",
            "start": "2026-06-03T08:00:00", "end": "2026-06-03T09:00:00",
            "group_ny0er64/Motivo_da_visita": "investigacao", "group_ny0er64/Tipo_de_animal_001": "aranha",
            "group_zn1kq42/Localidade": "Localidade Ficticia", "group_zn1kq42/Logradouro": "Rua Ficticia",
            "group_zn1kq42/Quarteir_o": 123, "group_zn1kq42/N_mero": 45,
            "group_zn1kq42/Tipo_do_im_vel": "residencia", "group_zn1kq42/Sequ_ncia": "1",
            "group_zn1kq42/Ocorr_ncia_da_resid_ncia": "primeira", "Houve_captura": "sim",
            "group_qv2dg30/Tipo_de_animal": "escorpiao", "group_qv2dg30/Qual_a_esp_cie_do_escorpi_o": "especie_ficticia",
            "group_qv2dg30/Quantidade": 2,
        }
        parsed = amostras_animais.parse_workbook(self.workbook("AMOSTRA_ANIMAIS", record))[0]
        self.assertEqual(parsed["kobo_uuid"], record["_uuid"])
        self.assertEqual(parsed["animal_motivador"], "aranha")
        self.assertEqual(parsed["tipo_animal"], "escorpiao")
        self.assertEqual(parsed["especie_escorpiao"], "especie_ficticia")
        self.assertEqual(parsed["numero"], "45")
        self.assertEqual(parsed["quarteirao"], 123)
        self.assertEqual(parsed["sequencia"], "1")
        self.assertEqual(parsed["ocorrencia_residencia"], "primeira")
        self.assertEqual(parsed["quantidade"], 2)

    def test_repeat_animal_ignora_anexos_e_tem_indices_unicos(self):
        animal = lambda nome: {"group_tl0nq13/Escolha_o_animal_a_ser_cadastr": "outro", "group_tl0nq13/Nome_do_animal": nome, "group_tl0nq13/Qual_animal": "Animal ficticio", "group_tl0nq13/Esp_cie": "Raca ficticia"}
        record = {"_attachments": [{"filename": "ficticio.txt"}], "animais": [animal("Primeiro")], "grupo": {"outros_animais": [animal("Segundo")]}, "metadados": [{"filename": "outro.txt"}]}
        rows = kobo_api._repeat_group_rows(record, "uuid-ficticio", "7")
        self.assertEqual([r["_index"] for r in rows], ["1", "2"])
        self.assertTrue(all(r["_submission__uuid"] == "uuid-ficticio" and r["_parent_index"] == "7" for r in rows))
        self.assertTrue(all(r["Dados do animal/Qual animal?"] == "Animal ficticio" and r["Dados do animal/Raça:"] == "Raca ficticia" for r in rows))

    def test_esporo_planilha_preserva_animais_e_separa_qual_animal_da_raca(self):
        animal = lambda nome: {"group_tl0nq13/Escolha_o_animal_a_ser_cadastr": "outro", "group_tl0nq13/Nome_do_animal": nome, "group_tl0nq13/Qual_animal": "Animal ficticio", "group_tl0nq13/Esp_cie": "Raca ficticia"}
        record = {"_uuid": "esporo-ficticio", "start": "2026-06-03T08:00:00", "end": "2026-06-03T09:00:00", "group_su8jh28/Data": "2026-06-03", "_attachments": [{"filename": "ficticio.txt", "Nome_do_animal": "Metadado"}], "group_tl0nq13": [animal("Primeiro"), animal("Segundo")]}
        visitas, animais = esporotricose.parse_workbook(self.workbook("ESPOROTRICOSE", record), "nova")
        self.assertEqual(len(visitas), 1)
        self.assertEqual(len(animais), 2)
        self.assertEqual(len({a["id_animal"] for a in animais}), 2)
        self.assertEqual({a["nome"] for a in animais}, {"Primeiro", "Segundo"})
        self.assertTrue(all(a["outro_animal"] == "Animal ficticio" and a["raca"] == "Raca ficticia" for a in animais))

    def test_pdf_bri_preserva_decimal_e_zero(self):
        for value, text in [(2.5, "2,5 carga"), (20, "20 carga"), (0, "0 carga"), (None, "0 carga")]:
            with self.subTest(value=value):
                self.assertEqual(relatorio_agente._detalhe_atividade({"codigo": "BRI", "extras": {"carga": value}}), text)


class VisitaPeReconciliacao201Tests(unittest.TestCase):
    def setUp(self):
        from app_core import pontos_estrategicos, visitas
        self.visitas = visitas
        self.fixture = visita_fixture.VisitasPostgresqlCompatTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.conn = self.fixture.conn
        pontos_estrategicos.ensure_schema(self.conn)
        for ident, q, rua, num in ((1, 123, "Rua Alfa", "10"), (2, 124, "Rua Bravo", "20")):
            self.conn.execute("""INSERT INTO pontos_estrategicos(id_pe,codigo_pe,nome,localidade,id_localidade,quarteirao,logradouro,numero,criado_em,atualizado_em)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (ident, "PE-ficticio-" + str(ident), "PE Ficticio", "Lamenha", 1, q, rua, num, "2026-06-03", "2026-06-03"))
        self.conn.execute("UPDATE visitas SET tipo='PE',id_pe=1,codigo_pe='PE-ficticio-1' WHERE id_visita='visita-1'")
        self.conn.commit()

    def read(self):
        return self.conn.execute("SELECT id_pe,codigo_pe,quarteirao FROM visitas WHERE id_visita='visita-1'").fetchone()

    def test_mudanca_de_endereco_atualiza_identidade(self):
        self.visitas.editar(self.conn, "visita-1", {"quarteirao": 124, "logradouro": "Rua Bravo", "numero": "20"})
        self.assertEqual(tuple(self.read()), (2, "PE-ficticio-2", 124))

    def test_mudar_tipo_remove_vinculo_e_editar_observacao_o_preserva(self):
        self.visitas.editar(self.conn, "visita-1", {"observacoes": "Observacao ficticia nova"})
        self.assertEqual(tuple(self.read()), (1, "PE-ficticio-1", 123))
        self.visitas.editar(self.conn, "visita-1", {"tipo": "TB"})
        self.assertEqual(tuple(self.read()), (None, None, 123))

    def test_destino_desconhecido_remove_identidade_anterior(self):
        self.visitas.editar(self.conn, "visita-1", {"quarteirao": 125, "logradouro": "Rua Desconhecida"})
        self.assertEqual(tuple(self.read()), (None, None, 125))

    def test_endereco_ambiguo_recusa_alteracao_sem_mover_visita(self):
        self.conn.execute("""INSERT INTO pontos_estrategicos(codigo_pe,nome,localidade,id_localidade,quarteirao,logradouro,numero,criado_em,atualizado_em)
            VALUES('PE-ficticio-3','PE Ficticio','Lamenha',1,124,'Rua Bravo','20','2026-06-03','2026-06-03')""")
        self.conn.commit()
        with self.assertRaises(self.visitas.VisitaInvalida):
            self.visitas.editar(self.conn, "visita-1", {"quarteirao": 124, "logradouro": "Rua Bravo", "numero": "20"})
        self.assertEqual(tuple(self.read()), (1, "PE-ficticio-1", 123))
