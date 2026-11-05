"""Conferencia/aprovacao manual em massa ficticia e transporte Kobo falso."""
import contextlib
import io
import json
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import app
from app_core import auth, bri, db, kobo_api, kobo_conciliacao as core, sessoes
from scripts.preparar_massa_web_teste import preparar


ROOT = Path(__file__).resolve().parents[1]


class KoboConciliacao201Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".venv")
        cls.base = Path(cls.temp.name)
        cls.seed = cls.base / "seed.db"
        with contextlib.redirect_stdout(io.StringIO()):
            preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.base))
        self.path = self.directory / "ficticio.db"
        shutil.copyfile(self.seed, self.path)
        config = dict(DB_PATH=str(self.path), TESTING=True, WTF_CSRF_ENABLED=False,
            SETORES_ENABLED=True, TERMOS_USO_ENABLED=False,
            SECRET_KEY="segredo-exclusivo-de-ensaio", CONFIG_PATH=str(ROOT / "config.json"),
            BACKUP_DIR=str(self.directory / "backups"), BACKUP_COMPLETO_DIR=str(self.directory / "completos"),
            UPLOAD_TEMP=str(self.directory / "uploads"), KOBO_CONFIG_PATH=str(self.directory / "kobo.json"))
        self.apps = {s: app.create_app({**config, "SETOR": s}) for s in ("endemias", "ambiental")}
        self.sql("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) SELECT 5,'superficticio','Super ficticio',senha_hash,'superadmin',criado_em FROM usuarios WHERE id_usuario=1")
        self.sql("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) SELECT 6,'adminficticio','Admin ficticio',senha_hash,'admin',criado_em FROM usuarios WHERE id_usuario=1")
        for table in ("bri_agentes", "bri_registros", "recolhimento_agentes", "recolhimentos"):
            self.sql("DELETE FROM " + table)
        self.sql("INSERT INTO bri_registros(id_bri,kobo_uuid,data,hora,localidade,id_localidade,logradouro,numero,quarteirao,quantidade_carga,agentes_texto,destino_tratamento,arquivo_origem,processado_em) VALUES('bri-ficticio','uuid-bri-ficticio','2026-06-03','08:00','Localidade Ficticia',1,'Rua Ficticia','10',123,2.5,'Agente Ficticio','Outro','origem-preservada.xlsx','2026-06-03')")
        self.sql("INSERT INTO bri_agentes VALUES('bri-ficticio',1)")
        self.sql("INSERT INTO recolhimentos(id_recolhimento,kobo_uuid,data,hora,localidade,id_localidade,agentes_texto,pneu,louca_sanitaria,tv,parachoque,outros,total_materiais,processado_em) VALUES('rec-ficticio','uuid-rec-ficticio','2026-06-03','08:00','Localidade Ficticia',1,'Agente Ficticio',1,2,100,0,3,106,'2026-06-03')")
        (self.directory / "kobo.json").write_text(json.dumps({"server_url": "https://kf.kobotoolbox.org", "api_token": "token-ficticio", "assets": {"BRI": "form-bri-ficticio", "RECOLHIMENTO": "form-rec-ficticio"}}), encoding="utf-8")
        self.records = [self.bri_record()]
        self.transport = mock.patch.object(kobo_api, "fetch_submissions", side_effect=lambda *a, **kw: (self.records, {"count": len(self.records), "next": None})).start()
        self.addCleanup(mock.patch.stopall)
        self.client = self.logged()

    def sql(self, statement, parameters=()):
        conn = db.connect(str(self.path))
        try:
            cur = conn.execute(statement, parameters)
            rows = cur.fetchall() if cur.description else []
            conn.commit()
            return rows
        finally:
            conn.close()

    def logged(self, area="endemias", uid=1):
        application = self.apps[area]
        client = application.test_client()
        user = db.query_one(str(self.path), "SELECT * FROM usuarios WHERE id_usuario=?", (uid,))
        with application.app_context(), client.session_transaction() as session:
            session.update(uid=uid, nome=user["nome"], auth_token=auth.token_sessao(user["senha_hash"]), sessao_id=sessoes.criar(str(self.path), user))
        return client

    def bri_record(self, uuid="uuid-bri-ficticio", carga=9.5):
        return {"_uuid": uuid, "start": "2026-06-03T08:00:00", "end": "2026-06-03T09:00:00", "Digite_a_data": "2026-06-03", "Digite_a_hora": "08:00", "Nome_do_s_agente_s": "AgenteNovo", "Onde_vai_ser_realizado_o_trata": "outro", "group_pt6ft99/localidade_001": "Localidade Ficticia", "group_pt6ft99/Logradouro_001": "Rua Ficticia", "group_pt6ft99/N_mero": 10, "group_pt6ft99/Quarteir_o": 123, "group_rb5ho54/Quantidade_de_carga": carga}

    def preview(self, tipo="BRI", client=None, **extra):
        return (client or self.client).post("/api/kobo/conferencia-correcao", json={"tipo": tipo, "inicio": "2026-06-01", "fim": "2026-06-30", **extra})

    def selection(self, preview, *fields, row=0):
        return [{"registro": preview["registros"][row]["chave"], "campo": f} for f in fields]

    def apply(self, preview, fields, client=None, **extra):
        return (client or self.client).post("/api/kobo/conferencia-correcao/aplicar", json={"token": preview["token"], "selecoes": fields, **extra})

    def test_previa_nao_grava_e_aplicacao_preserva_campos_nao_selecionados(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json
        self.assertEqual(self.sql("SELECT quantidade_carga FROM bri_registros")[0][0], 2.5)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auditoria_eventos")[0][0], 0)
        self.sql("UPDATE bri_registros SET logradouro='Ajuste manual preservado'")
        applied = self.apply(result, self.selection(result, "quantidade_carga"))
        self.assertEqual(applied.status_code, 200, applied.json)
        row = self.sql("SELECT quantidade_carga,logradouro,arquivo_origem FROM bri_registros")[0]
        self.assertEqual(tuple(row), (9.5, "Ajuste manual preservado", "origem-preservada.xlsx"))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auditoria_eventos WHERE acao='kobo_correcao_campos_aprovados' AND setor='endemias'")[0][0], 1)
        self.assertNotEqual(self.apply(result, self.selection(result, "quantidade_carga")).status_code, 200)

    def test_admin_e_superadmin_podem_gerar_mas_outros_perfis_nao(self):
        result = self.preview().json
        for uid in (1, 5):
            self.assertEqual(self.preview(client=self.logged(uid=uid)).status_code, 200)
        self.transport.reset_mock()
        for uid in (2, 3, 4):
            self.assertEqual(self.preview(client=self.logged(uid=uid)).status_code, 403)
            self.assertEqual(self.apply(result, self.selection(result, "quantidade_carga"), client=self.logged(uid=uid)).status_code, 403)
        self.transport.assert_not_called()

    def test_usuario_setor_expiracao_e_tamper_bloqueiam_aplicacao(self):
        result = self.preview().json
        choices = self.selection(result, "quantidade_carga")
        self.assertEqual(self.apply(result, choices, client=self.logged(uid=6)).status_code, 400)
        self.assertEqual(self.apply(result, choices, client=self.logged("ambiental")).status_code, 403)
        with mock.patch.object(core.time, "time", return_value=time.time() + core.TTL + 1):
            self.assertEqual(self.apply(result, choices).status_code, 409)
        file = self.directory / "uploads" / "endemias" / "conferencias_kobo" / (result["token"] + ".json")
        envelope = json.loads(file.read_text(encoding="utf-8"))
        envelope["body"]["registros"][0]["depois"]["quantidade_carga"] = 999
        file.write_text(json.dumps(envelope), encoding="utf-8")
        self.assertEqual(self.apply(result, choices).status_code, 400)
        self.assertEqual(self.sql("SELECT quantidade_carga FROM bri_registros")[0][0], 2.5)

    def test_sem_selecao_bulk_ids_valores_e_campos_nao_oferecidos_sao_recusados(self):
        result = self.preview().json
        key = result["registros"][0]["chave"]
        for choices in ([], True, "todos", [{"registro": key, "campo": "id_pe"}], [{"registro": key, "campo": "data"}], [{"registro": key, "campo": "quantidade_carga", "valor": 999}], [{"registro": "outro", "campo": "quantidade_carga"}]):
            with self.subTest(choices=choices):
                self.assertEqual(self.apply(result, choices).status_code, 400)
        self.assertEqual(self.apply(result, self.selection(result, "quantidade_carga"), aplicar_todos=True).status_code, 400)
        self.assertEqual(self.sql("SELECT quantidade_carga FROM bri_registros")[0][0], 2.5)

    def test_conflito_em_segundo_registro_reverte_todos(self):
        self.sql("INSERT INTO bri_registros(id_bri,kobo_uuid,data,quantidade_carga,processado_em) VALUES('bri-segundo','uuid-bri-segundo','2026-06-03',1,'2026-06-03')")
        self.records.append(self.bri_record("uuid-bri-segundo", 4))
        result = self.preview().json
        self.sql("UPDATE bri_registros SET quantidade_carga=3 WHERE id_bri='bri-segundo'")
        choices = self.selection(result, "quantidade_carga") + self.selection(result, "quantidade_carga", row=1)
        self.assertEqual(self.apply(result, choices).status_code, 409)
        self.assertEqual([r[0] for r in self.sql("SELECT quantidade_carga FROM bri_registros ORDER BY id_bri")], [2.5, 3])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auditoria_eventos")[0][0], 0)

    def test_agentes_e_auditoria_participam_da_transacao(self):
        result = self.preview().json
        choices = self.selection(result, "quantidade_carga", "agentes_texto")
        with mock.patch("blueprints.processar.audit.registrar_evento", side_effect=RuntimeError("Falha ficticia")):
            self.assertEqual(self.apply(result, choices).status_code, 500)
        self.assertEqual(self.sql("SELECT quantidade_carga FROM bri_registros")[0][0], 2.5)
        self.assertEqual([r[0] for r in self.sql("SELECT id_agente FROM bri_agentes")], [1])
        self.assertEqual(self.apply(result, choices).status_code, 200)
        names = [r[0] for r in self.sql("SELECT a.nome FROM bri_agentes ba JOIN agentes a ON a.id_agente=ba.id_agente")]
        self.assertEqual(names, ["AgenteNovo"])

    def test_recolhimentos_recalcula_total_sem_tocar_material_nao_aprovado(self):
        self.records[:] = [{"_uuid": "uuid-rec-ficticio", "start": "2026-06-03T08:00:00", "end": "2026-06-03T09:00:00", "Data": "2026-06-03", "Hora": "08:00", "Localidade": "Localidade Ficticia", "group_cw8wz69/A1": 4, "group_cw8wz69/A2": 2, "group_cw8wz69/B": 0, "group_cw8wz69/E": 0, "group_cw8wz69/D2": 3}]
        response = self.preview("RECOLHIMENTO")
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json
        self.assertEqual(self.apply(result, self.selection(result, "pneu")).status_code, 200)
        self.assertEqual(tuple(self.sql("SELECT pneu,tv,total_materiais FROM recolhimentos")[0]), (4, 100, 109))

    def test_pe_reconciliado_usando_somente_campos_aprovados(self):
        self.sql("INSERT INTO pontos_estrategicos(id_pe,codigo_pe,nome,id_localidade,localidade,quarteirao,logradouro,numero,criado_em,atualizado_em) VALUES(1,'PE-ficticio','Ponto ficticio',1,'Localidade Ficticia',123,'Rua Ficticia','10','2026-06-03','2026-06-03')")
        self.records[0]["Onde_vai_ser_realizado_o_trata"] = "ponto_estrat_gico"
        self.records[0].update({"group_zn1kq42/localidade": "Localidade Ficticia", "group_zn1kq42/logradouro": "Outro endereco nao aprovado", "group_zn1kq42/quarteirao": 999, "group_zn1kq42/numero": 99})
        result = self.preview().json
        self.assertEqual(self.apply(result, self.selection(result, "destino_tratamento")).status_code, 200)
        self.assertEqual(tuple(self.sql("SELECT id_pe,codigo_pe,logradouro,quarteirao FROM bri_registros")[0]), (1, "PE-ficticio", "Rua Ficticia", 123))

    def test_sem_uuid_duplicado_resposta_incompleta_periodo_e_outro_setor_nao_preparam(self):
        for records in ([{}], [self.bri_record(), self.bri_record()]):
            self.records[:] = records
            self.assertEqual(self.preview().status_code, 400)
        self.records[:] = [self.bri_record()]
        self.transport.side_effect = lambda *a, **kw: (self.records, {"count": 2, "next": "mais"})
        self.assertEqual(self.preview().status_code, 400)
        self.transport.reset_mock()
        self.assertEqual(self.preview(inicio="2026-07-01", fim="2026-06-01").status_code, 400)
        self.assertEqual(self.preview(client=self.logged("ambiental")).status_code, 403)
        self.transport.assert_not_called()

    def test_nulo_e_zero_sao_diferencas_distintas(self):
        self.sql("UPDATE bri_registros SET quantidade_carga=NULL")
        self.records[0]["group_rb5ho54/Quantidade_de_carga"] = 0
        result = self.preview().json
        field = next(c for c in result["registros"][0]["alteracoes"] if c["campo"] == "quantidade_carga")
        self.assertIsNone(field["antes"])
        self.assertEqual(field["depois"], 0)
        self.assertEqual(self.apply(result, self.selection(result, "quantidade_carga")).status_code, 200)
        self.assertEqual(self.sql("SELECT quantidade_carga FROM bri_registros")[0][0], 0)

    def test_uuid_nao_importado_nao_usa_kobo_id_como_fallback(self):
        self.sql("UPDATE bri_registros SET kobo_id=123")
        self.records[:] = [self.bri_record("uuid-nao-importado")]
        self.records[0]["_id"] = 123
        result = self.preview().json
        self.assertEqual(result["encontrados"], 0)
        self.assertEqual(result["nao_importados"], 1)
        self.assertEqual(result["registros"], [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM bri_registros")[0][0], 1)

    def test_mudanca_de_vinculo_de_agente_tambem_causa_conflito(self):
        result = self.preview().json
        self.sql("DELETE FROM bri_agentes")
        self.assertEqual(self.apply(result, self.selection(result, "agentes_texto")).status_code, 409)
        self.assertEqual(self.sql("SELECT agentes_texto FROM bri_registros")[0][0], "Agente Ficticio")

    def test_csrf_e_selecao_inicial_da_interface(self):
        self.apps["endemias"].config["WTF_CSRF_ENABLED"] = True
        self.assertEqual(self.preview().status_code, 400)
        self.transport.assert_not_called()
        html = self.client.get("/processar").get_data(as_text=True)
        self.assertIn('id="conferencia-correcao"', html)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)
        response = self.client.post("/api/kobo/conferencia-correcao", json={"tipo": "BRI", "inicio": "2026-06-01", "fim": "2026-06-30"}, headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.client.post("/api/kobo/conferencia-correcao/aplicar", json={"token": response.json["token"], "selecoes": []}).status_code, 400)
