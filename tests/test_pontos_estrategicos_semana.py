import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core
from app_core import sispncd
from blueprints import pontos_estrategicos as pe_blueprint


class PontosEstrategicosSemanaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "pe.db"
        self.conn = db_core.connect(self.db_path)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS localidades (
                id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cod_localidade TEXT
            );
            CREATE TABLE IF NOT EXISTS visitas (
                id_visita TEXT PRIMARY KEY,
                tipo TEXT NOT NULL,
                data DATE NOT NULL,
                id_localidade INTEGER,
                quarteirao INTEGER,
                id_pe INTEGER,
                codigo_pe TEXT
            );
            CREATE TABLE IF NOT EXISTS focos_positivos (
                id_foco INTEGER PRIMARY KEY AUTOINCREMENT,
                gera_notificacao INTEGER,
                id_localidade INTEGER,
                quarteirao INTEGER
            );
            """
        )
        pe_core.ensure_schema(self.conn)
        agora = "2026-08-01T10:00:00"
        self.id_visitado = self._inserir_pe(
            codigo_pe="PE-0001", nome="Feito na semana", quarteirao=1, agora=agora
        )
        self.id_pendente = self._inserir_pe(
            codigo_pe="PE-0002", nome="Pendente na semana", quarteirao=2, agora=agora
        )
        self.id_fora_periodo = self._inserir_pe(
            codigo_pe="PE-0003", nome="Visitado fora da semana", quarteirao=3, agora=agora
        )
        # Semana epidemiologica de referencia para os testes.
        self.ano, self.semana = sispncd.epidemiological_week_for_date("2026-08-03")
        self.d_ini, self.d_fim = sispncd.epidemiological_week_range(self.ano, self.semana)
        self.conn.execute(
            "INSERT INTO visitas (id_visita, tipo, data, id_pe) VALUES (?,?,?,?)",
            ("v1", "PE", self.d_ini, self.id_visitado),
        )
        self.conn.execute(
            "INSERT INTO visitas (id_visita, tipo, data, id_pe) VALUES (?,?,?,?)",
            ("v2", "PE", self.d_fim, self.id_visitado),
        )
        # Visita fora da janela da semana selecionada (nao deve contar como feito).
        anterior_ano, anterior_semana = sispncd.epidemiological_week_for_date(self.d_ini)
        anterior_inicio, _ = sispncd.epidemiological_week_range(
            anterior_ano if anterior_semana > 1 else anterior_ano - 1,
            anterior_semana - 1 if anterior_semana > 1 else 53,
        )
        self.conn.execute(
            "INSERT INTO visitas (id_visita, tipo, data, id_pe) VALUES (?,?,?,?)",
            ("v3", "PE", anterior_inicio, self.id_fora_periodo),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _inserir_pe(self, *, codigo_pe, nome, quarteirao, agora):
        cur = self.conn.execute(
            """INSERT INTO pontos_estrategicos (
                   codigo_pe, nome, quarteirao, situacao, criado_em, atualizado_em
               ) VALUES (?,?,?,1,?,?)""",
            (codigo_pe, nome, quarteirao, agora, agora),
        )
        self.conn.commit()
        return cur.lastrowid

    def test_sem_filtro_de_periodo_nao_marca_feito_nem_pendente(self):
        resultado = pe_core.listar(self.conn, {})
        por_id = {r["id_pe"]: r for r in resultado["registros"]}
        self.assertIsNone(por_id[self.id_visitado]["visitado_periodo_selecionado"])
        self.assertNotIn("feitos_periodo", resultado["totais"])
        self.assertNotIn("pendentes_periodo", resultado["totais"])

    def test_com_periodo_marca_feito_e_pendente_corretamente(self):
        filtros = {"periodo_inicio": self.d_ini, "periodo_fim": self.d_fim}
        resultado = pe_core.listar(self.conn, filtros)
        por_id = {r["id_pe"]: r for r in resultado["registros"]}
        self.assertTrue(por_id[self.id_visitado]["visitado_periodo_selecionado"])
        self.assertFalse(por_id[self.id_pendente]["visitado_periodo_selecionado"])
        self.assertFalse(por_id[self.id_fora_periodo]["visitado_periodo_selecionado"])
        self.assertEqual(resultado["totais"]["feitos_periodo"], 1)
        self.assertEqual(resultado["totais"]["pendentes_periodo"], 2)

    def test_filtro_pendentes_periodo_remove_feitos(self):
        filtros = {
            "periodo_inicio": self.d_ini,
            "periodo_fim": self.d_fim,
            "pendentes_periodo": "1",
        }
        resultado = pe_core.listar(self.conn, filtros)
        ids = {r["id_pe"] for r in resultado["registros"]}
        self.assertNotIn(self.id_visitado, ids)
        self.assertIn(self.id_pendente, ids)
        self.assertIn(self.id_fora_periodo, ids)

    def test_visita_sem_id_pe_conta_pelo_fallback_localidade_quarteirao(self):
        agora = "2026-08-01T10:00:00"
        id_localidade = self.conn.execute(
            "INSERT INTO localidades (nome) VALUES ('Sede')"
        ).lastrowid
        id_pe_fallback = self._inserir_pe(
            codigo_pe="PE-0004", nome="Fallback", quarteirao=9, agora=agora
        )
        self.conn.execute(
            "UPDATE pontos_estrategicos SET id_localidade=? WHERE id_pe=?",
            (id_localidade, id_pe_fallback),
        )
        self.conn.execute(
            "INSERT INTO visitas (id_visita, tipo, data, id_localidade, quarteirao) "
            "VALUES (?,?,?,?,?)",
            ("v4", "PE", self.d_ini, id_localidade, 9),
        )
        self.conn.commit()
        filtros = {"periodo_inicio": self.d_ini, "periodo_fim": self.d_fim}
        resultado = pe_core.listar(self.conn, filtros)
        por_id = {r["id_pe"]: r for r in resultado["registros"]}
        self.assertTrue(por_id[id_pe_fallback]["visitado_periodo_selecionado"])


class PontosEstrategicosFiltrosBlueprintTests(unittest.TestCase):
    def test_filtros_ano_semana_calcula_periodo(self):
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context("/api/pontos-estrategicos?ano=2026&semana=31"):
            filtros = pe_blueprint._filtros()
        self.assertEqual(filtros["ano"], 2026)
        self.assertEqual(filtros["semana"], 31)
        inicio, fim = sispncd.epidemiological_week_range(2026, 31)
        self.assertEqual(filtros["periodo_inicio"], inicio)
        self.assertEqual(filtros["periodo_fim"], fim)

    def test_filtros_sem_semana_nao_inclui_periodo(self):
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context("/api/pontos-estrategicos"):
            filtros = pe_blueprint._filtros()
        self.assertNotIn("periodo_inicio", filtros)
        self.assertNotIn("periodo_fim", filtros)

    def test_filtros_semana_invalida_levanta_validation_error(self):
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context("/api/pontos-estrategicos?ano=2026&semana=99"):
            with self.assertRaises(sispncd.ValidationError):
                pe_blueprint._filtros()


if __name__ == "__main__":
    unittest.main()
