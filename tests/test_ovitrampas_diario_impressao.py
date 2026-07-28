import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


class OvitrampasDiarioImpressaoTests(unittest.TestCase):
    def test_imprime_somente_as_linhas_das_armadilhas_cadastradas(self):
        templates_dir = Path(__file__).resolve().parents[1] / "templates"
        ambiente = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html"]),
        )
        template = ambiente.get_template("ovitrampas_diario_impressao.html")
        registros = [
            {
                "ovitrampa_id": "129",
                "rua": "Rua Jose Real Prado",
                "numero": "210",
                "complemento": "Mercado",
                "quarteirao": "0739",
                "localizacao": "Ao lado do portao",
                "telefone_responsavel": "",
                "responsavel": "Joao",
            },
            {
                "ovitrampa_id": "130",
                "rua": "Rua Manoel Barbosa",
                "numero": "207",
                "complemento": "Condominio",
                "quarteirao": "0746",
                "localizacao": "Casa de gas a direita",
                "telefone_responsavel": "",
                "responsavel": "Maria",
            },
        ]

        html = template.render(
            diario={"nome": "Sao Francisco"},
            registros=registros,
            semana=None,
        )

        self.assertEqual(html.count('class="trap-id"'), len(registros))
        self.assertNotIn("linhas_vazias", html)
        self.assertIn("Ocorr&ecirc;ncias", html)
        self.assertNotIn("Laborat&oacute;rio", html)
        self.assertNotIn('class="col-head">Ovos</th>', html)
        self.assertNotIn('class="col-head">Larva</th>', html)
        self.assertIn('<td colspan="15" class="field-head">Campo</td>', html)
        self.assertNotIn('class="r55"', html)
        self.assertNotIn("Di&aacute;rio<br>Conta ovos", html)
        self.assertEqual(html.count('class="alter-head"'), 1)
        self.assertNotIn("Agentes instala&ccedil;&atilde;o:", html)
        self.assertNotIn("Agentes troca:", html)
        self.assertNotIn("Agentes retirada:", html)
        self.assertIn('class="alter-head-cell">Agentes</th>', html)
        self.assertNotIn("dh-semana", html)


if __name__ == "__main__":
    unittest.main()
