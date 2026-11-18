import copy
import sqlite3
import unittest

from scripts import reconciliar_entregas_zoomed as core


class ConciliacaoZoomedTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''
            CREATE TABLE esporotricose_doentes_animais(id_animal_doente INTEGER PRIMARY KEY, atualizado_em TEXT);
            CREATE TABLE esporotricose_doentes_receitas(id_receita INTEGER PRIMARY KEY,id_animal_doente INTEGER);
            CREATE TABLE esporotricose_doentes_entregas(id_entrega INTEGER PRIMARY KEY,id_receita INTEGER,
                quantidade INTEGER,data_entrega TEXT,fonte_medicacao TEXT,baixa_zoomed TEXT,observacoes TEXT,criado_em TEXT);
            CREATE TABLE esporotricose_doentes_anexos(id_anexo INTEGER PRIMARY KEY,caminho_rel TEXT);
            CREATE TABLE esporotricose_estoque_medicacao(id_movimento INTEGER PRIMARY KEY,quantidade INTEGER);
            CREATE TABLE auditoria_eventos(acao TEXT,entidade TEXT,entidade_id TEXT,usuario_nome TEXT,
                detalhes_json TEXT,criado_em TEXT,setor TEXT);
            INSERT INTO esporotricose_doentes_animais VALUES(1,'anterior');
            INSERT INTO esporotricose_doentes_receitas VALUES(1,1);
            INSERT INTO esporotricose_doentes_entregas VALUES(1,1,30,'2026-06-23','SESA','Não','preservar','anterior');
            INSERT INTO esporotricose_doentes_anexos VALUES(1,'comprovante.pdf');
            INSERT INTO esporotricose_estoque_medicacao VALUES(1,100);
        ''')
        old = dict(quantidade=30, data_entrega='2026-06-23', fonte_medicacao='SESA', baixa_zoomed='Não')
        new = dict(quantidade=35, data_entrega='2026-06-26', fonte_medicacao='Município', baixa_zoomed='Sim')
        self.plan = {'lote':'teste', 'fonte_sha256':'ficticio',
                     'assinaturas_antes':core.signatures(core.snapshot(self.conn)),
                     'operacoes':[{'tipo':'atualizar','id_entrega':1,'id_receita':1,'id_animal_doente':1,
                                   'antes':old,'depois':new,'linhas_zoomed':[2],'motivo':'Conferência fictícia'}],
                     'totais_depois':{'registros':1,'capsulas':35,'fontes':{'Município':35}}}

    def tearDown(self):
        self.conn.close()

    def test_corrige_preservando_observacao_anexo_receita_estoque_e_audita(self):
        result = core.apply(self.conn,self.plan)
        self.assertEqual(result['depois']['capsulas'],35)
        row = dict(self.conn.execute('SELECT * FROM esporotricose_doentes_entregas').fetchone())
        self.assertEqual(row['observacoes'],'preservar')
        self.assertEqual(row['criado_em'],'anterior')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],1)

    def test_desfaz_lote_inteiro_quando_total_final_diverge(self):
        before = core.snapshot(self.conn)
        self.plan['totais_depois']['capsulas'] = 999
        with self.assertRaises(ValueError): core.apply(self.conn,self.plan)
        self.assertEqual(core.snapshot(self.conn),before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],0)

    def test_bloqueia_estado_alterado_e_reaplicacao(self):
        core.apply(self.conn,self.plan)
        with self.assertRaisesRegex(ValueError,'mudaram'): core.apply(self.conn,self.plan)

    def test_bloqueia_vinculo_errado_e_exclusao(self):
        self.plan['operacoes'][0]['id_animal_doente']=2
        with self.assertRaisesRegex(ValueError,'Vínculo'):core.apply(self.conn,self.plan)
        self.plan['operacoes'][0]['tipo']='excluir'
        with self.assertRaisesRegex(ValueError,'não permitida'):core.apply(self.conn,self.plan)

    def test_inclui_entrega_com_auditoria_e_impede_duplicar(self):
        op=copy.deepcopy(self.plan['operacoes'][0])
        op.update(tipo='inserir',depois=dict(quantidade=30,data_entrega='2026-09-24',fonte_medicacao='SESA',baixa_zoomed='Sim'))
        op.pop('id_entrega');op.pop('antes')
        self.plan['operacoes']=[op]
        self.plan['totais_depois']={'registros':2,'capsulas':60,'fontes':{'SESA':60}}
        core.apply(self.conn,self.plan)
        self.plan['assinaturas_antes']=core.signatures(core.snapshot(self.conn))
        with self.assertRaisesRegex(ValueError,'já existe'):core.apply(self.conn,self.plan)


if __name__ == '__main__':
    unittest.main()
