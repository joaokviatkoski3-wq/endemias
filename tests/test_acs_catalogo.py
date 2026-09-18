import sqlite3
import unittest

from app_core import kobo_api
from app_core import visitas


class CatalogoAcsTests(unittest.TestCase):
    def test_le_catalogo_da_definicao_publicada_do_pve(self):
        conteudo = {
            "survey": [
                {
                    "$autoname": "Qual_quais_ACS",
                    "type": "select_multiple",
                    "select_from_list_name": "lista_acs",
                }
            ],
            "choices": [
                {
                    "list_name": "lista_acs",
                    "name": "ACS-026",
                    "label": ["Ana da Silva"],
                },
                {
                    "list_name": "lista_acs",
                    "name": "ACS-040",
                    "label": "Bruno dos Santos",
                },
                {
                    "list_name": "outra_lista",
                    "name": "IGNORAR",
                    "label": "Ignorado",
                },
            ],
        }

        self.assertEqual(
            kobo_api.catalogo_acs_pve_do_conteudo(conteudo),
            [
                {"codigo": "ACS-026", "nome": "Ana da Silva"},
                {"codigo": "ACS-040", "nome": "Bruno dos Santos"},
            ],
        )

    def test_sincroniza_rotulos_sem_alterar_codigos_das_visitas(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE acs_catalogo (
                   acs_codigo TEXT PRIMARY KEY,
                   nome TEXT NOT NULL,
                   atualizado_em TEXT NOT NULL
               )"""
        )
        try:
            primeiro = visitas.sincronizar_catalogo_acs(conn, [
                {"codigo": "ACS-026", "nome": "Ana da Silva"},
                {"codigo": "ACS-040", "nome": "Bruno dos Santos"},
            ])
            self.assertEqual(primeiro, {
                "total": 2,
                "criados": 2,
                "atualizados": 0,
                "inalterados": 0,
            })
            self.assertEqual(
                visitas.formatar_acs_codigos(
                    "ACS-026, ACS-040", visitas.catalogo_acs(conn)
                ),
                "Ana da Silva, Bruno dos Santos",
            )

            segundo = visitas.sincronizar_catalogo_acs(conn, [
                {"codigo": "ACS-026", "nome": "Ana Souza"},
                {"codigo": "ACS-040", "nome": "Bruno dos Santos"},
            ])
            self.assertEqual(segundo["atualizados"], 1)
            self.assertEqual(segundo["inalterados"], 1)
            self.assertEqual(
                visitas.formatar_acs_codigos(
                    "ACS-026", visitas.catalogo_acs(conn)
                ),
                "Ana Souza",
            )
        finally:
            conn.close()

    def test_mantem_fallback_para_codigo_historico_sem_catalogo(self):
        self.assertEqual(
            visitas.formatar_acs_codigos("maria_da_silva"),
            "Maria da Silva",
        )
