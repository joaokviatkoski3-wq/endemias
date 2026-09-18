import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class EsporotricoseVisitasDualTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = str(Path(self.tempdir.name) / "esporotricose.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE localidades (
                   id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE,
                   cod_localidade INTEGER
               )"""
        )
        conn.execute(
            """CREATE TABLE agentes (
                   id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE
               )"""
        )
        esporotricose.ensure_schema(conn)
        conn.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?, ?)", ("Tamboara", 1))
        conn.execute("INSERT INTO agentes(nome) VALUES (?)", ("Agente B",))
        agente_b = conn.execute(
            "SELECT id_agente FROM agentes WHERE nome=?", ("Agente B",)
        ).fetchone()[0]
        conn.execute("INSERT INTO agentes(nome) VALUES (?)", ("Agente A",))
        agente_a = conn.execute(
            "SELECT id_agente FROM agentes WHERE nome=?", ("Agente A",)
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                   id_visita, kobo_uuid, data, hora_inicio, agentes_texto,
                   localidade, quarteirao, logradouro, numero, morador,
                   telefone, visita, origem_estrutura, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "visita-dual",
                "uuid-visita-dual",
                "2026-07-28",
                "09:00",
                "Agente A, Agente B",
                "Tamboara",
                1405,
                "Rua das Flores",
                "25",
                "Maria",
                "41999990000",
                "Normal",
                "nova",
                "2026-07-28T10:00:00",
            ),
        )
        conn.executemany(
            """INSERT INTO esporotricose_visita_agentes(id_visita, id_agente)
               VALUES (?,?)""",
            (("visita-dual", agente_b), ("visita-dual", agente_a)),
        )
        conn.executemany(
            """INSERT INTO esporotricose_animais(
                   id_animal, id_visita, kobo_uuid, especie, nome, feridas,
                   vacinado, castrado, ambiente, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    "animal-dual-1",
                    "visita-dual",
                    "uuid-animal-dual-1",
                    "Gato",
                    "Tilapia",
                    "Sim",
                    "Sim",
                    "Não",
                    "Domiciliado",
                    "2026-07-28T10:00:00",
                ),
                (
                    "animal-dual-2",
                    "visita-dual",
                    "uuid-animal-dual-2",
                    "Cão",
                    "Lobo",
                    "Não",
                    "Desconhecido",
                    "Sim",
                    "Semidomiciliado",
                    "2026-07-28T10:00:00",
                ),
            ),
        )
        conn.commit()
        conn.close()

    def test_lista_visita_sem_duplicar_animais_ou_agentes(self):
        dados = esporotricose.listar_visitas(
            self.db_path, {"busca": "1405"}
        )

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["registros"][0]["animais"], 2)
        self.assertEqual(
            dados["registros"][0]["agentes"],
            "Agente A, Agente B",
        )

    def test_busca_aceita_data_e_lista_animais_com_detalhes(self):
        visitas = esporotricose.listar_visitas(
            self.db_path, {"busca": "2026-07-28"}
        )
        animais = esporotricose.listar_animais(
            self.db_path,
            {
                "busca": "Tilapia",
                "especie": ["Gato"],
                "feridas": ["Sim"],
            },
        )

        self.assertEqual(visitas["total"], 1)
        self.assertEqual(animais["total"], 1)
        self.assertEqual(animais["registros"][0]["nome"], "Tilapia")
        self.assertEqual(
            animais["registros"][0]["motivo_atencao"],
            "Ferida informada",
        )

    def test_edita_visita_animal_e_resume_localidade(self):
        esporotricose.atualizar_visita(
            self.db_path,
            "visita-dual",
            {"observacoes": "Revisada", "quarteirao": 1406},
        )
        esporotricose.atualizar_animal(
            self.db_path,
            "animal-dual-1",
            {"evolucao_caso": "Em acompanhamento"},
        )
        localidades = esporotricose.resumo_localidades(self.db_path)
        visitas = esporotricose.listar_visitas(
            self.db_path, {"busca": "1406"}
        )
        animais = esporotricose.listar_animais(
            self.db_path, {"busca": "Tilapia"}
        )

        self.assertEqual(visitas["registros"][0]["observacoes"], "Revisada")
        self.assertEqual(
            animais["registros"][0]["evolucao_caso"],
            "Em acompanhamento",
        )
        self.assertEqual(localidades["registros"][0]["visitas"], 1)
        self.assertEqual(localidades["registros"][0]["animais"], 2)

    def test_cria_historico_por_imovel_para_visitas_exatas(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                    id_visita, kobo_uuid, data, localidade, quarteirao, logradouro, numero,
                    morador, visita, origem_estrutura, processado_em
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("visita-dual-2", "uuid-visita-dual-2", "2026-08-03", "Tamboara", 1405,
             "R. das Flores", "25", "José", "Normal", "nova", "2026-08-03T10:00:00"),
        )
        conn.execute(
            """INSERT INTO esporotricose_animais(id_animal, id_visita, kobo_uuid, especie, nome, processado_em)
                VALUES (?,?,?,?,?,?)""",
            ("animal-dual-3", "visita-dual-2", "uuid-animal-dual-3", "Gato", "Pipoca", "2026-08-03T10:00:00"),
        )
        conn.commit()
        conn.close()

        previa = esporotricose.previsualizar_vinculos_imoveis(self.db_path)
        self.assertEqual(previa["aptas"], 2)
        self.assertEqual(previa["grupos_com_historico"], 1)
        resultado = esporotricose.vincular_visitas_exatas(self.db_path)
        self.assertEqual(resultado["vinculadas"], 2)
        imoveis = esporotricose.listar_imoveis(self.db_path)
        self.assertEqual(imoveis["total"], 1)
        self.assertEqual(imoveis["registros"][0]["visitas"], 2)
        detalhe = esporotricose.detalhe_imovel(self.db_path, imoveis["registros"][0]["id_imovel"])
        self.assertEqual(len(detalhe["visitas"]), 2)
        self.assertEqual({item["nome"] for item in detalhe["animais"]}, {"Tilapia", "Lobo", "Pipoca"})
        self.assertEqual({item["morador"] for item in detalhe["tutores"]}, {"Maria", "José"})

    def test_vinculo_manual_nao_muda_campos_originais_da_visita(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                    id_visita, kobo_uuid, data, localidade, quarteirao, logradouro, numero,
                    visita, origem_estrutura, processado_em
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("visita-dual-3", "uuid-visita-dual-3", "2026-08-03", "Tamboara", 1405,
             "Rua das Flore", "25", "Normal", "nova", "2026-08-03T10:00:00"),
        )
        conn.commit()
        conn.close()

        resultado = esporotricose.vincular_visitas_manual(
            self.db_path, ["visita-dual", "visita-dual-3"]
        )
        self.assertEqual(resultado["vinculadas"], 2)
        conn = sqlite3.connect(self.db_path)
        logradouro = conn.execute(
            "SELECT logradouro FROM esporotricose_visitas WHERE id_visita='visita-dual-3'"
        ).fetchone()[0]
        origem = conn.execute(
            "SELECT origem FROM esporotricose_visita_imoveis WHERE id_visita='visita-dual-3'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(logradouro, "Rua das Flore")
        self.assertEqual(origem, "manual")


if __name__ == "__main__":
    unittest.main()
