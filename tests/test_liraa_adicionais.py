"""Adicionais autorizados integram o campo sem reescrever o sorteio original."""

import json
import unittest
from unittest.mock import patch

from app_core import db, liraa, liraa_modelo as modelo, liraa_operacional as op
from app_core import liraa_kobo as kobo, liraa_laboratorio as lab, liraa_boletim as boletim
from tests import test_liraa_operacao as fixtures


class AdicionaisTests(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.OperacaoTests()
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.target, self.cid, self.base = self.env.target, self.env.ciclo, self.env.base
        plano = op.plano(self.target, self.cid, self.base)
        sorteados = {(q['id_localidade'], q['quarteirao']) for q in plano['quarteiroes']}
        candidatos = [q for q in liraa.inventario(self.target, self.base)['quarteiroes']
                      if (q['id_localidade'], q['quarteirao']) not in sorteados]
        self.extras = candidatos[:2]
        self.outro = candidatos[2]
        self.config = {'ciclo': self.cid, 'plano_hash': plano['plano_hash'],
                       'quarteiroes': [{'localidade': q['localidade'], 'quarteirao': q['quarteirao']} for q in self.extras]}
        self.mock = patch.object(modelo, 'adicionais', return_value=self.config)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def envio(self, uuid, q, num):
        r = self.env.registro(uuid, Houve_coleta='sim', endemias_ciclo=str(self.cid), endemias_plano=self.config['plano_hash'])
        r['Dados_visita'].update(Localidade=q['localidade'], Quarteir_o=q['quarteirao'], Imovel='residencia', Numero=num)
        r['group_jr1vc40'][0]['N_mero_do_tubito'] = 100 + num
        return r

    def snapshot(self):
        conn = db.connect(self.target)
        try:
            return json.dumps({t: [dict(r) for r in conn.execute('SELECT * FROM ' + t)] for t in
                ('liraa_ciclos', 'liraa_estratos', 'liraa_estrato_quarteiroes', 'liraa_sorteios', 'liraa_sorteios_historico')}, sort_keys=True)
        finally:
            conn.close()

    def test_plano_inclui_adicionais_preservando_todas_tabelas_do_sorteio(self):
        antes = self.snapshot()
        p = op.plano(self.target, self.cid, self.base)
        self.assertEqual((p['total_sorteados'], p['total_adicionais'], len(p['quarteiroes'])), (len(self.env.draw['selecionados']), 2, len(self.env.draw['selecionados']) + 2))
        self.assertEqual(p['plano_hash'], self.config['plano_hash'])
        self.assertEqual(p['ciclo']['estratos'][0]['sorteio']['n'], self.env.draw['n'])
        self.assertEqual(self.snapshot(), antes)
        self.assertEqual(sum(g['adicionais'] for g in p['grupos']), 2)

    def test_vincula_somente_adicionais_autorizados_respeitando_ciclo_e_periodo(self):
        r = self.envio('extra', self.extras[0], 1)
        self.assertEqual(kobo.previa(self.target, self.cid, [r])[0]['situacao_vinculo'], 'adicional')
        r['Dados_visita']['Quarteir_o'] = 'outros'
        r['Dados_visita']['Quarteir_o_outros'] = self.extras[0]['quarteirao']
        self.assertEqual(kobo.previa(self.target, self.cid, [r])[0]['situacao_vinculo'], 'adicional')
        r = self.envio('fora', self.outro, 1)
        self.assertEqual(kobo.previa(self.target, self.cid, [r])[0]['situacao_vinculo'], 'fora_do_sorteio')
        r = self.envio('antigo', self.extras[0], 1)
        r['endemias_plano'] = 'outro-plano'
        self.assertEqual(kobo.previa(self.target, self.cid, [r])[0]['situacao_vinculo'], 'plano_formulario_desatualizado')
        r['endemias_plano'] = self.config['plano_hash']
        r['Data'] = '2026-09-01'
        self.assertEqual(kobo.previa(self.target, self.cid, [r])[0]['situacao_vinculo'], 'fora_do_periodo')

    def test_importacao_laboratorio_correcao_e_boletim_incluem_e_identificam_adicionais(self):
        antes = self.snapshot()
        q = self.env.draw['selecionados'][0]
        records = [self.envio('sorteado', q, 1)] + [self.envio('extra' + str(i), q, i + 2) for i, q in enumerate(self.extras)]
        self.assertEqual(kobo.importar(self.target, self.cid, records), 3)
        self.assertEqual(kobo.importar(self.target, self.cid, records), 0)
        tubes = lab.listar(self.target, self.cid)
        self.assertEqual(sum(t['situacao_vinculo'] == 'adicional' for t in tubes), 2)
        for t in tubes:
            lab.salvar(self.target, t['id_tubito'], self.env.payload(aegypt_larvas='1', albopictus_pupas='1'), self.env.user)
        g = boletim.resumir(self.target, self.cid, self.base)['grupos'][0]
        self.assertEqual((g['trabalhados'], g['trabalhados_adicionais'], g['aegypt_outros'], g['positivos_adicionais_aegypt']), (3, 2, 3, 2))
        self.assertEqual((g['tubitos_adicionais'], g['positivos_adicionais_albopictus']), (2, 2))
        self.assertFalse(g['parcial'])
        v = next(v for v in kobo.listar(self.target, self.cid) if v['situacao_vinculo'] == 'adicional')
        kobo.corrigir(self.target, v['id_visita'], {'versao': v['versao_dados'], 'motivo': 'Conferido', 'tipo_imovel': 'comercio'})
        corrigida = next(row for row in kobo.listar(self.target) if row['id_visita'] == v['id_visita'])
        self.assertEqual((corrigida['situacao_vinculo'], corrigida['tipo_imovel']), ('adicional', 'comercio'))
        self.assertEqual(boletim.resumir(self.target, self.cid, self.base)['excluidas'], 0)
        self.assertEqual(self.snapshot(), antes)

    def test_mapa_kml_e_filtros_identificam_adicionais(self):
        geo = op.geojson(self.target, self.cid, self.base)
        self.assertEqual(sum(f['properties']['adicional'] for f in geo['features']), 2)
        self.assertTrue(all(f['properties']['origem'] == 'Adicional de campo' for f in geo['features'] if f['properties']['adicional']))
        self.assertIn(b'(Adicional)', op.kml(self.target, self.cid, self.base))
        loc = self.extras[0]['id_localidade']
        p = op.plano(self.target, self.cid, self.base, id_localidade=loc)
        self.assertTrue(all(q['id_localidade'] == loc for q in p['quarteiroes']))
        self.assertEqual(p['total_adicionais'], sum(q['id_localidade'] == loc for q in self.extras))

    def test_recusa_duplicata_adicional_fora_de_estrato_e_assinatura_errada(self):
        original = self.config['quarteiroes']
        self.config['quarteiroes'] = original + original[:1]
        with self.assertRaisesRegex(liraa.LiraaError, 'repetido'):
            op.plano(self.target, self.cid, self.base)
        self.config['quarteiroes'] = [{'localidade': 'Sede', 'quarteirao': '9999'}]
        with self.assertRaisesRegex(liraa.LiraaError, 'sem estrato'):
            op.plano(self.target, self.cid, self.base)
        self.config['quarteiroes'] = original
        self.config['plano_hash'] = 'divergente'
        with self.assertRaisesRegex(liraa.LiraaError, 'outro plano'):
            op.plano(self.target, self.cid, self.base)

    def test_adicionais_nao_sao_aplicados_em_outro_ciclo(self):
        cid = liraa.criar_ciclo(self.target, {'ano': 2026, 'nome': 'Outro ciclo'})
        p = op.plano(self.target, cid, self.base)
        self.assertEqual((len(p['quarteiroes']), p['total_adicionais']), (0, 0))
