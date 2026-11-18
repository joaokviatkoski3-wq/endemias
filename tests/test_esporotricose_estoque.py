import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose as esporotricose_core
from app_core import db as db_core


class EstoqueAutomaticoTests(unittest.TestCase):
    def test_necessidade_ativa_exclui_encerrados_e_separa_aguardando_e_incerto(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'necessidade.db')
            core = esporotricose_core
            core.salvar_estoque_medicacao(path, {'tipo':'Entrada','quantidade':680})
            ativos = []
            for nome, status, total in [('Ativo','Em tratamento',1210),('Falecido','Faleceu',90),
                                        ('Concluído','Acabou tratamento',80),('Curado','Curado',70),
                                        ('Eutanásia','Eutanásia',60),('Outro','Outro',50),
                                        ('Aguardando','Aguardando medicação',40)]:
                ident = core.salvar_doente(path, {'nome':nome,'tutor':'Tutor fictício','status':status})
                receita = core.salvar_receita_doente(path, ident, {'capsulas_total':total})
                if status in {'Curado', 'Eutanásia'}:
                    conn = db_core.connect(path)
                    try:
                        conn.execute('UPDATE esporotricose_doentes_animais SET status=? WHERE id_animal_doente=?', (status, ident))
                        conn.commit()
                    finally:
                        conn.close()
                if status == 'Em tratamento':
                    core.salvar_entrega_doente(path, receita, {'quantidade':30})
                    ativos.append(ident)
            sem_receita = core.salvar_doente(path, {'nome':'Sem receita','tutor':'Tutor fictício','status':'Em tratamento'})
            pendente = core.salvar_doente(path, {'nome':'Receita pendente','tutor':'Tutor fictício','status':'Em tratamento'})
            core.salvar_receita_doente(path, pendente, {'receita_pendente':True})
            totais = core.estoque_medicacao(path)['totais']
            self.assertEqual(totais['saldo_setor'],650)
            self.assertEqual(totais['faltantes_tratamento'],1180)
            self.assertEqual(totais['deficit_tratamento'],530)
            self.assertEqual(totais['tratamento_sem_quantificar'],2)
            self.assertEqual(totais['faltantes_aguardando'],40)
            self.assertEqual(totais['status_a_revisar'],1)
            linhas = core.listar_doentes(path)['registros']
            falecido = next(r for r in linhas if r['nome']=='Falecido')
            self.assertEqual(falecido['capsulas_restantes'],0)
            self.assertEqual(falecido['capsulas_restantes_historico'],90)
            self.assertFalse(falecido['receita_pendente'])
            detalhe = core.obter_doente(path,falecido['id_animal_doente'])
            self.assertFalse(detalhe['receitas'][0]['pendencia_ativa'])
            self.assertEqual(detalhe['receitas'][0]['capsulas_total'],90)
            csv = next(r for r in core.listar_doentes_csv(path) if r['animal']=='Falecido')
            self.assertEqual(csv['capsulas_restantes'],0)
            core.salvar_doente(path, {'id_animal_doente':ativos[0],'nome':'Ativo','tutor':'Tutor fictício','status':'Faleceu'})
            depois = core.estoque_medicacao(path)['totais']
            self.assertEqual(depois['faltantes_tratamento'],0)
            self.assertEqual(depois['saldo_setor'],650)  # entrega passada continua sendo saída física

    def test_excluir_uma_entrega_recalcula_estoque_sem_apagar_receita(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            animal = esporotricose_core.salvar_doente(db_path, {
                "nome": "Paciente", "tutor": "Tutor", "status": "Em tratamento",
            })
            receita = esporotricose_core.salvar_receita_doente(
                db_path, animal, {"capsulas_total": 60},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 100, "fonte_medicacao": "SESA"},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 50, "fonte_medicacao": "Município"},
            )
            apagar = esporotricose_core.salvar_entrega_doente(
                db_path, receita, {"quantidade": 20, "fonte_medicacao": "Município"},
            )
            manter = esporotricose_core.salvar_entrega_doente(
                db_path, receita, {"quantidade": 10, "fonte_medicacao": "SESA"},
            )
            antes = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(antes["totais"]["saldos_por_fonte"], {"SESA": 90, "Município": 30})
            self.assertEqual(antes["totais"]["saldo_setor"], 120)
            self.assertEqual(antes['totais']['entregues_por_fonte'], {'SESA':10, 'Município':20})
            self.assertEqual(antes['totais']['entregues_baixa_zoomed'], 0)
            self.assertEqual(antes['totais']['entregues_baixa_pendente'], 30)

            removida = esporotricose_core.excluir_entrega_doente(db_path, apagar)
            self.assertEqual(removida, {
                "id_animal_doente": animal,
                "quantidade_restaurada": 20,
                "fonte_medicacao": "Município",
            })
            depois = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(depois["totais"]["saldos_por_fonte"], {"SESA": 90, "Município": 50})
            self.assertEqual(depois["totais"]["saldo_setor"], 140)
            self.assertEqual(depois["totais"]["saidas_entregas"], 10)
            self.assertEqual([e["id_entrega"] for e in depois["movimentos_automaticos"]], [manter])
            cadastro = esporotricose_core.obter_doente(db_path, animal)
            self.assertEqual(cadastro["receitas"][0]["id_receita"], receita)
            self.assertEqual(cadastro["receitas"][0]["capsulas_entregues"], 10)
            self.assertEqual([e["id_entrega"] for e in cadastro["receitas"][0]["entregas"]], [manter])
            with self.assertRaisesRegex(esporotricose_core.ValidationError, "não encontrada"):
                esporotricose_core.excluir_entrega_doente(db_path, apagar)
            self.assertEqual(esporotricose_core.estoque_medicacao(db_path)["totais"]["saldo_setor"], 140)

    def test_excluir_sobra_reduz_saldo_sem_alterar_entregas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'sobras.db')
            core = esporotricose_core
            core.salvar_estoque_medicacao(path, {'tipo':'Entrada','quantidade':380})
            sobra = core.salvar_estoque_medicacao(path, {'tipo':'Sobra','quantidade':270})
            antes = core.estoque_medicacao(path)['totais']
            self.assertEqual(antes['saldo_setor'], 650)
            core.excluir_estoque_medicacao(path, sobra)
            depois = core.estoque_medicacao(path)['totais']
            self.assertEqual(depois['saldo_setor'], 380)
            self.assertEqual(depois['saidas_entregas'], antes['saidas_entregas'])

    def test_saldos_por_fonte_e_correcao_de_entrega_antiga(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            animal = esporotricose_core.salvar_doente(db_path, {
                "nome": "Paciente", "tutor": "Tutor", "status": "Em tratamento",
            })
            receita = esporotricose_core.salvar_receita_doente(
                db_path, animal, {"capsulas_total": 60},
            )
            antiga = esporotricose_core.salvar_entrega_doente(
                db_path, receita, {"quantidade": 20, "baixa_zoomed": "Sim", "observacoes": "Entrega conferida"},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 100},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 50, "fonte_medicacao": "Município"},
            )
            self.assertEqual(esporotricose_core.estoque_medicacao(db_path)["totais"]["saldos_por_fonte"],
                             {"SESA": 80, "Município": 50})
            esporotricose_core.atualizar_entrega_doente(db_path, antiga, {
                "quantidade": 20, "baixa_zoomed": "Sim", "fonte_medicacao": "Município",
            })
            estoque = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(estoque["totais"]["saldos_por_fonte"], {"SESA": 100, "Município": 30})
            self.assertEqual(estoque["totais"]["saldo_setor"], 130)
            self.assertEqual(estoque['totais']['entregues_por_fonte'], {'SESA':0, 'Município':20})
            self.assertEqual(estoque['totais']['entregues_baixa_zoomed'], 20)
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["totais"]["capsulas_baixa_zoomed"], 20)
            entrega = esporotricose_core.obter_doente(db_path, animal)["receitas"][0]["entregas"][0]
            self.assertEqual(entrega["baixa_zoomed"], "Sim")
            self.assertEqual(entrega["fonte_medicacao"], "Município")
            self.assertEqual(entrega["observacoes"], "Entrega conferida")
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["registros"][0]["entregas_zoomed_pendentes"], 0)

            pendente = esporotricose_core.salvar_entrega_doente(db_path, receita, {
                "quantidade": 5, "fonte_medicacao": "Município", "baixa_zoomed": "Não",
            })
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["registros"][0]["entregas_zoomed_pendentes"], 1)
            self.assertEqual(len(esporotricose_core.listar_doentes(db_path, {"baixa_zoomed": "Pendente"})["registros"]), 1)
            self.assertEqual(len(esporotricose_core.listar_doentes_csv(db_path, {"baixa_zoomed": "Pendente"})), 1)
            esporotricose_core.atualizar_entrega_doente(db_path, pendente, {
                "quantidade": 5, "fonte_medicacao": "Município", "baixa_zoomed": "Sim",
            })
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["totais"]["capsulas_baixa_zoomed"], 25)
            self.assertEqual(esporotricose_core.listar_doentes(db_path, {"baixa_zoomed": "Pendente"})["registros"], [])
            self.assertEqual(esporotricose_core.listar_doentes_csv(db_path, {"baixa_zoomed": "Pendente"}), [])

    def test_edicao_do_movimento_reclassifica_saldo_sem_alterar_total(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            movimento = esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 40},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"id_movimento": movimento, "tipo": "Entrada", "quantidade": 40,
                          "fonte_medicacao": "Município"},
            )
            self.assertEqual(esporotricose_core.estoque_medicacao(db_path)["totais"]["saldos_por_fonte"],
                             {"SESA": 0, "Município": 40})

    def test_nome_legado_zoomed_e_convertido_em_sesa(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            movimento = esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 10, "fonte_medicacao": "Zoomed"},
            )
            conn = db_core.connect(db_path)
            try:
                conn.execute("UPDATE esporotricose_estoque_medicacao SET fonte_medicacao='Zoomed' WHERE id_movimento=?", (movimento,))
                conn.commit()
            finally:
                conn.close()
            estoque = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(estoque["movimentos"][0]["fonte_medicacao"], "SESA")
            self.assertEqual(estoque["totais"]["entradas_sesa"], 10)

    def test_rejeita_fonte_desconhecida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            with self.assertRaises(esporotricose_core.ValidationError):
                esporotricose_core.salvar_estoque_medicacao(
                    db_path, {"tipo": "Entrada", "quantidade": 10, "fonte_medicacao": "Outra"},
                )

    def test_atualiza_apenas_observacao_da_saida_automatica(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "estoque.db"
            conn = db_core.connect(db_path)
            try:
                esporotricose_core.ensure_schema(conn)
            finally:
                conn.close()

            id_animal = esporotricose_core.salvar_doente(str(db_path), {
                "nome": "Paciente",
                "tutor": "Tutor de teste",
                "status": "Em tratamento",
            })
            id_receita = esporotricose_core.salvar_receita_doente(
                str(db_path), id_animal, {"capsulas_total": 30, "status": "Em tratamento"},
            )
            id_entrega = esporotricose_core.salvar_entrega_doente(
                str(db_path), id_receita, {"quantidade": 30, "observacoes": "Entrega inicial"},
            )

            esporotricose_core.salvar_observacao_movimento_automatico(
                str(db_path), id_entrega, "Paciente orientado sobre o retorno.",
            )
            estoque = esporotricose_core.estoque_medicacao(str(db_path))

        movimento = next(item for item in estoque["movimentos_automaticos"] if item["id_entrega"] == id_entrega)
        self.assertEqual(movimento["quantidade"], 30)
        self.assertEqual(movimento["observacoes"], "Paciente orientado sobre o retorno.")


if __name__ == "__main__":
    unittest.main()
