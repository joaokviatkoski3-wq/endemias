"""Regressões de integridade, agenda e previsão com massa exclusivamente fictícia."""
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import pandas as pd

import app
from app_core import auth, db, esporotricose, meteorologia, sessoes
from blueprints import acoes_setor
from scripts.preparar_massa_web_teste import preparar


class CorrecoesAmbientalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".venv")
        cls.base = Path(cls.tmp.name)
        cls.seed = cls.base / "seed.db"
        preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.base))
        self.path = self.directory / "ficticio.db"
        shutil.copyfile(self.seed, self.path)
        config = dict(
            DB_PATH=str(self.path), DB_BACKEND="sqlite", TESTING=True,
            WTF_CSRF_ENABLED=False, SETORES_ENABLED=True, TERMOS_USO_ENABLED=False,
            INSTANCE_DIR=str(self.directory), SECRET_KEY_PATH=str(self.directory / "secret.key"),
            LOG_PATH=str(self.directory / "teste.log"), ANEXOS_DIR=str(self.directory / "anexos"),
            BACKUP_DIR=str(self.directory / "backups"), BACKUP_COMPLETO_DIR=str(self.directory / "completos"),
            UPLOAD_TEMP=str(self.directory / "uploads"), KOBO_CONFIG_PATH=str(self.directory / "kobo.json"),
        )
        with mock.patch.object(app, "_configure_logging"):
            self.apps = {s: app.create_app({**config, "SETOR": s}) for s in ("endemias", "ambiental")}
        self.visit = "ficticio-esporotricose_visitas"

    def client(self, sector):
        application = self.apps[sector]
        client = application.test_client()
        user = db.query_one(str(self.path), "SELECT * FROM usuarios WHERE id_usuario=1")
        with application.app_context(), client.session_transaction() as session:
            session.update(uid=1, nome=user["nome"], auth_token=auth.token_sessao(user["senha_hash"]),
                           sessao_id=sessoes.criar(str(self.path), user))
        return client

    def visit_row(self):
        return next(row for row in esporotricose.listar_visitas(str(self.path))["registros"] if row["id_visita"] == self.visit)

    def test_edicao_neutra_preserva_endereco_e_vinculo_do_imovel(self):
        conn = db.connect(str(self.path))
        try:
            esporotricose._vincular_visita_exatamente(conn, self.visit)
            conn.commit()
        finally:
            conn.close()
        before = db.query_one(str(self.path), "SELECT * FROM esporotricose_visita_imoveis WHERE id_visita=?", (self.visit,))
        registro = self.visit_row()
        payload = {key: registro[key] for key in ("data", "hora_inicio", "localidade", "quarteirao", "tipo_imovel", "logradouro", "numero", "morador", "telefone", "visita", "deseja_cadastrar_animal", "agente_ids")}
        with mock.patch.object(esporotricose, "_vincular_visita_exatamente", wraps=esporotricose._vincular_visita_exatamente) as vincular:
            response = self.client("ambiental").put(f"/api/esporotricose/visitas/{self.visit}", json=payload)
        self.assertEqual(response.status_code, 200)
        vincular.assert_not_called()
        self.assertEqual(self.visit_row()["logradouro"], "Rua Ficticia")
        self.assertEqual(self.visit_row()["numero"], "10")
        self.assertEqual(db.query_one(str(self.path), "SELECT * FROM esporotricose_visita_imoveis WHERE id_visita=?", (self.visit,)), before)

    def test_ids_da_equipe_atualizam_texto_e_filtros(self):
        esporotricose.atualizar_visita(str(self.path), self.visit, {"agente_ids": [2, 2], "agentes_texto": "Texto antigo"})
        registro = self.visit_row()
        self.assertEqual(registro["agente_ids"], [2])
        self.assertEqual(registro["agentes_texto"], "Outro Agente Ficticio")
        self.assertEqual(registro["agentes"], "Outro Agente Ficticio")
        self.assertEqual(esporotricose.listar_visitas(str(self.path), {"agente": "Agente Ficticio"})["total"], 0)
        self.assertEqual(esporotricose.listar_visitas(str(self.path), {"agente": "Outro Agente Ficticio", "busca": "Rua Ficticia"})["total"], 1)

    def test_edicao_legada_de_texto_reconcilia_vinculos(self):
        esporotricose.atualizar_visita(str(self.path), self.visit, {"agentes_texto": "Outro Agente Ficticio"})
        self.assertEqual(self.visit_row()["agente_ids"], [2])

    def test_falha_ao_reconciliar_equipe_reverte_toda_edicao(self):
        before = self.visit_row()
        with mock.patch.object(esporotricose, "_inserir_agentes", side_effect=RuntimeError("Falha fictícia")):
            with self.assertRaises(RuntimeError):
                esporotricose.atualizar_visita(str(self.path), self.visit, {"agentes_texto": "Outro Agente Ficticio", "localidade": "Localidade Nova Ficticia"})
        after = self.visit_row()
        self.assertEqual(after["localidade"], before["localidade"])
        self.assertEqual(after["agentes_texto"], before["agentes_texto"])
        self.assertEqual(after["agente_ids"], before["agente_ids"])
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM localidades WHERE nome='Localidade Nova Ficticia'"), 0)

    def test_id_de_agente_invalido_nao_grava_parcialmente(self):
        before = self.visit_row()
        for values in ([99999], [True], "2", [-1]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                esporotricose.atualizar_visita(str(self.path), self.visit, {"agente_ids": values, "numero": "99"})
        self.assertEqual(self.visit_row()["numero"], before["numero"])
        self.assertEqual(self.visit_row()["agente_ids"], before["agente_ids"])

    def test_busca_ferido_aparece_somente_na_agenda_ambiental_e_impressao(self):
        animal = "animal-ficticio"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT INTO esporotricose_animais(id_animal,id_visita,kobo_uuid,especie,nome,processado_em) VALUES(?,?,?,?,?,?)", (animal, self.visit, "uuid-animal-ficticio", "Gato", "Animal Ficticio", "2026-06-01"))
        busca = esporotricose.salvar_busca_ferido(str(self.path), animal, {"data_busca": "2026-06-02", "agente": "Agente Ficticio", "observacoes": "Busca fictícia"})
        eventos = self.client("ambiental").get("/api/agenda/eventos?start=2026-06-02&end=2026-06-03").get_json()
        buscas = [r for r in eventos if r["extendedProps"].get("tipo") == "busca_ferido"]
        self.assertEqual(len(buscas), 1)
        self.assertEqual(buscas[0]["id"], f"auto_ESPOROTRICOSE_2026-06-02_busca_{busca['id_busca']}")
        self.assertEqual(buscas[0]["start"], "2026-06-02")
        self.assertIn("Busca de animal ferido", self.client("ambiental").get("/agenda/imprimir?ano=2026&mes=6").get_data(as_text=True))
        endemias = self.client("endemias").get("/api/agenda/eventos?start=2026-06-02&end=2026-06-03").get_json()
        self.assertFalse(any(r["extendedProps"].get("tipo") == "busca_ferido" for r in endemias))

    def test_intervalos_invalidos_do_calendario_sao_400_nos_dois_setores(self):
        for sector in self.apps:
            for query in ("", "?start=2026-06-01", "?start=2026-02-30&end=2026-03-02", "?start=0000-01-01&end=2026-06-03", "?start=2026-06-03&end=2026-06-02", "?start=2026-06-03&end=2026-06-03"):
                with self.subTest(sector=sector, query=query):
                    response = self.client(sector).get("/api/agenda/eventos" + query)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("erro", response.get_json())
            self.assertEqual(self.client(sector).get("/api/agenda/eventos?start=2026-06-01T00:00:00-03:00&end=2026-07-01T00:00:00-03:00").status_code, 200)
            self.assertEqual(self.client(sector).get("/agenda/imprimir?ano=2026&mes=13").status_code, 400)

    def test_acao_rejeita_fim_anterior_e_aceita_travessia_com_data_final(self):
        payload = {"tipo": "outro", "data": "2026-06-01", "periodo": "integral", "hora_inicio": "18:00", "hora_fim": "08:00"}
        before = db.scalar(str(self.path), "SELECT COUNT(*) FROM acoes_setor")
        client = self.client("endemias")
        self.assertEqual(client.post("/api/acoes-setor", json=payload).status_code, 400)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM acoes_setor"), before)
        payload["data_fim"] = "2026-06-02"
        response = client.post("/api/acoes-setor", json=payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        payload["hora_inicio"] = "08:00"
        payload["hora_fim"] = "18:00"
        payload.pop("data_fim")
        self.assertEqual(acoes_setor._acao_payload(payload)["hora_fim"], "18:00")

    def test_parser_separa_raca_de_outro_animal(self):
        for canonical in (False, True):
            with self.subTest(canonical=canonical):
                path = self.directory / f"animais-{canonical}.xlsx"
                fields = {"Dados do animal/Qual animal?": "Coelho Ficticio", "Dados do animal/Raça:": "Raça Fictícia"} if canonical else {"Qual_animal": "Coelho Ficticio", "Esp_cie": "Raça Fictícia"}
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    pd.DataFrame([{"_uuid": "uuid-ficticio", "_index": 1, "Data": "2026-06-01"}]).to_excel(writer, sheet_name="dados", index=False)
                    pd.DataFrame([{**fields, "_submission__uuid": "uuid-ficticio", "_index": 1, "Nome_do_animal": "Animal Ficticio"}]).to_excel(writer, sheet_name="Dados do animal", index=False)
                _, animais = esporotricose.parse_workbook(path, estrutura="nova")
                self.assertEqual(animais[0]["outro_animal"], "Coelho Ficticio")
                self.assertEqual(animais[0]["raca"], "Raça Fictícia")


class PrevisaoCompletaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "previsao.db"
        meteorologia.ensure_schema(self.path)

    def previsao(self, values):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            cols = ["previsto_em", "fonte", "importado_em", *values]
            params = ["2026-06-01T09:00", "Ensaio", "2026-06-01T08:00", *values.values()]
            conn.execute(f"INSERT INTO meteorologia_previsoes_horarias({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", params)
        return meteorologia.resumo_trabalho(self.path, inicio="2026-06-01", dias_uteis=1)["dias"][0]

    def test_linha_vazia_ou_parcial_nao_e_favoravel(self):
        self.assertEqual(self.previsao({})["nivel"], "sem_dados")
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM meteorologia_previsoes_horarias")
        parcial = self.previsao({"temperatura": 22, "codigo_tempo": 1})
        self.assertEqual(parcial["nivel"], "sem_dados")
        self.assertTrue(parcial["previsao_incompleta"])
        self.assertNotIn("sem risco", parcial["resumo"])

    def test_risco_confirmado_nao_desaparece_em_previsao_parcial(self):
        parcial = self.previsao({"codigo_tempo": 95})
        self.assertEqual(parcial["nivel"], "critico")
        self.assertTrue(parcial["previsao_incompleta"])

    def test_previsao_completa_sem_risco_pode_ser_favoravel(self):
        complete = self.previsao({"temperatura": 22, "codigo_tempo": 1, "rajada_vento": 5, "sensacao_termica": 22, "probabilidade_chuva": 0, "precipitacao": 0})
        self.assertEqual(complete["nivel"], "favoravel")
        self.assertFalse(complete["previsao_incompleta"])
