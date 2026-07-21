import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import ovitrampas as ovitrampas_core
from app_core import ovitrampas_laboratorio as laboratorio_core


class OvitrampasLaboratorioTests(unittest.TestCase):
    def _banco(self, path):
        conn = db_core.connect(path)
        conn.executescript("""
            CREATE TABLE usuarios (
                id_usuario INTEGER PRIMARY KEY,
                nome TEXT,
                nivel TEXT,
                ativo INTEGER DEFAULT 1
            );
            CREATE TABLE agentes (
                id_agente INTEGER PRIMARY KEY,
                nome TEXT,
                ativo INTEGER DEFAULT 1
            );
            INSERT INTO usuarios(id_usuario,nome,nivel) VALUES (1,'Azimir','visualizador');
            INSERT INTO usuarios(id_usuario,nome,nivel) VALUES (2,'João','admin');
        """)
        ovitrampas_core.ensure_schema(conn)
        agora = "2026-07-21T08:00:00"
        grupo = conn.execute(
            """INSERT INTO ovitrampas_calendario_grupos
               (nome,localidades,cor,ativo,criado_em,atualizado_em)
               VALUES ('Cachoeira / Roma','Cachoeira, Roma','#123456',1,?,?)""",
            (agora, agora),
        ).lastrowid
        diario = conn.execute(
            """INSERT INTO ovitrampas_diarios(nome,ativo,criado_em,atualizado_em)
               VALUES ('Roma 1',1,?,?)""",
            (agora, agora),
        ).lastrowid
        for ordem, ovitrampa_id, complemento in (
            (1, "116", "Aviário Monte Santo"),
            (2, "117", "REALOCAR"),
        ):
            conn.execute(
                """INSERT INTO ovitrampas_armadilhas
                   (ovitrampa_id,complemento,localidade,ativo,atualizado_em)
                   VALUES (?,?,'Roma',1,?)""",
                (ovitrampa_id, complemento, agora),
            )
            conn.execute(
                """INSERT INTO ovitrampas_diario_armadilhas
                   (id_diario,ovitrampa_id,ordem,criado_em,atualizado_em)
                   VALUES (?,?,?,?,?)""",
                (diario, ovitrampa_id, ordem, agora, agora),
            )
        conn.execute(
            """INSERT INTO ovitrampas_calendario_eventos
               (data,movimento,id_grupo,ciclo,criado_em,atualizado_em)
               VALUES ('2026-07-22','instalacao',?,'9',?,?)""",
            (grupo, agora, agora),
        )
        conn.execute(
            """INSERT INTO ovitrampas_calendario_eventos
               (data,movimento,id_grupo,ciclo,criado_em,atualizado_em)
               VALUES ('2026-07-24','troca',?,'9',?,?)""",
            (grupo, agora, agora),
        )
        conn.commit()
        conn.close()

    def test_fluxo_da_leitura_ate_envio_ao_conta_ovos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-laboratorio.db")
            self._banco(db_path)

            criados = laboratorio_core.gerar_lotes_pendentes(db_path, hoje="2026-07-24")
            pendentes = laboratorio_core.listar_para_laboratorista(
                db_path, hoje="2026-07-24",
            )
            self.assertEqual(criados, 1)
            self.assertEqual(pendentes["total"], 1)
            self.assertEqual(pendentes["registros"][0]["diario_nome"], "Roma 1")

            id_lote = pendentes["registros"][0]["id_lote"]
            lote = laboratorio_core.obter_lote(db_path, id_lote)
            self.assertEqual(len(lote["itens"]), 1)
            self.assertEqual(lote["itens"][0]["ovitrampa_id"], "116")
            self.assertEqual(lote["itens"][0]["complemento"], "Aviário Monte Santo")

            leitura = [{"id_item": lote["itens"][0]["id_item"], "ovos": 12}]
            usuario_lab = {"id_usuario": 1, "nome": "Azimir"}
            laboratorio_core.salvar_rascunho(db_path, id_lote, leitura, usuario_lab)
            concluido = laboratorio_core.concluir_lote(db_path, id_lote, leitura, usuario_lab)
            self.assertEqual(concluido["status"], "concluido")
            self.assertEqual(concluido["ovos"], 12)

            correcao = [{"id_item": lote["itens"][0]["id_item"], "ovos": 13}]
            corrigido = laboratorio_core.salvar_rascunho(db_path, id_lote, correcao, usuario_lab)
            self.assertEqual(corrigido["ovos"], 13)
            self.assertEqual(
                laboratorio_core.listar_para_administracao(db_path, hoje="2026-07-24")["total"],
                1,
            )

            enviado = laboratorio_core.marcar_enviado_conta_ovos(
                db_path, id_lote, {"id_usuario": 2, "nome": "João"},
            )
            self.assertEqual(enviado["status"], "enviado_conta_ovos")
            with self.assertRaisesRegex(ValueError, "não pode mais ser alterado"):
                laboratorio_core.salvar_rascunho(db_path, id_lote, correcao, usuario_lab)
            self.assertEqual(
                laboratorio_core.listar_para_administracao(
                    db_path, status="enviado", hoje="2026-07-24",
                )["total"],
                1,
            )

    def test_mostra_trocas_futuras_da_semana_sem_criar_pendencia(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-proximas.db")
            self._banco(db_path)

            dados = laboratorio_core.listar_para_laboratorista(
                db_path, hoje="2026-07-21",
            )

        self.assertEqual(dados["total"], 0)
        self.assertEqual(len(dados["proximas"]), 1)
        self.assertEqual(dados["proximas"][0]["diario_nome"], "Roma 1")
        self.assertEqual(dados["proximas"][0]["movimento_label"], "Troca")
        self.assertEqual(dados["proximas"][0]["data_movimento"], "2026-07-24")
        self.assertEqual(dados["proximas"][0]["armadilhas"], 1)

    def test_eventos_anteriores_a_ativacao_nao_geram_lotes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-antigas.db")
            self._banco(db_path)
            conn = db_core.connect(db_path)
            grupo = conn.execute(
                "SELECT id_grupo FROM ovitrampas_calendario_grupos WHERE nome='Cachoeira / Roma'"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO ovitrampas_calendario_eventos
                   (data,movimento,id_grupo,ciclo,criado_em,atualizado_em)
                   VALUES ('2026-07-20','retirada',?,'8','2026-07-20','2026-07-20')""",
                (grupo,),
            )
            conn.commit()
            conn.close()

            laboratorio_core.gerar_lotes_pendentes(db_path, hoje="2026-07-21")
            self.assertEqual(
                laboratorio_core.listar_para_laboratorista(
                    db_path, hoje="2026-07-21",
                )["total"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
