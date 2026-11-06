import unittest
from app_core.formulario_condicoes import analisar,avaliar


class CondicoesTests(unittest.TestCase):
    def test_dependencia_e_operadores(self):
        tree=analisar("${Visita} = 'normal' or ${Visita} = 'recuperado'")
        self.assertTrue(avaliar(tree,{'Visita':'normal'}))
        self.assertFalse(avaliar(tree,{'Visita':'fechado'}))

    def test_selecao_multipla_sem_eval(self):
        tree=analisar("not(selected(., 'no-ace') and count-selected(.) > 1)")
        self.assertTrue(avaliar(tree,{},'joao-ficticio'))
        self.assertFalse(avaliar(tree,{},'no-ace joao-ficticio'))

    def test_filtro_liraa_condicional(self):
        tree=analisar("(localidade=${Localidade} and quarteirao_rg=string(number(if(${Quarteir_o} = 'outros', ${Quarteir_o_outros}, ${Quarteir_o})))) or name='outro'")
        values={'Localidade':'bairro-teste','Quarteir_o':'outros','Quarteir_o_outros':42}
        self.assertTrue(avaliar(tree,values,choice={'localidade':'bairro-teste','quarteirao_rg':'42','name':'rua'}))
        self.assertFalse(avaliar(tree,values,choice={'localidade':'outro-bairro','quarteirao_rg':'42','name':'rua'}))

    def test_datas_texto_obrigatoriedade(self):
        self.assertTrue(avaliar(analisar(". >= date('2026-11-09') and . <= date('2026-11-13')"),{},'2026-11-10'))
        self.assertFalse(avaliar(analisar("string-length(normalize-space(.)) > 0"),{},'   '))
        self.assertTrue(avaliar(analisar(True),{}))

    def test_rejeita_execucao_e_sintaxe_desconhecida(self):
        for bad in ("__import__('os')",'fetch(1)',"${a} = 'x'; 1",'${a} [1]'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):analisar(bad)
