"""A situação atual segue a data do acompanhamento, com desempate pelo ID."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import db
from app_core import esporotricose_humanos as humanos


class EsporotricoseHumanosCronologiaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "humanos-ficticio.db")
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE localidades(id_localidade INTEGER PRIMARY KEY,nome TEXT UNIQUE,cod_localidade INTEGER)")
            conn.execute("CREATE TABLE agentes(id_agente INTEGER PRIMARY KEY,nome TEXT UNIQUE)")
            humanos.ensure_schema(conn)
        finally:
            conn.close()
        self.pid = humanos.salvar_paciente(self.path, {"nome": "Pessoa Fictícia", "status": "Em tratamento"}, "Responsável Fictício")

    def salvar(self, data, status, **extra):
        return humanos.salvar_acompanhamento(self.path, self.pid, {"data": data, "status": status, **extra}, "Responsável Fictício")

    def paciente(self):
        return humanos.obter_paciente(self.path, self.pid)

    def test_retroativo_nao_reabre_caso_nem_altera_autoria_da_situacao(self):
        recente = self.salvar("2026-06-10", "Acabou tratamento")
        before = self.paciente()
        retroativo = humanos.salvar_acompanhamento(self.path, self.pid, {"data": "2026-06-01", "status": "Em tratamento"}, "Autor Retroativo Fictício")
        after = self.paciente()
        self.assertEqual(after["status"], "Acabou tratamento")
        self.assertEqual(after["atualizado_por"], before["atualizado_por"])
        self.assertEqual(after["atualizado_em"], before["atualizado_em"])
        self.assertEqual([item["id_acompanhamento"] for item in after["acompanhamentos"]], [recente, retroativo])

    def test_retroativo_nao_encerra_caso_em_tratamento(self):
        self.salvar("2026-06-10", "Em tratamento")
        self.salvar("2026-06-01", "Acabou tratamento")
        self.assertEqual(self.paciente()["status"], "Em tratamento")

    def test_data_mais_recente_atualiza_situacao_e_status_outro(self):
        self.salvar("2026-06-01", "Outros", status_outro="Em investigação fictícia")
        self.assertEqual(self.paciente()["status_outro"], "Em investigação fictícia")
        self.salvar("2026-06-02", "Acabou tratamento", status_outro="Texto descartado")
        self.assertEqual(self.paciente()["status"], "Acabou tratamento")
        self.assertIsNone(self.paciente()["status_outro"])

    def test_empate_de_data_usa_ultimo_id_como_historico(self):
        primeiro = self.salvar("2026-06-10", "Acabou tratamento")
        segundo = self.salvar("2026-06-10", "Outros", status_outro="Nova avaliação fictícia")
        paciente = self.paciente()
        self.assertGreater(segundo, primeiro)
        self.assertEqual(paciente["acompanhamentos"][0]["id_acompanhamento"], segundo)
        self.assertEqual(paciente["status"], "Outros")
        self.assertEqual(paciente["status_outro"], "Nova avaliação fictícia")

    def test_editar_cadastro_preserva_situacao_do_ultimo_acompanhamento(self):
        self.salvar("2026-06-10", "Acabou tratamento")
        humanos.salvar_paciente(self.path, {"id_paciente": self.pid, "nome": "Nome Fictício Corrigido", "status": "Em tratamento", "observacoes": "Correção cadastral fictícia"}, "Outro Responsável Fictício")
        paciente = self.paciente()
        self.assertEqual(paciente["nome"], "Nome Fictício Corrigido")
        self.assertEqual(paciente["status"], "Acabou tratamento")
        self.assertEqual(len(paciente["acompanhamentos"]), 1)

    def test_cadastro_sem_acompanhamento_ainda_aceita_situacao_inicial(self):
        humanos.salvar_paciente(self.path, {"id_paciente": self.pid, "nome": "Pessoa Fictícia", "status": "Outros", "status_outro": "Investigação fictícia"}, "Responsável Fictício")
        self.assertEqual(self.paciente()["status"], "Outros")
        self.assertEqual(self.paciente()["status_outro"], "Investigação fictícia")

    def test_validacao_nao_grava_historico_ou_muda_situacao(self):
        self.salvar("2026-06-10", "Acabou tratamento")
        for payload in (
            {"data": "2026-02-30", "status": "Em tratamento"},
            {"data": "2099-01-01", "status": "Em tratamento"},
            {"data": "", "status": "Em tratamento"},
            {"data": "2026-06-01", "status": "Inválido"},
            {"data": "2026-06-01", "status": "Outros"},
        ):
            with self.subTest(payload=payload), self.assertRaises(humanos.ValidationError):
                humanos.salvar_acompanhamento(self.path, self.pid, payload, "Responsável Fictício")
        self.assertEqual(self.paciente()["status"], "Acabou tratamento")
        self.assertEqual(len(self.paciente()["acompanhamentos"]), 1)

    def test_somente_paciente_gravado_e_afetado(self):
        outro = humanos.salvar_paciente(self.path, {"nome": "Outra Pessoa Fictícia", "status": "Em tratamento"}, "Responsável Fictício")
        before = db.query_one(self.path, "SELECT * FROM esporotricose_pacientes_humanos WHERE id_paciente=?", (outro,))
        self.salvar("2026-06-10", "Acabou tratamento")
        self.assertEqual(db.query_one(self.path, "SELECT * FROM esporotricose_pacientes_humanos WHERE id_paciente=?", (outro,)), before)

    def test_bloqueio_postgresql_serializa_gravacoes_do_mesmo_paciente(self):
        conn = mock.Mock(backend="postgresql")
        humanos._bloquear_paciente(conn, 17)
        statement, params = conn.execute.call_args.args
        self.assertIn("FOR UPDATE", statement)
        self.assertEqual(params, (17,))
