import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core


class PontosEstrategicosAliasesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = db_core.DatabaseTarget("sqlite", str(Path(self.tmp.name) / "pe.db"))
        conn = db_core.connect(self.target)
        conn.execute(
            "CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT, cod_localidade TEXT)"
        )
        pe_core.ensure_schema(conn)
        conn.commit()
        conn.close()

    def _criar_pe(self, codigo, nome, logradouro=None, localidade=None, numero=None):
        pe_core.salvar(self.target, {
            "codigo_pe": codigo,
            "nome": nome,
            "logradouro": logradouro,
            "localidade": localidade,
            "numero": numero,
        })

    def _id_pe(self, codigo):
        conn = db_core.connect(self.target)
        try:
            return conn.execute(
                "SELECT id_pe FROM pontos_estrategicos WHERE codigo_pe=?", (codigo,)
            ).fetchone()[0]
        finally:
            conn.close()

    def test_listar_aliases_traz_seed_e_automatico(self):
        self._criar_pe("PE-0001", "Borracharia do Nei", "Rodovia dos Minerios", "Tranqueira", "14365")
        aliases = pe_core.listar_aliases(self.target, "PE-0001")
        observacoes = {a["observacoes"] for a in aliases}
        self.assertIn(pe_core.OBS_ALIAS_INICIAL, observacoes)
        self.assertIn(pe_core.OBS_ALIAS_AUTOMATICO, observacoes)
        self.assertTrue(all(a["codigo_pe"] == "PE-0001" for a in aliases))

    def test_salvar_alias_manual_e_resolucao(self):
        self._criar_pe("PE-0046", "Auto Peças João 3:16", "Rua Domingos Scucato", "Sede")
        pe_core.salvar_alias_manual(
            self.target, "PE-0046", "RUA DOMINGOS SCUCATO - AUTO PEÇAS JOÃO 3:16", None
        )
        aliases = pe_core.listar_aliases(self.target, "PE-0046")
        manual = next(a for a in aliases if a["observacoes"] == pe_core.OBS_ALIAS_MANUAL)
        self.assertEqual(manual["alias_normalizado"], "rua domingos scucato - auto pecas joao 3:16")
        conn = db_core.connect(self.target)
        try:
            vinculo = pe_core.resolver_alias_visita(
                conn, "RUA DOMINGOS SCUCATO - AUTO PEÇAS JOÃO 3:16", "Sede"
            )
        finally:
            conn.close()
        self.assertEqual(vinculo["codigo_pe"], "PE-0046")

    def test_salvar_alias_manual_rejeita_conflito_entre_pes(self):
        self._criar_pe("PE-0001", "Borracharia do Nei", "Rodovia dos Minerios", "Tranqueira", "14365")
        self._criar_pe("PE-0046", "Auto Peças João 3:16", "Rua Domingos Scucato", "Sede")
        pe_core.salvar_alias_manual(self.target, "PE-0046", "ALIAS UNICO", None)
        with self.assertRaises(ValueError):
            pe_core.salvar_alias_manual(self.target, "PE-0001", "ALIAS UNICO", None)

    def test_regeneracao_preserva_alias_manual(self):
        self._criar_pe("PE-0046", "Auto Peças João 3:16", "Rua Domingos Scucato", "Sede")
        pe_core.salvar_alias_manual(self.target, "PE-0046", "ALIAS MANUAL CUSTOM", None)
        conn = db_core.connect(self.target)
        try:
            pe_core._seed_aliases(conn)
            conn.commit()
            row = conn.execute(
                "SELECT observacoes, ativo FROM pontos_estrategicos_alias WHERE alias_normalizado=?",
                ("alias manual custom",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["observacoes"], pe_core.OBS_ALIAS_MANUAL)
        self.assertEqual(row["ativo"], 1)

    def test_edit_alternar_excluir_restritos_a_manual(self):
        self._criar_pe("PE-0001", "Borracharia do Nei", "Rodovia dos Minerios", "Tranqueira", "14365")
        seed = next(
            a for a in pe_core.listar_aliases(self.target, "PE-0001")
            if a["observacoes"] == pe_core.OBS_ALIAS_INICIAL
        )
        with self.assertRaises(ValueError):
            pe_core.excluir_alias_manual(self.target, seed["id_alias"])
        with self.assertRaises(ValueError):
            pe_core.alternar_alias_manual(self.target, seed["id_alias"], 0)
        with self.assertRaises(ValueError):
            pe_core.salvar_alias_manual(self.target, "PE-0001", "X", id_alias=seed["id_alias"])

    def test_alternar_e_excluir_alias_manual(self):
        self._criar_pe("PE-0046", "Auto Peças João 3:16", "Rua Domingos Scucato", "Sede")
        pe_core.salvar_alias_manual(self.target, "PE-0046", "ALIAS MANUAL", None)
        manual = next(
            a for a in pe_core.listar_aliases(self.target, "PE-0046")
            if a["observacoes"] == pe_core.OBS_ALIAS_MANUAL
        )
        pe_core.alternar_alias_manual(self.target, manual["id_alias"], 0)
        desativado = next(a for a in pe_core.listar_aliases(self.target, "PE-0046") if a["id_alias"] == manual["id_alias"])
        self.assertEqual(desativado["ativo"], 0)
        pe_core.excluir_alias_manual(self.target, manual["id_alias"])
        self.assertFalse(any(a["id_alias"] == manual["id_alias"] for a in pe_core.listar_aliases(self.target, "PE-0046")))


if __name__ == "__main__":
    unittest.main()
