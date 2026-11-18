import sqlite3
import unittest
from scripts import corrigir_entrega_99_20261118 as core


class CorrecaoEntrega99Tests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE esporotricose_doentes_animais(id_animal_doente INTEGER PRIMARY KEY,atualizado_em TEXT);
            CREATE TABLE esporotricose_doentes_receitas(id_receita INTEGER PRIMARY KEY,id_animal_doente INTEGER);
            CREATE TABLE esporotricose_doentes_entregas(id_entrega INTEGER PRIMARY KEY,id_receita INTEGER,
                data_entrega TEXT,quantidade INTEGER,fonte_medicacao TEXT,baixa_zoomed TEXT,observacoes TEXT);
            CREATE TABLE esporotricose_doentes_anexos(id_anexo INTEGER,caminho_rel TEXT);
            CREATE TABLE esporotricose_estoque_medicacao(id_movimento INTEGER,quantidade INTEGER);
            CREATE TABLE auditoria_eventos(acao TEXT,entidade TEXT,entidade_id TEXT,usuario_nome TEXT,
                detalhes_json TEXT,criado_em TEXT,setor TEXT);
            INSERT INTO esporotricose_doentes_animais VALUES(54,'anterior');
            INSERT INTO esporotricose_doentes_receitas VALUES(73,54);
            INSERT INTO esporotricose_doentes_entregas VALUES(99,73,'2026-11-18',29,'Município','Não se aplica','preservar');
            INSERT INTO esporotricose_doentes_entregas VALUES(100,73,'2026-11-18',30,'Município','Não se aplica','outra');
            INSERT INTO esporotricose_doentes_anexos VALUES(1,'preservar.pdf');
            INSERT INTO esporotricose_estoque_medicacao VALUES(1,200);
        ''')

    def test_corrige_uma_capsula_audita_e_nao_reaplica(self):
        result=core.aplicar(self.conn)
        self.assertEqual(result['status'],'aplicado')
        self.assertEqual(self.conn.execute('SELECT quantidade FROM esporotricose_doentes_entregas WHERE id_entrega=99').fetchone()[0],30)
        self.assertEqual(self.conn.execute('SELECT observacoes FROM esporotricose_doentes_entregas WHERE id_entrega=99').fetchone()[0],'preservar')
        self.assertEqual(core.aplicar(self.conn)['status'],'ja_corrigido')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],1)

    def test_bloqueia_outra_fonte_antes_de_gravar(self):
        self.conn.execute("UPDATE esporotricose_doentes_entregas SET fonte_medicacao='SESA' WHERE id_entrega=99");self.conn.commit()
        before=core.snapshot(self.conn)
        with self.assertRaises(ValueError):core.aplicar(self.conn)
        self.assertEqual(core.snapshot(self.conn),before)

    def test_desfaz_lote_e_auditoria_em_efeito_fora_do_escopo(self):
        self.conn.executescript('''CREATE TRIGGER alterar_receita AFTER UPDATE ON esporotricose_doentes_entregas
          BEGIN UPDATE esporotricose_doentes_receitas SET id_animal_doente=999 WHERE id_receita=73; END;''')
        before=core.snapshot(self.conn)
        with self.assertRaises(ValueError):core.aplicar(self.conn)
        self.assertEqual(core.snapshot(self.conn),before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM auditoria_eventos').fetchone()[0],0)
