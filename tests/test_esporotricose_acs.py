import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from app_core import esporotricose, kobo_api
from blueprints import processar


class _Logger:
    def log(self, _mensagem, _tipo="normal"):
        pass


class EsporotricoseAcsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = str(Path(self.tempdir.name) / "visitas.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE localidades(id_localidade INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, cod_localidade INTEGER)"
        )
        conn.execute("CREATE TABLE agentes(id_agente INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
        conn.execute("CREATE TABLE acs_catalogo(acs_codigo TEXT PRIMARY KEY, nome TEXT NOT NULL, atualizado_em TEXT NOT NULL)")
        esporotricose.ensure_schema(conn)
        conn.executemany(
            "INSERT INTO acs_catalogo(acs_codigo, nome, atualizado_em) VALUES (?,?,?)",
            (("ACS-006", "Ana da Silva", "2026-09-24"), ("ACS-053", "Bruno Lima", "2026-09-24")),
        )
        conn.commit()
        conn.close()

    def _linha(self, **alteracoes):
        linha = {
            "_uuid": "uuid-esporo-acs",
            "_id": 123,
            "start": "2026-09-24T09:00:00",
            "end": "2026-09-24T09:30:00",
            "meta/rootUuid": "uuid-esporo-acs",
            "Dados do morador/Hora Inicio": "09:00",
            "Hora Final": "09:30",
            "Dados do morador/Agentes": "João",
            "Dados do morador/Data": "2026-09-24",
            "Dados do morador/Localidade": "Tamboara",
            "Dados do morador/Quarteirão": 1405,
            "Dados do morador/Logradouro": "Rua das Flores",
            "Dados do morador/Número": "25",
            "grupo/acs_presente": "sim_acs_presente",
            "grupo/Qual_quais_ACS": "ACS-006 ACS-053 ACS-006",
        }
        linha.update(alteracoes)
        return linha

    def _importar(self, linha):
        arquivo = Path(self.tempdir.name) / "esporotricose_acs.xlsx"
        with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
            pd.DataFrame([linha]).to_excel(writer, sheet_name="dados", index=False)
            pd.DataFrame(columns=["_submission__uuid"]).to_excel(
                writer, sheet_name="Dados do animal", index=False
            )
        preparado = esporotricose.preparar_arquivo(arquivo)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            resultado = esporotricose.processar_arquivo(
                arquivo, conn, _Logger(), "2026-09-24T10:00:00", preparado=preparado
            )
            conn.commit()
            return resultado
        finally:
            conn.close()

    def test_importa_multiplos_acs_e_exibe_nomes_com_filtro_por_codigo(self):
        resultado = self._importar(self._linha())
        self.assertEqual(resultado["visitas_novas"], 1)
        visitas = esporotricose.listar_visitas(self.db_path, {"acs": ["ACS-053"]})
        self.assertEqual(visitas["total"], 1)
        visita = visitas["registros"][0]
        self.assertEqual(visita["acs_presente"], 1)
        self.assertEqual(visita["acs_codigos"], "ACS-006, ACS-053")
        self.assertEqual(visita["acs"], "Ana da Silva, Bruno Lima")
        self.assertEqual(esporotricose.listar_visitas(self.db_path, {"acs": ["OUTRO"]})["total"], 0)
        self.assertEqual(esporotricose.opcoes_acs_visitas(self.db_path), [
            {"codigo": "ACS-006", "nome": "Ana da Silva"},
            {"codigo": "ACS-053", "nome": "Bruno Lima"},
        ])
        conn = sqlite3.connect(self.db_path)
        id_imovel = conn.execute("SELECT id_imovel FROM esporotricose_visita_imoveis").fetchone()[0]
        conn.close()
        detalhe = esporotricose.detalhe_imovel(self.db_path, id_imovel)
        self.assertEqual(detalhe["visitas"][0]["acs"], "Ana da Silva, Bruno Lima")

    def test_reimportacao_sem_campo_preserva_acs_e_resposta_negativa_limpa(self):
        self._importar(self._linha())
        sem_pergunta = self._linha()
        del sem_pergunta["grupo/acs_presente"]
        del sem_pergunta["grupo/Qual_quais_ACS"]
        self.assertEqual(self._importar(sem_pergunta)["duplicadas"], 1)
        self.assertEqual(esporotricose.listar_visitas(self.db_path)["registros"][0]["acs_codigos"], "ACS-006, ACS-053")

        negativa = self._linha(**{"grupo/acs_presente": "nao_acs_presente"})
        self.assertEqual(self._importar(negativa)["duplicadas"], 1)
        visita = esporotricose.listar_visitas(self.db_path)["registros"][0]
        self.assertEqual(visita["acs_presente"], 0)
        self.assertEqual(visita["acs_codigos"], "")
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertIsNone(conn.execute(
                "SELECT acs_nome FROM esporotricose_visitas"
            ).fetchone()[0])
        finally:
            conn.close()

    def test_alias_acs_nome_e_catalogo_do_formulario_esporotricose(self):
        alias = self._linha(**{"grupo/acs_nome": "ACS-006"})
        del alias["grupo/Qual_quais_ACS"]
        self._importar(alias)
        self.assertEqual(esporotricose.listar_visitas(self.db_path)["registros"][0]["acs"], "Ana da Silva")

        conteudo = {
            "survey": [{"name": "Qual_quais_ACS", "type": "select_multiple", "select_from_list_name": "acs"}],
            "choices": [{"list_name": "acs", "name": "ACS-006", "label": "Ana da Silva"}],
        }
        self.assertEqual(kobo_api.catalogo_acs_do_conteudo(conteudo, "Esporotricose"), [
            {"codigo": "ACS-006", "nome": "Ana da Silva"}
        ])

    def test_atualizacao_do_catalogo_na_importacao_e_tolerante_a_falha(self):
        itens = [{"codigo": "ACS-006", "nome": "Ana da Silva"}]
        with (
            mock.patch.object(processar.kobo_api, "obter_catalogo_acs_formulario", return_value=itens),
            mock.patch.object(processar.visitas_core, "sincronizar_catalogo_acs", return_value={"total": 1}),
            mock.patch.object(processar, "_db_path", return_value=self.db_path),
            mock.patch.object(processar.audit, "registrar_evento"),
        ):
            self.assertEqual(processar._atualizar_catalogo_acs_esporotricose({}, "uid"), {"total": 1})
        with mock.patch.object(
            processar.kobo_api, "obter_catalogo_acs_formulario", side_effect=kobo_api.KoboError("sem rede")
        ):
            self.assertIsNone(processar._atualizar_catalogo_acs_esporotricose({}, "uid"))


if __name__ == "__main__":
    unittest.main()
