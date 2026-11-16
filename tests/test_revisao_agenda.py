import unittest
from datetime import datetime

from blueprints.agenda import _eventos_manuais_expandido


class RecorrenciaMensalTests(unittest.TestCase):
    def test_mantem_dia_original_depois_de_fevereiro(self):
        row = dict(id_evento=1, titulo='Teste', data_inicio='2027-01-31', data_fim=None,
                   dia_inteiro=1, recorrencia='mensal', recorrencia_fim=None, cor=None,
                   tipo='outro', descricao='', lembrete_min=None, criado_por='', atividade_externa=0)
        eventos = _eventos_manuais_expandido(row, datetime(2027, 1, 1), datetime(2027, 4, 30))
        self.assertEqual([e['start'] for e in eventos], ['2027-01-31', '2027-02-28', '2027-03-31', '2027-04-30'])
