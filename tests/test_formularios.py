import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import formularios as f


class FormulariosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = db_core.DatabaseTarget("sqlite", str(Path(self.tmp.name) / "formularios.db"))
        conn = db_core.connect(self.target)
        f.ensure_schema(conn)
        conn.commit()
        conn.close()
        self.agente = {"id_usuario": 10, "nome": "Agente Teste", "nivel": "usuario"}
        self.admin = {"id_usuario": 1, "nome": "Admin", "nivel": "admin"}

    def test_registro_contem_rg(self):
        self.assertIsNotNone(f.formulario_por_tipo("rg_atualizacao"))

    def test_salvar_e_obter(self):
        novo_id = f.salvar(
            self.target, "rg_atualizacao",
            {"localidade": "Sede", "quarteirao": "0408", "linhas": []},
            self.agente,
        )
        item = f.obter(self.target, novo_id)
        self.assertEqual(item["tipo_formulario"], "rg_atualizacao")
        self.assertEqual(item["status"], f.STATUS_ENVIADO)
        self.assertEqual(item["agente_nome"], "Agente Teste")
        self.assertEqual(item["payload"]["localidade"], "Sede")

    def test_salvar_rejeita_tipo_desconhecido(self):
        with self.assertRaises(ValueError):
            f.salvar(self.target, "inexistente", {}, self.agente)

    def test_salvar_rejeita_status_invalido(self):
        with self.assertRaises(ValueError):
            f.salvar(self.target, "rg_atualizacao", {}, self.agente, status="sei_la")

    def test_idempotencia_por_uuid_cliente(self):
        id1 = f.salvar(self.target, "rg_atualizacao", {"x": 1}, self.agente, uuid_cliente="abc-123")
        id2 = f.salvar(self.target, "rg_atualizacao", {"x": 2}, self.agente, uuid_cliente="abc-123")
        self.assertEqual(id1, id2)
        self.assertEqual(f.obter(self.target, id1)["payload"]["x"], 2)

    def test_listar_filtra_por_usuario_nao_admin(self):
        f.salvar(self.target, "rg_atualizacao", {"q": "a"}, self.agente)
        f.salvar(self.target, "rg_atualizacao", {"q": "b"}, {"id_usuario": 20, "nome": "Outro", "nivel": "usuario"})
        self.assertEqual(len(f.listar(self.target, usuario=self.agente)), 1)
        self.assertEqual(len(f.listar(self.target, usuario=self.admin)), 2)

    def test_revisar_aprova_e_devolve(self):
        novo_id = f.salvar(self.target, "rg_atualizacao", {"linhas": []}, self.agente)
        f.revisar(self.target, novo_id, {"linhas": [{"logradouro": "Rua X"}]}, f.STATUS_APROVADO, self.admin)
        item = f.obter(self.target, novo_id)
        self.assertEqual(item["status"], f.STATUS_APROVADO)
        self.assertEqual(item["payload"]["linhas"][0]["logradouro"], "Rua X")
        self.assertEqual(item["revisado_por_nome"], "Admin")

        f.revisar(self.target, novo_id, {"linhas": []}, f.STATUS_DEVOLVIDO, self.admin, motivo="conferir lado")
        self.assertEqual(f.obter(self.target, novo_id)["status"], f.STATUS_DEVOLVIDO)
        self.assertEqual(f.obter(self.target, novo_id)["motivo_devolucao"], "conferir lado")

    def test_nao_revisa_formulario_oficializado(self):
        novo_id = f.salvar(self.target, "rg_atualizacao", {}, self.agente)
        f.marcar_oficializado(self.target, novo_id, self.admin)
        with self.assertRaises(ValueError):
            f.revisar(self.target, novo_id, {}, f.STATUS_APROVADO, self.admin)


if __name__ == "__main__":
    unittest.main()
