import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class EsporotricoseVinculoDoenteTests(unittest.TestCase):
    def _banco_com_visita(self):
        tempdir = tempfile.TemporaryDirectory()
        db_path = Path(tempdir.name) / "esporotricose.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE localidades (
                   id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE,
                   cod_localidade INTEGER
               )"""
        )
        esporotricose.ensure_schema(conn)
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                   id_visita, kobo_uuid, data, agentes_texto, localidade, quarteirao,
                   logradouro, numero, morador, telefone, visita, observacoes,
                   origem_estrutura, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "visita-1", "uuid-visita-1", "2026-07-10", "Ana Beatriz",
                "Tanguá", 1201, "Rua das Flores", "25", "Maria Silva",
                "41999990000", "Normal", "Retorno solicitado", "nova",
                "2026-07-10T10:00:00",
            ),
        )
        conn.execute(
            """INSERT INTO esporotricose_animais(
                   id_animal, id_visita, kobo_uuid, especie, nome, sexo, feridas,
                   regiao_ferida, atendimento_veterinario, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "animal-1", "visita-1", "uuid-animal-1", "Gato", "Mimi",
                "Fêmea", "Sim", "Face", "Sim", "2026-07-10T10:00:00",
            ),
        )
        conn.commit()
        conn.close()
        return tempdir, str(db_path)

    def test_prepara_formulario_com_dados_da_visita(self):
        tempdir, db_path = self._banco_com_visita()
        self.addCleanup(tempdir.cleanup)

        cadastro = esporotricose.preparar_doente_de_visita(db_path, "animal-1")

        self.assertIsNotNone(cadastro)
        self.assertIsNone(cadastro["id_animal_doente"])
        self.assertEqual(cadastro["animal"]["nome"], "Mimi")
        self.assertEqual(cadastro["animal"]["tutor"], "Maria Silva")
        self.assertEqual(cadastro["animal"]["especie"], "Gato")
        self.assertEqual(cadastro["animal"]["endereco"], "Rua das Flores, 25")
        self.assertEqual(cadastro["animal"]["status"], "Aguardando documentos")
        self.assertIn("Feridas informadas: Sim", cadastro["animal"]["observacoes_entomologica"])

    def test_salva_vinculo_e_nao_sobrescreve_doente_apos_mudanca_na_visita(self):
        tempdir, db_path = self._banco_com_visita()
        self.addCleanup(tempdir.cleanup)
        cadastro = esporotricose.preparar_doente_de_visita(db_path, "animal-1")

        id_doente = esporotricose.salvar_doente(db_path, cadastro["animal"])
        animais = esporotricose.listar_animais(db_path, {})["registros"]
        self.assertEqual(animais[0]["id_animal_doente"], id_doente)

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("UPDATE esporotricose_animais SET nome='Nome alterado no Kobo' WHERE id_animal='animal-1'")
            conn.commit()
        finally:
            conn.close()

        doente = esporotricose.obter_doente(db_path, id_doente)
        self.assertEqual(doente["nome"], "Mimi")
        self.assertEqual(doente["origens_visita"][0]["id_animal_visita"], "animal-1")

    def test_segunda_origem_igual_reaproveita_o_mesmo_doente(self):
        tempdir, db_path = self._banco_com_visita()
        self.addCleanup(tempdir.cleanup)
        primeiro = esporotricose.preparar_doente_de_visita(db_path, "animal-1")
        id_doente = esporotricose.salvar_doente(db_path, primeiro["animal"])
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """INSERT INTO esporotricose_animais(
                       id_animal, id_visita, kobo_uuid, especie, nome, sexo, feridas, processado_em
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                ("animal-2", "visita-1", "uuid-animal-2", "Gato", "Mimi", "Fêmea", "Sim", "2026-07-11T10:00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        segundo = esporotricose.preparar_doente_de_visita(db_path, "animal-2")
        id_reaproveitado = esporotricose.salvar_doente(db_path, segundo["animal"])

        self.assertEqual(id_reaproveitado, id_doente)
        conn = sqlite3.connect(db_path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM esporotricose_doentes_animais").fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM esporotricose_doentes_origens").fetchone()[0],
                2,
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
