import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import focos_positivos
import etl


class FocosPositivosTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "focos.db")
        self.conn = db_core.connect(self.db_path)
        self.conn.executescript(
            """
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY, tipo TEXT NOT NULL, data TEXT,
                id_localidade INTEGER, localidade TEXT, quarteirao INTEGER,
                logradouro TEXT, numero TEXT, morador TEXT, tipo_imovel TEXT,
                observacoes TEXT
            );
            CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT);
            CREATE TABLE visita_agentes (id_visita TEXT, id_agente INTEGER);
            CREATE TABLE coletas (
                id_coleta TEXT PRIMARY KEY, id_visita TEXT, num_tubo TEXT,
                tipo_deposito TEXT
            );
            CREATE TABLE resultados_laboratorio (
                id_resultado INTEGER PRIMARY KEY, id_coleta TEXT,
                aegypt_larvas INTEGER DEFAULT 0, aegypt_pupas INTEGER DEFAULT 0,
                aegypt_exuvias INTEGER DEFAULT 0, aegypt_adulto INTEGER DEFAULT 0
            );
            CREATE TABLE focos_positivos (
                id_foco TEXT PRIMARY KEY, id_visita TEXT, id_coleta TEXT,
                id_resultado INTEGER, num_tubo TEXT, codigo TEXT, origem TEXT,
                tipo_trabalho TEXT, data TEXT, id_localidade INTEGER,
                localidade TEXT, quarteirao INTEGER, logradouro TEXT,
                numero TEXT, complemento TEXT, nome_morador TEXT,
                tipo_imovel TEXT, depositos TEXT, agentes TEXT,
                observacoes TEXT, gera_notificacao INTEGER,
                status_notificacao TEXT DEFAULT 'pendente', processado_em TEXT
            );
            """
        )
        self.conn.execute("INSERT INTO agentes VALUES (1, 'Agente A')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _visita_positiva(self, id_visita, tipo, tipo_imovel, tubo="1"):
        self.conn.execute(
            """INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (id_visita, tipo, "2026-08-25", 1, "Sede", 2, "Rua A", "10",
             "Morador", tipo_imovel, "Obs."),
        )
        self.conn.execute(
            "INSERT INTO visita_agentes VALUES (?,1)", (id_visita,)
        )
        coleta = f"coleta-{id_visita}"
        self.conn.execute(
            "INSERT INTO coletas VALUES (?,?,?,?)", (coleta, id_visita, tubo, "A1")
        )
        self.conn.execute(
            "INSERT INTO resultados_laboratorio VALUES (?,?,2,0,0,0)",
            (len(id_visita) * 10 + int(tubo), coleta),
        )
        self.conn.commit()

    def test_regras_de_notificacao(self):
        self.assertTrue(focos_positivos.deve_gerar_notificacao("TB", "Residência"))
        self.assertTrue(focos_positivos.deve_gerar_notificacao("TBO", "Comércio"))
        self.assertTrue(focos_positivos.deve_gerar_notificacao("PVE", "Residência"))
        self.assertFalse(focos_positivos.deve_gerar_notificacao("PE", "Residência"))
        self.assertFalse(focos_positivos.deve_gerar_notificacao("TB", "TB"))
        self.assertFalse(
            focos_positivos.deve_gerar_notificacao("TBO", "Terreno Baldio")
        )

    def test_foco_agrupa_tubos_e_preserva_status_manual(self):
        self._visita_positiva("visita-principal", "PVE", "Residência", "1")
        foco = focos_positivos.sincronizar_foco_visita(
            self.conn, "visita-principal", "2026-08-25T10:00:00",
        )
        self.assertTrue(foco["gera_notificacao"])
        self.conn.execute(
            "UPDATE focos_positivos SET status_notificacao='entregue' WHERE id_foco=?",
            (foco["id_foco"],),
        )
        self.conn.execute(
            "INSERT INTO coletas VALUES ('coleta-extra','visita-principal','2','B')"
        )
        self.conn.execute(
            "INSERT INTO resultados_laboratorio VALUES (999,'coleta-extra',0,1,0,0)"
        )
        focos_positivos.sincronizar_foco_visita(
            self.conn, "visita-principal", "2026-08-25T11:00:00",
        )
        row = self.conn.execute(
            "SELECT num_tubo, status_notificacao, gera_notificacao FROM focos_positivos"
        ).fetchone()
        self.assertEqual(("1, 2", "entregue", 1), tuple(row))

        self.conn.execute(
            "UPDATE resultados_laboratorio SET aegypt_larvas=0, aegypt_pupas=0"
        )
        focos_positivos.sincronizar_foco_visita(
            self.conn, "visita-principal", "2026-08-25T12:00:00",
        )
        row = self.conn.execute(
            "SELECT status_notificacao, gera_notificacao FROM focos_positivos"
        ).fetchone()
        self.assertEqual(("entregue", 0), tuple(row))

    def test_pe_e_terreno_baldio_ficam_fora_da_fila(self):
        casos = (
            ("visita-pe", "PE", "Residência", False),
            ("visita-tb", "TB", "TB", False),
            ("visita-tbo", "TBO", "Terreno Baldio", False),
            ("visita-pve", "PVE", "Residência", True),
        )
        for indice, (id_visita, tipo, tipo_imovel, esperado) in enumerate(casos, 1):
            with self.subTest(id_visita=id_visita):
                self._visita_positiva(id_visita, tipo, tipo_imovel, str(indice + 10))
                foco = focos_positivos.sincronizar_foco_visita(
                    self.conn, id_visita, "2026-08-25T10:00:00",
                )
                self.assertEqual(esperado, foco["gera_notificacao"])

    def test_previa_lista_positivo_sem_foco(self):
        self._visita_positiva("visita-sem-foco", "TBO", "Residência", "30")
        previa = focos_positivos.listar_divergencias(self.conn)
        self.assertEqual(1, len(previa))
        self.assertEqual("positivo_sem_foco", previa[0]["motivo"])

    def test_reutiliza_foco_legado_da_mesma_visita(self):
        self._visita_positiva("visita-legado", "TBO", "Residência", "31")
        self.conn.execute(
            """INSERT INTO focos_positivos
                   (id_foco, id_visita, gera_notificacao, status_notificacao,
                    processado_em)
               VALUES ('foco-legado', 'visita-legado', 0, 'entregue',
                       '2026-01-01T00:00:00')"""
        )
        foco = focos_positivos.sincronizar_foco_visita(
            self.conn, "visita-legado", "2026-08-25T10:00:00",
        )
        self.assertEqual("foco-legado", foco["id_foco"])
        rows = self.conn.execute(
            """SELECT id_foco, gera_notificacao, status_notificacao
                 FROM focos_positivos WHERE id_visita='visita-legado'"""
        ).fetchall()
        self.assertEqual([("foco-legado", 1, "entregue")], [tuple(row) for row in rows])
        self.assertEqual([], focos_positivos.listar_divergencias(self.conn))

    def test_etl_usa_a_mesma_regra_para_terreno_baldio(self):
        self._visita_positiva("visita-etl", "TBO", "TB", "40")
        etl.inserir_foco_visita(
            self.conn.cursor(), "visita-etl", [], {}, "TBO", {},
            "2026-08-25T10:00:00",
        )
        foco = self.conn.execute(
            "SELECT gera_notificacao FROM focos_positivos WHERE id_visita='visita-etl'"
        ).fetchone()
        self.assertEqual(0, foco[0])


if __name__ == "__main__":
    unittest.main()
