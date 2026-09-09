import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app_core import db as db_core
from app_core import enderecos
from app_core import logradouros


class LogradourosTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _csv(rows):
        return ("nome,localidade,id_logr\n" + "\n".join(rows) + "\n").encode("utf-8")

    def test_importa_trechos_repetidos_e_atualiza_por_id_estavel(self):
        first = self._csv((
            "Rua Sao Joao,Sede,uuid-a",
            "Rua Sao Joao,Roma,uuid-b",
            "Avenida Central,Sede,uuid-c",
        ))
        result = logradouros.importar_csv(self.path, first)
        self.assertEqual((3, 0, 0), (result["inseridos"], result["atualizados"], result["sem_alteracao"]))
        summary = logradouros.resumo(self.path)
        self.assertEqual(3, summary["trechos"])
        self.assertEqual(2, summary["nomes_normalizados"])

        second = self._csv((
            "Rua São João,Sede,uuid-a",
            "Rua Sao Joao,Roma,uuid-b",
            "Avenida Central,Sede,uuid-c",
        ))
        result = logradouros.importar_csv(self.path, second)
        self.assertEqual((0, 1, 2), (result["inseridos"], result["atualizados"], result["sem_alteracao"]))
        rows = logradouros.listar(self.path, "São João")["registros"]
        self.assertEqual(2, len(rows))
        self.assertEqual({"uuid-a", "uuid-b"}, {row["id_logradouro"] for row in rows})

    def test_recusa_coluna_ou_id_repetido(self):
        with self.assertRaisesRegex(ValueError, "obrigatória"):
            logradouros.importar_csv(self.path, b"nome,id_logr\nRua A,1\n")
        with self.assertRaisesRegex(ValueError, "repetido"):
            logradouros.importar_csv(
                self.path,
                self._csv(("Rua A,Sede,1", "Rua B,Sede,1")),
            )

    def test_importacao_nao_remove_trecho_ausente(self):
        logradouros.importar_csv(self.path, self._csv(("Rua A,Sede,1", "Rua B,Sede,2")))
        logradouros.importar_csv(self.path, self._csv(("Rua A,Sede,1",)))
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM logradouros_oficiais").fetchone()[0])
        finally:
            conn.close()

    def test_ativo_e_compativel_com_postgresql(self):
        class PostgresConnection:
            backend = "postgresql"

        class SQLiteConnection:
            backend = "sqlite"

        self.assertEqual("ativo=TRUE", logradouros._ativo_verdadeiro_sql(PostgresConnection()))
        self.assertTrue(logradouros._ativo_verdadeiro_valor(PostgresConnection()))
        self.assertEqual("ativo=1", logradouros._ativo_verdadeiro_sql(SQLiteConnection()))
        self.assertEqual(1, logradouros._ativo_verdadeiro_valor(SQLiteConnection()))

    def test_previa_confirma_positivos_sem_alterar_visita_bruta(self):
        logradouros.importar_csv(
            self.path, self._csv(("Rua São João,Sede,uuid-a",))
        )
        conn = db_core.connect(self.path)
        try:
            conn.executescript(
                """
                CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
                CREATE TABLE visitas (
                    id_visita TEXT PRIMARY KEY, logradouro TEXT, numero TEXT, data TEXT,
                    tipo TEXT, localidade TEXT, id_localidade INTEGER, quarteirao INTEGER
                );
                CREATE TABLE coletas (id_coleta TEXT PRIMARY KEY, id_visita TEXT);
                CREATE TABLE resultados_laboratorio (
                    id_coleta TEXT, aegypt_larvas INTEGER, aegypt_pupas INTEGER,
                    aegypt_exuvias INTEGER, aegypt_adulto INTEGER
                );
                """
            )
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?)",
                ("v-1", "R. SAO Joao", "20", "2026-09-01", "TB", "Sede", None, 10),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-1", "v-1"))
            conn.execute("INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)", ("c-1", 1, 0, 0, 0))
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?)",
                ("v-pe", "Rua São João", "20", "2026-09-01", "PE", "Sede", None, 10),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-pe", "v-pe"))
            conn.execute("INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)", ("c-pe", 1, 0, 0, 0))
            conn.commit()
        finally:
            conn.close()

        previa = logradouros.previa_visitas_positivas(self.path)
        self.assertEqual(1, previa["total_grupos"])
        self.assertEqual(1, previa["total_visitas"])
        grupo = previa["grupos"][0]
        self.assertEqual("pronto_para_revisar", grupo["situacao"])
        self.assertEqual("Rua São João", grupo["nome_oficial"])
        result = logradouros.confirmar_grupo_visitas_positivas(
            self.path, grupo["chave"], grupo["nome_oficial"], "João"
        )
        self.assertEqual(1, result["visitas_vinculadas"])
        summary = logradouros.resumo(self.path)
        self.assertEqual(1, summary["enderecos_confirmados"])
        self.assertEqual(1, summary["visitas_vinculadas"])
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(
                "R. SAO Joao",
                conn.execute("SELECT logradouro FROM visitas WHERE id_visita='v-1'").fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute("SELECT COUNT(*) FROM visitas_enderecos_normalizados").fetchone()[0],
            )
        finally:
            conn.close()

    def test_sugere_plural_e_artigo_como_correspondencia_aproximada(self):
        self.assertEqual(
            (96, "variação de artigo ou singular/plural"),
            enderecos.similaridade_logradouro("Rua Salgueiro", "Rua dos Salgueiros"),
        )
        logradouros.importar_csv(
            self.path, self._csv(("Rua dos Salgueiros,Sede,uuid-salgueiros",))
        )
        conn = db_core.connect(self.path)
        try:
            conn.executescript(
                """
                CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
                CREATE TABLE visitas (
                    id_visita TEXT PRIMARY KEY, logradouro TEXT, numero TEXT, data TEXT,
                    tipo TEXT, localidade TEXT, id_localidade INTEGER, quarteirao INTEGER
                );
                CREATE TABLE coletas (id_coleta TEXT PRIMARY KEY, id_visita TEXT);
                CREATE TABLE resultados_laboratorio (
                    id_coleta TEXT, aegypt_larvas INTEGER, aegypt_pupas INTEGER,
                    aegypt_exuvias INTEGER, aegypt_adulto INTEGER
                );
                """
            )
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?)",
                ("v-salgueiro", "Rua Salgueiro", "51", "2026-09-01", "TBO", "Sede", None, 10),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-salgueiro", "v-salgueiro"))
            conn.execute(
                "INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)",
                ("c-salgueiro", 1, 0, 0, 0),
            )
            conn.commit()
        finally:
            conn.close()

        grupo = logradouros.previa_visitas_positivas(self.path)["grupos"][0]
        self.assertEqual("sugestao_aproximada", grupo["situacao"])
        self.assertEqual("Rua dos Salgueiros", grupo["candidatos"][0]["nome"])
        self.assertEqual(96, grupo["candidatos"][0]["score"])
        result = logradouros.confirmar_grupo_visitas_positivas(
            self.path, grupo["chave"], "Rua dos Salgueiros", "João"
        )
        self.assertEqual(1, result["visitas_vinculadas"])
        conn = db_core.connect(self.path)
        try:
            endereco = conn.execute("SELECT * FROM enderecos_normalizados").fetchone()
            self.assertEqual("rua dos salgueiros", endereco["logradouro_normalizado"])
            self.assertEqual("Rua dos Salgueiros", endereco["logradouro_oficial"])
            self.assertEqual(
                "Rua Salgueiro",
                conn.execute("SELECT logradouro FROM visitas WHERE id_visita='v-salgueiro'").fetchone()[0],
            )
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?)",
                ("v-oficial", "Rua dos Salgueiros", "51", "2026-09-02", "TBO", "Sede", None, 10),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-oficial", "v-oficial"))
            conn.execute(
                "INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)",
                ("c-oficial", 1, 0, 0, 0),
            )
            conn.commit()
        finally:
            conn.close()

        grupo_oficial = logradouros.previa_visitas_positivas(self.path)["grupos"][0]
        logradouros.confirmar_grupo_visitas_positivas(
            self.path, grupo_oficial["chave"], "Rua dos Salgueiros", "João"
        )
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM enderecos_normalizados").fetchone()[0])
            self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM visitas_enderecos_normalizados").fetchone()[0])
        finally:
            conn.close()

    def test_migracao_postgresql_cria_entidades_do_piloto(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "migrations/postgresql/0007_enderecos_normalizados_visitas.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE enderecos_normalizados", sql)
        self.assertIn("CREATE TABLE visitas_enderecos_normalizados", sql)
        self.assertIn("REFERENCES visitas(id_visita)", sql)


if __name__ == "__main__":
    unittest.main()
