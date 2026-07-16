import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TableSortingTests(unittest.TestCase):
    def test_componente_global_tem_texto_numero_data_e_teclado(self):
        javascript = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

        self.assertIn("function tableSortValue", javascript)
        self.assertIn("type === 'number'", javascript)
        self.assertIn("type === 'date'", javascript)
        self.assertIn("new Intl.Collator('pt-BR'", javascript)
        self.assertIn("event.key === 'Enter' || event.key === ' '", javascript)
        self.assertIn("window.refreshSortableTable", javascript)
        self.assertIn('th.sort[aria-sort="ascending"]', css)
        self.assertIn('th.sort[aria-sort="descending"]', css)

    def test_esporotricose_aplica_ordenacao_nas_tabelas_adequadas(self):
        html = (ROOT / "templates" / "esporotricose.html").read_text(encoding="utf-8")
        tabelas = (
            "esp-resumo-visitas-table",
            "esp-visitas-table",
            "esp-animais-table",
            "esp-doentes-table",
            "doe-res-atencao-table",
            "esp-localidades-table",
        )

        for tabela in tabelas:
            self.assertIn(f'id="{tabela}" data-sortable-table', html)
            self.assertIn(f"refreshSortableTable('{tabela}')", html)
        self.assertIn("data-sort-detail data-detail-id", html)
        self.assertIn('data-sort-type="date"', html)
        self.assertIn('data-sort-type="number"', html)
        self.assertIn('data-sort-type="text"', html)


if __name__ == "__main__":
    unittest.main()
