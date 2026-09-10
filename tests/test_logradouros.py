import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from flask import Flask

from app_core import db as db_core
from app_core import enderecos
from app_core import geocodificacao
from app_core import logradouros
from blueprints import logradouros as logradouros_bp


class LogradourosTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    def _criar_endereco(self, logradouro="Rua São João", numero="20"):
        logradouros.ensure_schema(self.path)
        conn = db_core.connect(self.path)
        try:
            cursor = conn.execute(
                """INSERT INTO enderecos_normalizados
                   (chave_endereco, logradouro_normalizado, logradouro_oficial,
                    numero_normalizado, criado_em, atualizado_em, confirmado_por)
                   VALUES (?,?,?,?,?,?,?)""",
                (f"{logradouro}|{numero}", logradouros.normalizar_logradouro(logradouro),
                 logradouro, numero, "2026-09-10", "2026-09-10", "João"),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

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

    def test_api_informa_sucesso_quando_apenas_a_auditoria_falha(self):
        app = Flask(__name__)
        resultado = {
            "grupos_confirmados": 2,
            "enderecos_afetados": 2,
            "visitas_vinculadas": 3,
            "confirmacoes": [],
        }
        view = logradouros_bp.api_confirmar_visitas_positivas
        while hasattr(view, "__wrapped__"):
            view = view.__wrapped__

        with app.test_request_context(
            "/api/logradouros/visitas-positivas/confirmar",
            method="POST",
            json={"itens": [{"chave": "grupo-1"}]},
        ):
            with (
                mock.patch.object(logradouros_bp, "_usuario_atual", return_value={"nome": "João"}),
                mock.patch.object(logradouros_bp, "_target", return_value=self.path),
                mock.patch.object(
                    logradouros_bp.logradouros_core,
                    "confirmar_grupos_visitas_positivas",
                    return_value=resultado,
                ),
                mock.patch.object(
                    logradouros_bp.audit,
                    "registrar_evento",
                    side_effect=RuntimeError("auditoria indisponível"),
                ),
            ):
                response = view()

        dados = response.get_json()
        self.assertTrue(dados["ok"])
        self.assertEqual(3, dados["visitas_vinculadas"])
        self.assertIn("foram confirmados", dados["aviso"])

    def test_template_envia_a_mesma_variavel_de_itens_que_monta(self):
        template = (
            Path(__file__).resolve().parents[1] / "templates" / "logradouros.html"
        ).read_text(encoding="utf-8")
        self.assertIn("const itens = [...selectedGroups]", template)
        self.assertIn("body:JSON.stringify({itens})", template)
        self.assertNotIn("const items = [...selectedGroups]", template)

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
                    tipo TEXT, localidade TEXT, id_localidade INTEGER, quarteirao INTEGER,
                    morador TEXT, visita TEXT
                );
                CREATE TABLE coletas (id_coleta TEXT PRIMARY KEY, id_visita TEXT);
                CREATE TABLE resultados_laboratorio (
                    id_coleta TEXT, aegypt_larvas INTEGER, aegypt_pupas INTEGER,
                    aegypt_exuvias INTEGER, aegypt_adulto INTEGER
                );
                """
            )
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("v-1", "R. SAO Joao", "20", "2026-09-01", "TB", "Sede", None, 10, None, "Normal"),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-1", "v-1"))
            conn.execute("INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)", ("c-1", 1, 0, 0, 0))
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("v-pe", "Rua São João", "20", "2026-09-01", "PE", "Sede", None, 10, None, "Normal"),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-pe", "v-pe"))
            conn.execute("INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)", ("c-pe", 1, 0, 0, 0))
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("v-sem-endereco", "", "", "2026-09-01", "PVE", "Sede", None, 11, None, "Normal"),
            )
            conn.execute("INSERT INTO coletas VALUES (?,?)", ("c-sem-endereco", "v-sem-endereco"))
            conn.execute(
                "INSERT INTO resultados_laboratorio VALUES (?,?,?,?,?)",
                ("c-sem-endereco", 1, 0, 0, 0),
            )
            conn.commit()
        finally:
            conn.close()

        previa = logradouros.previa_visitas_positivas(self.path)
        self.assertEqual(2, previa["total_grupos"])
        self.assertEqual(2, previa["total_visitas"])
        self.assertEqual(2, previa["total_elegiveis"])
        self.assertEqual(0, previa["total_vinculadas"])
        self.assertEqual(1, previa["enderecos_incompletos"])
        grupo = next(item for item in previa["grupos"] if item["situacao"] == "pronto_para_revisar")
        grupo_incompleto = next(item for item in previa["grupos"] if item["situacao"] == "sem_logradouro")
        self.assertEqual("pronto_para_revisar", grupo["situacao"])
        self.assertEqual("Rua São João", grupo["nome_oficial"])
        with self.assertRaisesRegex(ValueError, "logradouro oficial"):
            logradouros.confirmar_grupos_visitas_positivas(
                self.path,
                [
                    {"chave": grupo["chave"], "nome_oficial": "Rua São João", "numero": "20"},
                    {"chave": grupo_incompleto["chave"], "nome_oficial": "Rua Inexistente", "numero": "30"},
                ],
                "João",
            )
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM visitas_enderecos_normalizados").fetchone()[0])
        finally:
            conn.close()
        result = logradouros.confirmar_grupos_visitas_positivas(
            self.path,
            [
                {"chave": grupo["chave"], "nome_oficial": "Rua São João", "numero": "20"},
                {"chave": grupo_incompleto["chave"], "nome_oficial": "Rua São João", "numero": "30"},
            ],
            "João",
        )
        self.assertEqual(2, result["grupos_confirmados"])
        self.assertEqual(2, result["visitas_vinculadas"])
        summary = logradouros.resumo(self.path)
        self.assertEqual(2, summary["enderecos_confirmados"])
        self.assertEqual(2, summary["visitas_vinculadas"])
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(
                "R. SAO Joao",
                conn.execute("SELECT logradouro FROM visitas WHERE id_visita='v-1'").fetchone()[0],
            )
            self.assertEqual(
                2,
                conn.execute("SELECT COUNT(*) FROM visitas_enderecos_normalizados").fetchone()[0],
            )
        finally:
            conn.close()
        vinculados = logradouros.listar_enderecos_vinculados(self.path)
        self.assertEqual(2, vinculados["total"])
        endereco_20 = next(item for item in vinculados["registros"] if item["numero_normalizado"] == "20")
        detalhe = logradouros.detalhar_endereco_vinculado(
            self.path, endereco_20["id_endereco"]
        )
        self.assertEqual("v-1", detalhe["visitas"][0]["id_visita"])
        removido = logradouros.desfazer_vinculo(
            self.path, detalhe["endereco"]["id_endereco"], "v-1"
        )
        self.assertTrue(removido["endereco_removido"])
        self.assertEqual(1, logradouros.previa_visitas_positivas(self.path)["total_visitas"])

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
                    tipo TEXT, localidade TEXT, id_localidade INTEGER, quarteirao INTEGER,
                    morador TEXT, visita TEXT
                );
                CREATE TABLE coletas (id_coleta TEXT PRIMARY KEY, id_visita TEXT);
                CREATE TABLE resultados_laboratorio (
                    id_coleta TEXT, aegypt_larvas INTEGER, aegypt_pupas INTEGER,
                    aegypt_exuvias INTEGER, aegypt_adulto INTEGER
                );
                """
            )
            conn.execute(
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("v-salgueiro", "Rua Salgueiro", "51", "2026-09-01", "TBO", "Sede", None, 10, None, "Normal"),
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
                "INSERT INTO visitas VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("v-oficial", "Rua dos Salgueiros", "51", "2026-09-02", "TBO", "Sede", None, 10, None, "Normal"),
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

    def test_geocodificacao_aceita_apenas_rua_numero_e_municipio_compativeis(self):
        id_endereco = self._criar_endereco()
        candidato = {
            "lat": "-25.321234", "lon": "-49.291234",
            "display_name": "Rua São João, 20, Almirante Tamandaré, Paraná, Brasil",
            "address": {
                "house_number": "20", "road": "Rua São João",
                "municipality": "Almirante Tamandaré", "country_code": "br",
            },
        }
        result = logradouros.geocodificar_endereco(
            self.path, id_endereco, geocoder=lambda rua, numero: [candidato]
        )
        self.assertEqual("automatico", result["status"])
        conn = db_core.connect(self.path)
        try:
            row = conn.execute(
                "SELECT * FROM enderecos_normalizados WHERE id_endereco=?", (id_endereco,)
            ).fetchone()
            self.assertEqual("automatico", row["geocodificacao_status"])
            self.assertAlmostEqual(-25.321234, row["latitude"])
            self.assertEqual("numero_exato", row["geocodificacao_precisao"])
        finally:
            conn.close()

    def test_geocodificacao_de_rua_sem_numero_fica_para_revisao(self):
        id_endereco = self._criar_endereco()
        candidato = {
            "lat": "-25.32", "lon": "-49.29",
            "display_name": "Rua São João, Almirante Tamandaré, Paraná, Brasil",
            "address": {
                "road": "Rua São João", "town": "Almirante Tamandaré",
                "country_code": "br",
            },
        }
        result = logradouros.geocodificar_endereco(
            self.path, id_endereco, geocoder=lambda rua, numero: [candidato]
        )
        self.assertEqual("aproximado", result["status"])
        conn = db_core.connect(self.path)
        try:
            row = conn.execute(
                "SELECT * FROM enderecos_normalizados WHERE id_endereco=?", (id_endereco,)
            ).fetchone()
            self.assertEqual("logradouro_aproximado", row["geocodificacao_precisao"])
        finally:
            conn.close()

    def test_endereco_sem_numero_nao_e_enviado_e_aceita_coordenada_manual(self):
        id_endereco = self._criar_endereco(numero="S/N")
        buscar = mock.Mock(return_value=[])
        result = logradouros.geocodificar_endereco(self.path, id_endereco, geocoder=buscar)
        buscar.assert_not_called()
        self.assertEqual("aguarda_manual", result["status"])

        manual = logradouros.salvar_coordenadas_manuais(
            self.path, id_endereco, "-25,3101", "-49,2902", "Maria"
        )
        self.assertEqual("manual", manual["status"])
        conn = db_core.connect(self.path)
        try:
            row = conn.execute(
                "SELECT * FROM enderecos_normalizados WHERE id_endereco=?", (id_endereco,)
            ).fetchone()
            self.assertEqual("Maria", row["geocodificado_por"])
            self.assertAlmostEqual(-25.3101, row["latitude"])
        finally:
            conn.close()
        with self.assertRaisesRegex(ValueError, "juntas"):
            logradouros.salvar_coordenadas_manuais(self.path, id_endereco, "-25", "")

    def test_falha_do_servico_fica_registrada_para_nova_tentativa(self):
        id_endereco = self._criar_endereco()

        def falhar(rua, numero):
            raise geocodificacao.GeocodificacaoErro("indisponível")

        with self.assertRaises(geocodificacao.GeocodificacaoErro):
            logradouros.geocodificar_endereco(self.path, id_endereco, geocoder=falhar)
        conn = db_core.connect(self.path)
        try:
            status = conn.execute(
                "SELECT geocodificacao_status FROM enderecos_normalizados WHERE id_endereco=?",
                (id_endereco,),
            ).fetchone()[0]
            self.assertEqual("erro", status)
        finally:
            conn.close()

    def test_migracao_postgresql_adiciona_campos_de_geocodificacao(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "migrations/postgresql/0008_geocodificacao_enderecos.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("ADD COLUMN latitude double precision", sql)
        self.assertIn("geocodificacao_status", sql)
        self.assertIn("idx_enderecos_geocodificacao_status", sql)


if __name__ == "__main__":
    unittest.main()
