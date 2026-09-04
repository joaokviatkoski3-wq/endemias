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
            self.assertIsNone(lote["itens"][0]["ocorrencia"])

            leitura = [{
                "id_item": lote["itens"][0]["id_item"],
                "ovos": 12,
                "ocorrencia": 6,
            }]
            usuario_lab = {"id_usuario": 1, "nome": "Azimir"}
            laboratorio_core.salvar_rascunho(db_path, id_lote, leitura, usuario_lab)
            concluido = laboratorio_core.concluir_lote(db_path, id_lote, leitura, usuario_lab)
            self.assertEqual(concluido["status"], "concluido")
            self.assertEqual(concluido["ovos"], 12)
            self.assertEqual(concluido["itens"][0]["ocorrencia"], 6)
            self.assertEqual(concluido["itens"][0]["ocorrencia_label"], "Casa Fechada")

            correcao = [{
                "id_item": lote["itens"][0]["id_item"],
                "ovos": 13,
                "ocorrencia": None,
            }]
            corrigido = laboratorio_core.salvar_rascunho(db_path, id_lote, correcao, usuario_lab)
            self.assertEqual(corrigido["ovos"], 13)
            self.assertIsNone(corrigido["itens"][0]["ocorrencia"])
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

    def test_nao_expoe_programacao_futura_como_pendencia(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-proximas.db")
            self._banco(db_path)

            dados = laboratorio_core.listar_para_laboratorista(
                db_path, hoje="2026-07-21",
            )

        self.assertEqual(dados["total"], 0)
        self.assertEqual(dados["registros"], [])
        self.assertNotIn("proximas", dados)

    def test_rejeita_ocorrencia_fora_do_catalogo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-ocorrencia-invalida.db")
            self._banco(db_path)
            laboratorio_core.gerar_lotes_pendentes(db_path, hoje="2026-07-24")
            lote = laboratorio_core.listar_para_laboratorista(
                db_path, hoje="2026-07-24",
            )["registros"][0]
            item = laboratorio_core.obter_lote(db_path, lote["id_lote"])["itens"][0]

            with self.assertRaisesRegex(ValueError, "entre 1 e 8"):
                laboratorio_core.salvar_rascunho(
                    db_path,
                    lote["id_lote"],
                    [{"id_item": item["id_item"], "ovos": 0, "ocorrencia": 9}],
                    {"id_usuario": 1, "nome": "Azimir"},
                )

    def test_migra_itens_existentes_com_ocorrencia_nula(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ovitrampas-schema-anterior.db")
            self._banco(db_path)
            conn = db_core.connect(db_path)
            conn.executescript("""
                CREATE TABLE ovitrampas_laboratorio_itens (
                    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_lote INTEGER NOT NULL,
                    ovitrampa_id TEXT NOT NULL,
                    complemento TEXT,
                    localidade TEXT,
                    ovos INTEGER NOT NULL DEFAULT 0,
                    atualizado_em TEXT,
                    UNIQUE(id_lote, ovitrampa_id)
                );
                INSERT INTO ovitrampas_laboratorio_itens
                    (id_lote, ovitrampa_id, complemento, localidade, ovos)
                VALUES (999, '116', 'Aviário Monte Santo', 'Roma', 4);
            """)
            conn.commit()
            conn.close()

            laboratorio_core.ensure_schema(db_path)

            conn = db_core.connect(db_path)
            try:
                colunas = {
                    row[1] for row in conn.execute(
                        "PRAGMA table_info(ovitrampas_laboratorio_itens)"
                    ).fetchall()
                }
                item = conn.execute(
                    "SELECT ovos, ocorrencia FROM ovitrampas_laboratorio_itens"
                ).fetchone()
            finally:
                conn.close()
            self.assertIn("ocorrencia", colunas)
            self.assertEqual(item["ovos"], 4)
            self.assertIsNone(item["ocorrencia"])

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

    def test_contagens_api_para_aba_lê_espelho_e_rotula_fonte(self):
        import tempfile
        base = Path(tempfile.mkdtemp())  # sem remocao automatica (evita lock do WAL no Windows)
        db_path = base / "api.db"
        conn = db_core.connect(db_path)
        ovitrampas_core.ensure_schema(conn)
        conn.execute(
            """INSERT INTO ovitrampas_armadilhas
               (ovitrampa_id, localidade, complemento, latitude, longitude, atualizado_em)
               VALUES ('97','Roma','Local A',-25.1,-49.2,'2026-08-24T10:00:00')"""
        )
        conn.execute(
            """INSERT INTO ovitrampas_ocorrencias_conta_ovos
               (id_contagem, ovitrampa_id, ano, semana, data, ovos,
                resultado, ocorrencia_codigo, latitude, longitude, arquivo_origem, importado_em)
               VALUES ('900','97',2026,33,'2026-08-24',0,'Negativa',5,-25.1,-49.2,
                       'API privada Conta Ovos','2026-09-02T10:00:00')"""
        )
        conn.commit()
        conn.close()

        dados = ovitrampas_core.contagens_api_para_aba(db_path, limite=20)
        self.assertEqual("API Conta Ovos", dados["fonte"])
        self.assertEqual(1, dados["total"])
        reg = dados["registros"][0]
        self.assertEqual("97", reg["ovitrampa_id"])
        self.assertEqual("Roma", reg["localidade"])  # join com cadastro local
        self.assertEqual(0, reg["ovos"])
        self.assertEqual("2026-08-24", reg["data"])

    def test_monitoramento_contagens_lê_espelho_api_com_periodo(self):
        import tempfile
        base = Path(tempfile.mkdtemp())
        db_path = base / "mon.db"
        conn = db_core.connect(db_path)
        ovitrampas_core.ensure_schema(conn)
        conn.execute(
            """INSERT INTO ovitrampas_armadilhas
               (ovitrampa_id, localidade, complemento, latitude, longitude, atualizado_em)
               VALUES ('97','Roma','A',-25.1,-49.2,'2026-08-24T10:00:00'),
                      ('98','Roma','B',-25.2,-49.3,'2026-08-24T10:00:00')"""
        )
        rows = [
            ("900", "97", 2026, 33, 0),
            ("901", "97", 2026, 34, 5),
            ("902", "98", 2026, 33, 0),
            ("903", "99", 2025, 40, 0),  # fora do ano/período
        ]
        for idc, ovi, ano, sem, ovos in rows:
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem, ovitrampa_id, ano, semana, data, ovos,
                    resultado, latitude, longitude, arquivo_origem, importado_em)
                   VALUES (?,?,?,?,?,?,'x',-25.1,-49.2,'API privada Conta Ovos','2026-09-02')""",
                (idc, ovi, ano, sem, f"2026-08-{10+sem}", ovos),
            )
        conn.commit()
        conn.close()

        # filtro ano 2026, semanas 1 a 33 -> so contagens 2026 semana<=33
        dados = ovitrampas_core.monitoramento_contagens(
            db_path, {"ano": "2026", "semana_ini": "1", "semana_fim": "33"}
        )
        self.assertEqual("API Conta Ovos", dados["fonte"])
        t = dados["totais"]
        self.assertEqual(2, t["leituras"])  # 97/33 e 98/33 (exclui 97/34 e 2025)
        self.assertEqual(0, t["positivas"])  # ambas ovos=0
        # sem filtro de semana (ano 2026) -> 3 (33,33,34)
        dados2 = ovitrampas_core.monitoramento_contagens(db_path, {"ano": "2026"})
        self.assertEqual(3, dados2["totais"]["leituras"])

    def test_monitoramento_contagens_ocorrencias_ranking_e_realocar(self):
        import tempfile
        base = Path(tempfile.mkdtemp())
        db_path = base / "mon3.db"
        conn = db_core.connect(db_path)
        conn.executescript("""
            CREATE TABLE usuarios (
                id_usuario INTEGER PRIMARY KEY,
                nome TEXT, nivel TEXT, ativo INTEGER DEFAULT 1
            );
            CREATE TABLE agentes (
                id_agente INTEGER PRIMARY KEY,
                nome TEXT, ativo INTEGER DEFAULT 1
            );
        """)
        laboratorio_core.ensure_schema(db_path)  # cria schema ovitrampas + laboratorio
        conn.execute("INSERT INTO usuarios(id_usuario,nome,nivel) VALUES (1,'Azimir','visualizador')")
        agora = "2026-08-24T10:00:00"
        conn.execute(
            """INSERT INTO ovitrampas_armadilhas
               (ovitrampa_id, localidade, complemento, latitude, longitude, atualizado_em)
               VALUES ('97','Roma','A',-25.1,-49.2,?),
                      ('98','Roma','B',-25.2,-49.3,?),
                      ('77','Zona','REALOCAR em teste',-25.3,-49.4,?)""",
            (agora, agora, agora),
        )
        # Espelho de contagens (o GET lastcounting NAO traz a ocorrencia).
        rows = [
            # id_contagem, ovitrampa, ano, sem, data, ovos
            ("900", "97", 2026, 33, "2026-08-10", 3),
            ("901", "97", 2026, 34, "2026-08-20", 5),
            ("902", "98", 2026, 34, "2026-08-20", 0),
            ("903", "77", 2026, 34, "2026-08-20", 0),
        ]
        for idc, ovi, ano, sem, data, ovos in rows:
            conn.execute(
                """INSERT INTO ovitrampas_ocorrencias_conta_ovos
                   (id_contagem, ovitrampa_id, ano, semana, data, ovos,
                    resultado, latitude, longitude, arquivo_origem, importado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,'API privada Conta Ovos','2026-09-02')""",
                (idc, ovi, ano, sem, data, ovos,
                 "Positiva" if ovos else "Negativa", -25.1, -49.2),
            )
        # Lote de laboratorio concluido/enviado com ocorrencia 6 (Casa fechada)
        # na ovitrampa 97, coleta em 2026-08-20 (casando com a contagem 901).
        diario = conn.execute(
            """INSERT INTO ovitrampas_diarios(nome,ativo,criado_em,atualizado_em)
               VALUES ('Roma 1',1,?,?)""",
            (agora, agora),
        ).lastrowid
        evento = conn.execute(
            """INSERT INTO ovitrampas_calendario_eventos
               (data,movimento,ciclo,criado_em,atualizado_em)
               VALUES ('2026-08-20','troca','9',?,?)""",
            (agora, agora),
        ).lastrowid
        lote = conn.execute(
            """INSERT INTO ovitrampas_laboratorio_lotes
               (id_evento,id_diario,diario_nome,data_movimento,movimento,ciclo,
                status,criado_em,atualizado_em)
               VALUES (?,?,?,'2026-08-20','troca','9','enviado_conta_ovos',?,?)""",
            (evento, diario, "Roma 1", agora, agora),
        ).lastrowid
        conn.execute(
            """INSERT INTO ovitrampas_laboratorio_itens
               (id_lote,ovitrampa_id,complemento,localidade,ovos,ocorrencia,atualizado_em)
               VALUES (?,?,'A','Roma',5,6,?)""",
            (lote, "97", agora),
        )
        conn.commit()
        conn.close()

        dados = ovitrampas_core.monitoramento_contagens(
            db_path, {"ano": "2026", "semana_ini": "1", "semana_fim": "34"}
        )
        t = dados["totais"]
        # ocorrencia vem do lancamento de laboratorio (codigo 6), nao do espelho
        self.assertEqual(1, t["ocorrencias"])
        self.assertEqual("Lançamentos de laboratório", dados["ocorrencias_fonte"])
        self.assertEqual(1, t["realocar"])  # 77 marcada REALOCAR no cadastro local
        # ranking so com positivas: 97 (2 positivas) -> 1 linha
        self.assertEqual(1, len(dados["ranking_positivas"]))
        rank = dados["ranking_positivas"][0]
        self.assertEqual("97", rank["ovitrampa_id"])
        self.assertEqual(2, rank["positivas"])
        self.assertEqual(8, rank["ovos"])
        self.assertEqual("2026 / Semana 34", rank["ultima_positiva"])
        # ocorrencias detalhadas vindas do laboratorio
        self.assertEqual(1, len(dados["ocorrencias"]))
        occ_row = dados["ocorrencias"][0]
        self.assertEqual(6, occ_row["codigo"])
        self.assertEqual("Casa fechada", occ_row["descricao"])
        self.assertEqual("97", occ_row["armadilhas_destaque"][0]["ovitrampa_id"])
        # positivas recentes trazem vezes_positiva
        self.assertEqual(1, len(dados["positivas_recentes"]))
        self.assertEqual(2, dados["positivas_recentes"][0]["vezes_positiva"])
        # realocar registros locais presentes
        ids = [r["ovitrampa_id"] for r in dados["realocar"]["registros"]]
        self.assertIn("77", ids)

    def test_monitoramento_contagens_realocar_fica_vazio_sem_marcador(self):
        import tempfile
        base = Path(tempfile.mkdtemp())
        db_path = base / "mon4.db"
        conn = db_core.connect(db_path)
        ovitrampas_core.ensure_schema(conn)
        conn.execute(
            """INSERT INTO ovitrampas_armadilhas
               (ovitrampa_id, localidade, atualizado_em)
               VALUES ('97','Roma','2026-08-24T10:00:00')"""
        )
        conn.execute(
            """INSERT INTO ovitrampas_ocorrencias_conta_ovos
               (id_contagem, ovitrampa_id, ano, semana, data, ovos,
                resultado, latitude, longitude, arquivo_origem, importado_em)
               VALUES ('900','97',2026,34,'2026-08-10',0,'Negativa',
                       -25.1,-49.2,'API privada Conta Ovos','2026-09-02')"""
        )
        conn.commit()
        conn.close()
        dados = ovitrampas_core.monitoramento_contagens(
            db_path, {"ano": "2026", "semana_ini": "1", "semana_fim": "34"}
        )
        self.assertEqual(0, dados["totais"]["realocar"])
        self.assertEqual(0, len(dados["realocar"]["registros"]))


if __name__ == "__main__":
    unittest.main()
