import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import formularios as f
from app_core import registro_geografico as rg_core
from app_core import rg_formulario


class RgFormularioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = db_core.DatabaseTarget("sqlite", str(Path(self.tmp.name) / "rg.db"))
        conn = db_core.connect(self.target)
        conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT)")
        conn.execute("INSERT INTO localidades (id_localidade, nome) VALUES (1, 'Sede')")
        conn.execute("CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER DEFAULT 1)")
        rg_core.ensure_schema(conn)
        f.ensure_schema(conn)
        conn.commit()
        conn.close()
        self.agente = {"id_usuario": 10, "nome": "Agente", "nivel": "usuario"}
        self.admin = {"id_usuario": 1, "nome": "Admin", "nivel": "admin"}

    def _payload(self):
        return {
            "id_localidade": 1,
            "quarteirao": "0408",
            "linhas": [
                {"logradouro": "Rua A", "numero": "10", "sequencia": "1", "lado": "par",
                 "tipo": "R", "condominio": 0, "observacao": ""},
                {"logradouro": "Rua A", "numero": "12", "sequencia": "2", "lado": "par",
                 "tipo": "C", "condominio": 0, "observacao": ""},
            ],
        }

    def test_snapshot_traz_logradouros_existentes_e_tipos(self):
        rg_core.salvar_quarteirao(self.target, self._payload())
        snap = rg_formulario.snapshot(self.target, [{"id_localidade": 1, "quarteirao": "0408"}])
        self.assertEqual(len(snap["selecoes"]), 1)
        self.assertIn("Rua A", snap["selecoes"][0]["logradouros"])
        self.assertTrue(any(t["codigo"] == "R" for t in snap["tipos"]))

    def test_oficializar_substitui_quarteirao(self):
        rg_core.salvar_quarteirao(self.target, {
            "id_localidade": 1, "quarteirao": "0408",
            "linhas": [{"logradouro": "Rua Antiga", "numero": "1", "tipo": "R"}],
        })
        novo_id = f.salvar(self.target, "rg_atualizacao", self._payload(), self.agente)
        f.revisar(self.target, novo_id, self._payload(), f.STATUS_APROVADO, self.admin)
        rg_formulario.oficializar(self.target, novo_id, self.admin)

        self.assertEqual(f.obter(self.target, novo_id)["status"], f.STATUS_OFICIALIZADO)
        conn = db_core.connect(self.target)
        try:
            rows = conn.execute(
                "SELECT logradouro FROM registro_geografico_imoveis WHERE id_localidade=1 AND quarteirao='0408'"
            ).fetchall()
        finally:
            conn.close()
        logradouros = {r["logradouro"] for r in rows}
        self.assertIn("Rua A", logradouros)
        self.assertNotIn("Rua Antiga", logradouros)

    def test_oficializar_exige_aprovado(self):
        novo_id = f.salvar(self.target, "rg_atualizacao", self._payload(), self.agente)
        with self.assertRaises(ValueError):
            rg_formulario.oficializar(self.target, novo_id, self.admin)


if __name__ == "__main__":
    unittest.main()
