import sqlite3
import unittest
from scripts import corrigir_entregas_confirmadas_20261118 as core


class ConfirmacoesEntregasTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
          CREATE TABLE esporotricose_doentes_animais(id_animal_doente INTEGER PRIMARY KEY,atualizado_em TEXT);
          CREATE TABLE esporotricose_doentes_receitas(id_receita INTEGER PRIMARY KEY,id_animal_doente INTEGER);
          CREATE TABLE esporotricose_doentes_entregas(id_entrega INTEGER PRIMARY KEY,id_receita INTEGER,
            data_entrega TEXT,quantidade INTEGER,fonte_medicacao TEXT,baixa_zoomed TEXT,observacoes TEXT,criado_em TEXT);
          CREATE TABLE esporotricose_doentes_anexos(id_anexo INTEGER,caminho_rel TEXT);
          CREATE TABLE esporotricose_estoque_medicacao(id_movimento INTEGER,quantidade INTEGER);
          CREATE TABLE auditoria_eventos(acao TEXT,entidade TEXT,entidade_id TEXT,usuario_nome TEXT,
            detalhes_json TEXT,criado_em TEXT,setor TEXT);
          INSERT INTO esporotricose_doentes_anexos VALUES(1,'preservar.pdf');
          INSERT INTO esporotricose_estoque_medicacao VALUES(1,200);
        ''')
        for ident,(rx,aid,dia,qty,fonte,baixa) in core.ESPERADOS.items():
            self.conn.execute('INSERT INTO esporotricose_doentes_animais VALUES(?,?)',(aid,'anterior'))
            self.conn.execute('INSERT INTO esporotricose_doentes_receitas VALUES(?,?)',(rx,aid))
            self.conn.execute('INSERT INTO esporotricose_doentes_entregas VALUES(?,?,?,?,?,?,?,?)',
                              (ident,rx,dia,qty,fonte,baixa,'preservar','anterior'))
        self.conn.execute("INSERT INTO esporotricose_doentes_animais VALUES(56,'anterior')")
        self.conn.execute('INSERT INTO esporotricose_doentes_receitas VALUES(75,56)')
        self.conn.commit()

    def test_corrige_so_confirmados_com_auditoria_e_preserva_outros_dados(self):
        result=core.aplicar(self.conn)
        self.assertEqual(result['depois'],{'registros':6,'capsulas':180,'fontes':{'SESA':60,'Município':120}})
        rows=core.snapshot(self.conn)
        self.assertFalse({45,91}&{e['id_entrega'] for e in rows['entregas']})
        self.assertEqual(sum(e['quantidade'] for e in rows['entregas'] if e['baixa_zoomed']=='Não se aplica'),60)
        self.assertEqual(len(rows['receitas']),8)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],8)
        with self.assertRaises(ValueError):core.aplicar(self.conn)

    def test_bloqueia_estado_divergente_antes_de_excluir(self):
        self.conn.execute('UPDATE esporotricose_doentes_entregas SET quantidade=40 WHERE id_entrega=88');self.conn.commit()
        before=core.snapshot(self.conn)
        with self.assertRaises(ValueError):core.aplicar(self.conn)
        self.assertEqual(before,core.snapshot(self.conn))

    def test_aplica_acordo_a_novo_lancamento_municipal_sem_apagar_baixa_realizada(self):
        self.conn.executemany('INSERT INTO esporotricose_doentes_entregas VALUES(?,?,?,?,?,?,?,?)',[
            (100,79,'2026-11-18',30,'Município','Não','preservar','anterior'),
            (101,79,'2026-11-18',30,'Município','Sim','preservar','anterior')])
        self.conn.commit();core.aplicar(self.conn)
        rows={r['id_entrega']:r for r in core.snapshot(self.conn)['entregas']}
        self.assertEqual(rows[100]['baixa_zoomed'],'Não se aplica')
        self.assertEqual(rows[101]['baixa_zoomed'],'Sim')

    def test_erro_no_fim_desfaz_exclusoes_inclusao_e_auditoria(self):
        self.conn.executescript('''CREATE TRIGGER alterar_receita AFTER DELETE ON esporotricose_doentes_entregas
            BEGIN UPDATE esporotricose_doentes_receitas SET id_animal_doente=999 WHERE id_receita=37; END;''')
        before=core.snapshot(self.conn)
        with self.assertRaises(ValueError):core.aplicar(self.conn)
        self.assertEqual(before,core.snapshot(self.conn))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],0)
