import tempfile
import unittest
from pathlib import Path
from app_core import esporotricose as core


class DispensaZooMedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target=str(Path(self.tmp.name)/'teste.db')
        self.animal=core.salvar_doente(self.target,{'nome':'Animal fictício','tutor':'Tutor fictício','status':'Em tratamento'})
        self.receita=core.salvar_receita_doente(self.target,self.animal,{'capsulas_total':180})
        core.salvar_estoque_medicacao(self.target,{'tipo':'Entrada','quantidade':200,'fonte_medicacao':'Município'})

    def entrega(self,fonte,dia,baixa='Não'):
        return core.salvar_entrega_doente(self.target,self.receita,{'quantidade':30,'fonte_medicacao':fonte,'data_entrega':dia,'baixa_zoomed':baixa})

    def test_marco_preserva_legado_e_exige_sesa_mas_dispensa_municipio(self):
        self.entrega('Município','2026-11-07')
        self.entrega('Município','2026-11-08')
        self.entrega('SESA','2026-11-08')
        self.entrega('Município','2026-11-12','Sim')
        entregas=core.obter_doente(self.target,self.animal)['receitas'][0]['entregas']
        self.assertCountEqual([e['baixa_zoomed'] for e in entregas],['Não','Não se aplica','Não','Sim'])
        t=core.estoque_medicacao(self.target)['totais']
        self.assertEqual((t['entregues'],t['saldo_setor'],t['faltantes_tratamento']),(120,80,60))
        self.assertEqual((t['entregues_baixa_zoomed'],t['entregues_baixa_pendente'],t['entregues_baixa_dispensada']),(30,60,30))
        self.assertEqual(t['entregues_baixa_zoomed_por_fonte'],{'SESA':0,'Município':30})
        self.assertEqual(t['entregues_baixa_dispensada_por_fonte'],{'SESA':0,'Município':30})
        self.assertEqual(t['entregues_baixa_pendente_por_fonte'],{'SESA':30,'Município':30})

    def test_dispensada_nao_vira_pendencia_em_tela_csv_filtro_e_edicao(self):
        ident=self.entrega('Município','2026-11-08')
        row=core.listar_doentes(self.target)['registros'][0]
        self.assertEqual(row['entregas_zoomed_pendentes'],0)
        self.assertEqual(row['baixa_zoomed'],'Não se aplica')
        self.assertEqual(core.listar_doentes(self.target,{'baixa_zoomed':'Pendente'})['registros'],[])
        self.assertEqual(core.listar_doentes_csv(self.target,{'baixa_zoomed':'Pendente'}),[])
        self.assertEqual(core.listar_doentes_csv(self.target)[0]['baixa_zoomed'],'Não se aplica')
        self.assertEqual(len(core.listar_doentes(self.target,{'baixa_zoomed':'Não se aplica'})['registros']),1)
        self.assertEqual(len(core.listar_doentes_csv(self.target,{'baixa_zoomed':'Não se aplica'})),1)
        self.assertEqual(core.listar_doentes(self.target,{'baixa_zoomed':'Sim'})['registros'],[])
        core.atualizar_entrega_doente(self.target,ident,{'quantidade':30,'fonte_medicacao':'Município','data_entrega':'2026-11-12','baixa_zoomed':'Não se aplica'})
        self.assertEqual(core.obter_doente(self.target,self.animal)['receitas'][0]['entregas'][0]['baixa_zoomed'],'Não se aplica')
        self.assertEqual(core.controle_entregas_medicacao(self.target,{'baixa_zoomed':'Não se aplica'})['total'],1)

    def test_impede_dispensar_sesa_ou_municipal_anterior_e_nao_inventa_baixa_sem_entrega(self):
        for fonte,dia in [('SESA','2026-11-12'),('Município','2026-11-07')]:
            with self.assertRaises(core.ValidationError):self.entrega(fonte,dia,'Não se aplica')
        self.assertEqual(core.listar_doentes(self.target)['registros'][0]['baixa_zoomed'],'Sem entregas')
        self.assertEqual(core.listar_doentes_csv(self.target)[0]['baixa_zoomed'],'Sem entregas')
        self.assertEqual(core.listar_doentes(self.target,{'baixa_zoomed':'Pendente'})['registros'],[])

    def test_edicao_parcial_preserva_baixa_ja_registrada_fonte_e_data(self):
        ident=self.entrega('Município','2026-11-12','Sim')
        core.atualizar_entrega_doente(self.target,ident,{'quantidade':35})
        row=core.obter_doente(self.target,self.animal)['receitas'][0]['entregas'][0]
        self.assertEqual((row['quantidade'],row['fonte_medicacao'],row['data_entrega'],row['baixa_zoomed']),
                         (35,'Município','2026-11-12','Sim'))

    def test_edicao_de_legado_sem_data_nao_aplica_data_atual(self):
        from app_core import db
        ident=self.entrega('Município','2026-11-07')
        conn=db.connect(self.target)
        conn.execute("UPDATE esporotricose_doentes_entregas SET data_entrega=NULL,criado_em='2026-06-01T10:00:00' WHERE id_entrega=?",(ident,))
        conn.commit();conn.close()
        core.atualizar_entrega_doente(self.target,ident,{'quantidade':30})
        row=core.obter_doente(self.target,self.animal)['receitas'][0]['entregas'][0]
        self.assertEqual(row['baixa_zoomed'],'Não')
        self.assertIsNone(row['data_entrega'])
