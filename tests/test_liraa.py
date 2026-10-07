import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape
from flask import Flask

from app_core import liraa
from app_core import registro_geografico as rg_core
from blueprints.liraa import bp as liraa_bp
from blueprints.auth import bp as auth_bp


ROOT = Path(__file__).resolve().parents[1]


def camada(quarteiroes=("0001", "0002", "0003", "0004", "0005")):
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"Localidade": "Sede" if i < 3 else "Graziela", "id_Q": q},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-49.30 + i * .01, -25.30], [-49.295 + i * .01, -25.30],
             [-49.30 + i * .01, -25.305], [-49.30 + i * .01, -25.30]]]}}
        for i, q in enumerate(quarteiroes)
    ]}, ensure_ascii=False).encode("utf-8")


class LiraaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "liraa.db")
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        conn.executescript("""CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT NOT NULL);
            CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER);
            INSERT INTO localidades VALUES (1,'Sede');
            INSERT INTO localidades VALUES (2,'Graziela');""")
        rg_core.ensure_schema(conn)
        conn.commit()
        conn.close()
        self.importar(camada())

    def importar(self, arquivo):
        previa = rg_core.preview_importacao_geojson(self.db, arquivo, "quarteiroes.geojson", self.temp.name)
        rg_core.importar_geojson(self.db, arquivo, "quarteiroes.geojson", previa["sha256"], self.temp.name)

    def criar(self):
        return liraa.criar_ciclo(self.db, {"ano": 2026, "nome": "1º LIRAa", "inicio": "2026-10-01"})

    def estrato(self, ciclo, localidades=(1, 2), n=9000, tipo="normal"):
        return liraa.salvar_estrato(self.db, ciclo, {
            "numero": 1, "tipo": tipo, "imoveis_confirmados": n,
            "localidades": list(localidades)}, base_dir=self.temp.name)

    def test_inventario_deduplica_geometria_e_exclui_pe(self):
        conn = sqlite3.connect(self.db)
        q = conn.execute("""INSERT INTO registro_geografico_quarteiroes
            (id_localidade,localidade,quarteirao,criado_em,atualizado_em)
            VALUES (1,'Sede','0001','2026-09-30','2026-09-30')""").lastrowid
        for tipo, condo in (("R", 4), ("C", 0), ("PE", 0), ("REF", 0)):
            conn.execute("""INSERT INTO registro_geografico_imoveis
                (id_quarteirao,id_localidade,localidade,quarteirao,logradouro,numero,tipo,condominio,criado_em,atualizado_em)
                VALUES (?,1,'Sede','0001','Rua Teste','1',?,?,'2026-09-30','2026-09-30')""", (q, tipo, condo))
        conn.commit()
        conn.close()
        dados = liraa.inventario(self.db, self.temp.name)
        self.assertEqual(len(dados["quarteiroes"]), 5)
        sede = next(r for r in dados["localidades"] if r["nome"] == "Sede")
        self.assertEqual(sede["registros_rg_sem_pe"], 2)
        self.assertEqual(sede["unidades_rg_sem_pe"], 5)
        self.assertEqual(sede["pe_rg"], 1)

    def test_ciclo_estrato_sorteio_congela_snapshot(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        primeiro = liraa.sortear(self.db, estrato, self.temp.name, seed=123)
        self.assertEqual(primeiro["a"], 5)
        self.assertEqual(primeiro["q"], 1)
        self.assertEqual(primeiro["n"], 429)
        self.assertEqual(len({r["quarteirao"] for r in primeiro["selecionados"]}), 2)
        with self.assertRaisesRegex(liraa.LiraaError, "já foi sorteado"):
            liraa.sortear(self.db, estrato, self.temp.name, seed=123)
        with self.assertRaisesRegex(liraa.LiraaError, "congelado"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "localidades": [1, 2]}, estrato, self.temp.name)
        self.importar(camada(("0001", "0002", "0003", "0004", "0006")))
        salvo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["sorteio"]
        self.assertEqual(salvo["selecionados"], primeiro["selecionados"])
        self.assertEqual(salvo["q"], 1)

    def test_sorteio_anterior_ganha_posicao_local_sem_mudar_snapshot(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=42)
        conn = sqlite3.connect(self.db)
        original = conn.execute("SELECT selecionados_json FROM liraa_sorteios").fetchone()[0]
        legado = json.loads(original)
        for row in legado:
            row.pop("ordem_localidade", None)
            row.pop("inicio_local", None)
        conn.execute("UPDATE liraa_sorteios SET selecionados_json=?",
                     (json.dumps(legado, ensure_ascii=False),))
        conn.commit()
        salvo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["sorteio"]
        self.assertTrue(all(row["ordem_localidade"] >= 1 for row in salvo["selecionados"]))
        self.assertEqual(conn.execute("SELECT selecionados_json FROM liraa_sorteios").fetchone()[0],
                         json.dumps(legado, ensure_ascii=False))
        conn.close()

    def test_sem_localidade_repetida_ou_duplo_uso_no_ciclo(self):
        ciclo = self.criar()
        self.estrato(ciclo, (1,))
        with self.assertRaisesRegex(liraa.LiraaError, "repita"):
            self.estrato(ciclo, (2, 2))
        with self.assertRaisesRegex(liraa.LiraaError, "já pertencem a outro estrato"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "localidades": [1]}, base_dir=self.temp.name)

    def test_localidade_dividida_entre_estratos_e_universo_exato(self):
        ciclo = self.criar()
        primeiro = liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001", "1:0002"]}, base_dir=self.temp.name)
        segundo = liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0003", "2:0004"]}, base_dir=self.temp.name)
        dados = liraa.painel(self.db, self.temp.name)["ciclos"][0]
        self.assertEqual(dados["quarteiroes_sem_estrato"], 1)
        self.assertEqual(dados["estratos"][0]["quarteiroes"], ["1:0001", "1:0002"])
        self.assertEqual(liraa.sortear(self.db, primeiro, self.temp.name, seed=4)["a"], 2)
        self.assertEqual(liraa.sortear(self.db, segundo, self.temp.name, seed=5)["a"], 2)

    def test_rejeita_sobreposicao_e_quarteirao_fora_da_camada(self):
        ciclo = self.criar()
        self.estrato(ciclo, (1,))
        with self.assertRaisesRegex(liraa.LiraaError, "outro estrato"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "quarteiroes": ["1:0001"]}, base_dir=self.temp.name)
        with self.assertRaisesRegex(liraa.LiraaError, "ausente da camada"):
            liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "normal",
                "imoveis_confirmados": 9000, "quarteiroes": ["2:9999"]}, base_dir=self.temp.name)
        self.assertEqual(len(liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"]), 1)

    def test_edicao_libera_quarteirao_para_outro_estrato(self):
        ciclo = self.criar()
        primeiro = liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001", "1:0002"]}, base_dir=self.temp.name)
        liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001"]}, primeiro, self.temp.name)
        segundo = liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0002"]}, base_dir=self.temp.name)
        self.assertEqual(liraa.sortear(self.db, segundo, self.temp.name, seed=2)["a"], 1)

    def test_mudanca_da_camada_sinaliza_ausente_e_bloqueia_sorteio(self):
        ciclo = self.criar()
        estrato = liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001", "1:0002"]}, base_dir=self.temp.name)
        self.importar(camada(("0001", "0006", "0003", "0004", "0005")))
        self.assertEqual(liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["ausentes"], 1)
        with self.assertRaisesRegex(liraa.LiraaError, "ausentes"):
            liraa.sortear(self.db, estrato, self.temp.name, seed=1)

    def test_plano_antigo_por_localidade_pode_ser_convertido(self):
        ciclo = self.criar()
        liraa.painel(self.db, self.temp.name)  # instala o schema local
        conn = sqlite3.connect(self.db)
        estrato = conn.execute("""INSERT INTO liraa_estratos
            (id_ciclo,numero,tipo,imoveis_confirmados,observacoes,criado_em,atualizado_em)
            VALUES (?,1,'reduzido',4000,'','2026-09-30','2026-09-30')""", (ciclo,)).lastrowid
        conn.execute("INSERT INTO liraa_estrato_localidades VALUES (?,?,1)", (estrato, ciclo))
        conn.commit()
        conn.close()
        atual = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]
        self.assertEqual(atual["quarteiroes"], ["1:0001", "1:0002", "1:0003"])
        self.assertTrue(atual["legado_localidades"])
        liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001"]}, estrato, self.temp.name)
        novo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]
        self.assertEqual(novo["quarteiroes"], ["1:0001"])
        self.assertFalse(novo["legado_localidades"])
        self.assertEqual(liraa.sortear(self.db, estrato, self.temp.name, seed=1)["a"], 1)

    def test_ciclo_pode_ser_corrigido_antes_e_congelado_depois(self):
        vazio = self.criar()
        liraa.atualizar_ciclo(self.db, vazio, {"ano": 2026, "nome": "2º LIRAa"})
        liraa.excluir_ciclo(self.db, vazio)
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=55)
        with self.assertRaisesRegex(liraa.LiraaError, "congelado"):
            liraa.atualizar_ciclo(self.db, ciclo, {"ano": 2026, "nome": "Alterado"})

    def test_excluir_estrato_sorteado_remove_sorteio_e_libera_quarteiroes(self):
        ciclo = self.criar()
        primeiro = liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001", "1:0002"]}, base_dir=self.temp.name)
        segundo = liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["2:0004"]}, base_dir=self.temp.name)
        liraa.sortear(self.db, primeiro, self.temp.name, seed=1)
        liraa.sortear(self.db, segundo, self.temp.name, seed=2)
        detalhes = liraa.excluir_estrato(self.db, primeiro)
        self.assertEqual(detalhes, {"id_ciclo": ciclo, "numero": 1, "sorteios_excluidos": 1})
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_sorteios").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_estrato_quarteiroes WHERE id_estrato=?",
                                      (primeiro,)).fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT id_estrato FROM liraa_estratos").fetchone()[0], segundo)
        conn.close()
        novo = liraa.salvar_estrato(self.db, ciclo, {"numero": 1, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "quarteiroes": ["1:0001"]}, base_dir=self.temp.name)
        self.assertNotEqual(novo, primeiro)

    def test_excluir_ciclo_com_sorteios_preserva_outro_ciclo(self):
        ciclo = self.criar()
        primeiro = self.estrato(ciclo, (1,))
        liraa.salvar_estrato(self.db, ciclo, {"numero": 2, "tipo": "reduzido",
            "imoveis_confirmados": 4000, "localidades": [2]}, base_dir=self.temp.name)
        liraa.sortear(self.db, primeiro, self.temp.name, seed=1)
        outro = liraa.criar_ciclo(self.db, {"ano": 2027, "nome": "Outro ciclo"})
        segundo = self.estrato(outro)
        liraa.sortear(self.db, segundo, self.temp.name, seed=2)
        detalhes = liraa.excluir_ciclo(self.db, ciclo)
        self.assertEqual((detalhes["estratos_excluidos"], detalhes["sorteios_excluidos"]), (2, 1))
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT id_ciclo FROM liraa_ciclos").fetchone()[0], outro)
        self.assertEqual(conn.execute("SELECT id_estrato FROM liraa_sorteios").fetchone()[0], segundo)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_estrato_quarteiroes").fetchone()[0], 5)
        conn.close()
        with self.assertRaisesRegex(liraa.LiraaError, "não encontrado"):
            liraa.excluir_ciclo(self.db, ciclo)

    def test_falha_de_auditoria_desfaz_exclusao_e_sorteio(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=1)
        def falhar(_conn, _detalhes):
            raise RuntimeError("falha simulada na auditoria")
        with self.assertRaisesRegex(RuntimeError, "falha simulada"):
            liraa.excluir_estrato(self.db, estrato, auditar=falhar)
        with self.assertRaisesRegex(RuntimeError, "falha simulada"):
            liraa.excluir_ciclo(self.db, ciclo, auditar=falhar)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_ciclos").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_estratos").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_sorteios").fetchone()[0], 1)
        conn.close()

    def test_faixa_de_imoveis_e_formula_do_manual(self):
        universo = [{"id_localidade": 1, "quarteirao": str(i)} for i in range(1, 351)]
        calculo = liraa._calcular_sorteio(9000, universo, "normal", 123)
        self.assertEqual((calculo["n"], calculo["a"], calculo["b"], calculo["q"]),
                         (429, 350, 26, 83))
        self.assertEqual(len({r["ordem_universo"] for r in calculo["selecionados"]}), 83)
        self.assertEqual(calculo, liraa._calcular_sorteio(9000, universo, "normal", 123))
        with self.assertRaisesRegex(liraa.LiraaError, "8.100"):
            liraa._calcular_sorteio(4000, universo, "normal", 123)
        self.assertEqual(liraa._calcular_sorteio(4000, universo, "reduzido", 123)["fracao"], .5)

    def test_parametros_conferem_com_cinco_estratos_do_relatorio_legado(self):
        casos = [
            (12104, 325, "normal", 434, 38, 57),
            (10214, 266, "normal", 431, 39, 55),
            (9312, 228, "normal", 429, 41, 52),
            (12071, 349, "normal", 434, 35, 62),
            (5090, 166, "reduzido", 238, 31, 15),
        ]
        for N, A, tipo, n, B, Q in casos:
            with self.subTest(N=N, A=A):
                plano = liraa._plano_amostral(N, A, tipo)
                self.assertEqual((plano["n"], plano["b"], plano["q"]), (n, B, Q))
                self.assertAlmostEqual(plano["intervalo"], A / Q)

    def test_sorteio_por_localidade_reproduz_relatorio_legado(self):
        # Listas do usuario, "Definicao de Quarteiroes" (nov/2026).
        # O IC exato do estrato 3 foi inferido; o plano impresso mostra apenas 2.
        casos = [
            (57, "3", [
                ("Lamenha", 192, "3 8 14 20 25 31 37 42 48 54 60 65 71 77 82 88 94 99 105 111 117 122 128 134 139 145 151 156 162 168 174 179 185 191"),
                ("Tanguá", 133, "5 10 16 22 27 33 39 44 50 56 62 67 73 79 84 90 96 101 107 113 119 124 130"),
            ]),
            (55, "2", [
                ("Cachoeira", 113, "2 6 11 16 21 26 31 35 40 45 50 55 60 64 69 74 79 84 89 93 98 103 108"),
                ("Roma", 153, "1 5 10 15 20 25 30 34 39 44 49 54 59 63 68 73 78 83 88 92 97 102 107 112 117 121 126 131 136 141 146 150"),
            ]),
            (52, "2.9", [
                ("São Venâncio", 72, "3 7 11 16 20 24 29 33 38 42 46 51 55 60 64 68"),
                ("Tamboara", 72, "1 5 9 14 18 22 27 31 36 40 44 49 53 58 62 66 71"),
                ("Graziela", 84, "4 8 12 17 21 25 30 34 39 43 47 52 56 61 65 69 74 78 82"),
            ]),
            (62, "4", [
                ("Paraíso", 131, "4 9 15 20 26 32 37 43 49 54 60 65 71 77 82 88 94 99 105 110 116 122 127"),
                ("Sede", 218, "2 7 13 18 24 30 35 41 47 52 58 63 69 75 80 86 92 97 103 108 114 120 125 131 137 142 148 153 159 165 170 176 182 187 193 199 204 210 215"),
            ]),
            (15, "1", [
                ("Tranqueira", 93, "1 12 23 34 45 56 67 78 89"),
                ("São João Batista", 35, "8 19 30"),
                ("Rosana", 38, "6 17 28"),
            ]),
        ]
        total = 0
        for estrato, (q_planejado, ic, localidades) in enumerate(casos, 1):
            universo = [{"id_localidade": j, "localidade": nome, "quarteirao": str(numero)}
                        for j, (nome, quantidade, _) in enumerate(localidades, 1)
                        for numero in range(1, quantidade + 1)]
            selecionados = liraa._selecionar_por_localidade(universo, q_planejado, ic)
            self.assertEqual(len(selecionados), q_planejado, f"Estrato {estrato}")
            for j, (_, _, lista) in enumerate(localidades, 1):
                esperado = [int(x) for x in lista.split()]
                encontrado = [r["ordem_localidade"] for r in selecionados
                              if r["id_localidade"] == j]
                self.assertEqual(encontrado, esperado, f"Estrato {estrato}, localidade {j}")
                total += len(encontrado)
        self.assertEqual(total, 241)

    def test_inicio_e_arredondamento_da_posicao_local(self):
        self.assertEqual(liraa._arredondar_metade_para_cima(5, 2), 3)
        with self.assertRaisesRegex(liraa.LiraaError, "início casual"):
            liraa._selecionar_por_localidade([{"id_localidade": 1}], 1, 0)

    def test_posicao_local_nao_e_numero_municipal_do_quarteirao(self):
        ids = [101, 103, 107, 240, 500, 900]
        universo = [{"id_localidade": 1, "quarteirao": str(i)} for i in ids]
        selecionados = liraa._selecionar_por_localidade(universo, 3, 1)
        self.assertEqual([r["ordem_localidade"] for r in selecionados], [1, 3, 5])
        self.assertEqual([r["quarteirao"] for r in selecionados], ["101", "107", "500"])

    def test_selecao_por_localidade_permanece_unica_e_no_universo(self):
        rng = random.Random(20261001)
        for _ in range(100):
            A = rng.randint(1, 900)
            Q = rng.randint(1, A)
            inicio = rng.random() * (A / Q) or (A / Q) / 2
            universo = [{"id_localidade": i // 100, "quarteirao": str(i)}
                        for i in range(1, A + 1)]
            selecionados = liraa._selecionar_por_localidade(universo, Q, inicio)
            ordens = [r["ordem_universo"] for r in selecionados]
            self.assertEqual(len(ordens), len(set(ordens)))
            self.assertTrue(all(1 <= indice <= A for indice in ordens))

    def test_template_renderiza_planejamento_e_sem_exportacao_falsa(self):
        ciclo = self.criar()
        estrato = self.estrato(ciclo)
        liraa.sortear(self.db, estrato, self.temp.name, seed=42)
        env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html"]))
        env.globals.update({"csrf_token": lambda: "teste", "url_for": lambda name, **kw: "/" + name,
                            "get_flashed_messages": lambda **kw: []})
        html = env.get_template("liraa.html").render(dados=liraa.painel(self.db, self.temp.name),
                                                       erro=None, editando=None, is_admin=True,
                                                       APP_VERSION_LABEL="Teste", TIPO_CORES={},
                                                       TIPO_LABELS={}, AGENDA_TIPO_LABELS={},
                                                         sidebar_groups=[], request=SimpleNamespace(endpoint="liraa.page", args={}))
        self.assertIn("Pontos Estratégicos", html)
        self.assertIn("Novo ciclo", html)
        self.assertIn("Mapa dos estratos", html)
        self.assertIn("Mapa geral · consulta", html)
        self.assertIn('id="liraa-geral-mapa"', html)
        self.assertIn('id="liraa-geral-ciclo"', html)
        self.assertIn('id="liraa-geral-detalhe"', html)
        self.assertIn('liraa_mapa_geral.js', html)
        geral = html.split('id="liraa-tab-geral"', 1)[1].split('id="liraa-tab-importar"', 1)[0]
        self.assertNotIn('<form', geral)
        self.assertNotIn('Sortear ensaio', geral)
        self.assertIn("Selecionar localidade inteira", html)
        self.assertIn("liraa-dados-json", html)
        self.assertIn("Sorteio registrado", html)
        self.assertIn("Excluir ciclo e seus 1 estratos", html)
        self.assertIn("Excluir estrato e sorteio", html)
        self.assertRegex(html, r"Ver \d+ quarteir")
        self.assertIn("Início local", html)
        self.assertIn("Posição sorteada (1 a A)", html)
        self.assertIn("Quarteirão municipal", html)
        self.assertIn("exportação", html)
        self.assertNotIn("Baixar .lira", html)

    def test_rota_exige_login_e_admin_para_gravar(self):
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE usuarios (
            id_usuario INTEGER PRIMARY KEY, usuario TEXT, nome TEXT, nivel TEXT, ativo INTEGER)""")
        conn.execute("INSERT INTO usuarios VALUES (1,'teste','Teste','visualizador',1)")
        conn.commit()
        conn.close()
        app = Flask(__name__, template_folder=str(ROOT / "templates"))
        app.secret_key = "teste-isolado"
        app.config.update(DB_PATH=self.db, DB_BACKEND="sqlite", BASE_DIR=self.temp.name)
        app.register_blueprint(auth_bp)
        app.register_blueprint(liraa_bp)
        app.jinja_env.globals.update(csrf_token=lambda: "teste")
        @app.context_processor
        def contexto():
            return {"TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {},
                    "sidebar_groups": [], "APP_VERSION_LABEL": "Teste"}
        with app.test_client() as client:
            self.assertEqual(client.get("/liraa").status_code, 302)
            with client.session_transaction() as session:
                session["uid"] = 1
            consulta = client.get("/liraa")
            self.assertEqual(consulta.status_code, 200)
            self.assertIn("Mapa geral · consulta", consulta.get_data(as_text=True))
            self.assertEqual(client.post("/liraa/ciclos", data={"ano": 2026, "nome": "1º"}).status_code, 403)
            self.assertEqual(client.post("/liraa/kobo/importar", data={}).status_code, 403)
            self.assertEqual(client.post("/liraa/visitas/1/excluir", data={}).status_code, 403)
            conn = sqlite3.connect(self.db)
            conn.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=1")
            conn.commit()
            conn.close()
            response = client.post("/liraa/ciclos", data={"ano": 2026, "nome": "1º"}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("1º", response.get_data(as_text=True))
            ciclo = liraa.painel(self.db, self.temp.name)["ciclos"][0]["id_ciclo"]
            response = client.post(f"/liraa/ciclos/{ciclo}/estratos", data={
                "numero": "1", "tipo": "normal", "imoveis_confirmados": "9000",
                "localidades": ["1", "2"]}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Estrato 1", response.get_data(as_text=True))
            estrato = liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["id_estrato"]
            response = client.post(f"/liraa/estratos/{estrato}/sortear", follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Sorteio registrado", response.get_data(as_text=True))
            sem_confirmacao = client.post(f"/liraa/estratos/{estrato}/excluir", follow_redirects=True)
            self.assertIn("Confirme a exclusão", sem_confirmacao.get_data(as_text=True))
            self.assertEqual(len(liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"]), 1)
            conn = sqlite3.connect(self.db)
            conn.execute("UPDATE usuarios SET nivel='visualizador' WHERE id_usuario=1")
            conn.commit()
            conn.close()
            self.assertEqual(client.post(f"/liraa/estratos/{estrato}/excluir",
                                         data={"confirmar_exclusao": "sim"}).status_code, 403)
            self.assertEqual(client.post(f"/liraa/ciclos/{ciclo}/excluir",
                                         data={"confirmar_exclusao": "sim"}).status_code, 403)
            conn = sqlite3.connect(self.db)
            conn.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=1")
            conn.commit()
            conn.close()
            removido = client.post(f"/liraa/estratos/{estrato}/excluir",
                                   data={"confirmar_exclusao": "sim"}, follow_redirects=True)
            self.assertEqual(removido.status_code, 200)
            self.assertEqual(liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"], [])
            conn = sqlite3.connect(self.db)
            evento_estrato = conn.execute("SELECT detalhes_json FROM auditoria_eventos WHERE acao='liraa_estrato_excluido'").fetchone()
            self.assertEqual(json.loads(evento_estrato[0])["sorteios_excluidos"], 1)
            conn.close()
            novo_estrato = self.estrato(ciclo)
            liraa.sortear(self.db, novo_estrato, self.temp.name, seed=3)
            apagado = client.post(f"/liraa/ciclos/{ciclo}/excluir",
                                  data={"confirmar_exclusao": "sim"}, follow_redirects=True)
            self.assertEqual(apagado.status_code, 200)
            self.assertEqual(liraa.painel(self.db, self.temp.name)["ciclos"], [])
            conn = sqlite3.connect(self.db)
            evento = conn.execute("SELECT detalhes_json FROM auditoria_eventos WHERE acao='liraa_ciclo_excluido'").fetchone()
            self.assertEqual(json.loads(evento[0])["sorteios_excluidos"], 1)
            conn.close()

    def test_rota_recebe_selecao_por_quarteirao(self):
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE usuarios (
            id_usuario INTEGER PRIMARY KEY, usuario TEXT, nome TEXT, nivel TEXT, ativo INTEGER)""")
        conn.execute("INSERT INTO usuarios VALUES (1,'teste','Teste','admin',1)")
        conn.commit()
        conn.close()
        app = Flask(__name__, template_folder=str(ROOT / "templates"))
        app.secret_key = "teste-isolado"
        app.config.update(DB_PATH=self.db, DB_BACKEND="sqlite", BASE_DIR=self.temp.name)
        app.register_blueprint(auth_bp)
        app.register_blueprint(liraa_bp)
        app.jinja_env.globals.update(csrf_token=lambda: "teste")
        @app.context_processor
        def contexto():
            return {"TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {},
                    "sidebar_groups": [], "APP_VERSION_LABEL": "Teste"}
        ciclo = self.criar()
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["uid"] = 1
            response = client.post(f"/liraa/ciclos/{ciclo}/estratos", data={
                "numero": "1", "tipo": "reduzido", "imoveis_confirmados": "4000",
                "quarteiroes": ["1:0001", "2:0004"]}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("2 quarteirões", response.get_data(as_text=True))
        self.assertEqual(liraa.painel(self.db, self.temp.name)["ciclos"][0]["estratos"][0]["quarteiroes"],
                         ["1:0001", "2:0004"])


if __name__ == "__main__":
    unittest.main()
