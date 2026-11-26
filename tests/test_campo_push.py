import base64
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import DSS

from app_core import campo_push, campo_release, db, sessoes


ENDPOINT = "https://fcm.googleapis.com/fcm/send/token-sintetico-com-20-caracteres"
ENDPOINT_ATUAL = ENDPOINT.replace("/fcm/send/", "/wp/")


def dec(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class CampoPushTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_setores import SetoresTests

        cls.fixture = SetoresTests
        cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def setUp(self):
        self.f = self.fixture("test_campo_sessao_conta_setor_e_proprios")
        self.f.setUp()
        self.path = str(self.f.path)
        conn = db.connect(self.path)
        try:
            ddl = Path("migrations/postgresql/0042_campo_push.sql").read_text()
            conn.executescript(ddl.replace("id_agente bigint NOT NULL", "id_agente bigint", 1))
            conn.executescript(Path("migrations/postgresql/0044_campo_push_teste_estado.sql").read_text())
        finally:
            conn.close()
        self.f.sql("UPDATE usuarios SET id_agente=1 WHERE id_usuario=1")
        self.user = db.query_one(self.path, "SELECT * FROM usuarios WHERE id_usuario=1")
        self.env = patch.dict(os.environ, {"ENDEMIAS_FORMULARIOS_OFFLINE_USUARIO": "admin",
                                          campo_push.CHAVE_ENV: "chave-ficticia"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.key = ECC.generate(curve="P-256")
        self.subject = "https://endemias.example.org"

    def test_superadmin_sem_agente_pode_inscrever_e_enviar_apenas_teste(self):
        os.environ["ENDEMIAS_FORMULARIOS_OFFLINE_USUARIO"] = "conta-de-campo"
        self.f.sql("UPDATE usuarios SET id_agente=NULL WHERE id_usuario=1")
        self.f.apps["endemias"].config["ACESSO_EXTERNO"] = True
        cliente = self.f.client("endemias")
        url = "/api/formularios/campo-push"
        https = {"base_url": "https://localhost"}
        dados = {"usuario": 1, "endpoint": ENDPOINT_ATUAL}
        with patch.object(campo_push, "chave", return_value=self.key):
            self.assertEqual(cliente.get(url, **https).json["modo"], "teste")
            self.assertEqual(cliente.post(url, json={**dados, "acao":"ativar"}, **https).status_code, 200)
            gestor = self.f.client("endemias", 5)
            self.assertEqual(gestor.get(url, **https).status_code, 403)
            self.assertIsNone(db.scalar(self.path, "SELECT id_agente FROM campo_push_aparelhos"))
            self.f.sql("UPDATE usuarios SET id_agente=1 WHERE id_usuario=1")
            with patch.object(campo_push.avisos_campo, "pendentes_push") as pendentes, patch.object(
                campo_push, "enviar", return_value=201
            ) as enviar:
                campo_push.verificar_resultados(self.path,self.key,self.subject)
                pendentes.assert_not_called()
                enviar.assert_not_called()
                resposta = cliente.post(url, json={**dados, "acao":"testar"}, **https)
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.json["segundos_para_fechar"], campo_push.TESTE_ESPERA)
                self.assertEqual(cliente.get(url, **https).json["teste_estado"], "agendado")
                campo_push.verificar_resultados(self.path,self.key,self.subject,
                                               datetime.now()+timedelta(seconds=campo_push.TESTE_ESPERA+1))
                pendentes.assert_not_called()
                enviar.assert_called_once_with(ENDPOINT_ATUAL,self.key,self.subject)
                self.assertEqual(cliente.get(url, **https).json["teste_estado"], "aceito")

    def test_atualizacao_reune_so_os_resumos_das_versoes_puladas(self):
        cliente = self.f.client("endemias")
        with patch.object(campo_release, "APP_VERSION", "2.14.2"):
            resposta = cliente.get("/api/formularios/kobo/versao-offline?desde=2.14.0")
            self.assertEqual([item["versao"] for item in resposta.json["atualizacoes"]], ["2.14.2", "2.14.1"])
            self.assertEqual(campo_release.historico("2.14.2"), [])

    def test_transporte_assina_sem_dados_da_coleta_e_restringe_destino(self):
        hdr = campo_push._cabecalhos(self.key, self.subject, 1000)
        signed, public = hdr["Authorization"].removeprefix("vapid t=").split(",k=")
        header, claims, sig = signed.split(".")
        pub = ECC.import_key(dec(public), curve_name="P-256")
        DSS.new(pub, "fips-186-3", encoding="binary").verify(SHA256.new(f"{header}.{claims}".encode()), dec(sig))
        self.assertEqual(json.loads(dec(claims)), {"aud":campo_push.ORIGEM_FCM,"exp":4600,"sub":self.subject})
        for url in ("http://fcm.googleapis.com", "https://fcm.googleapis.com@localhost/fcm/send/"+"x"*22,
                    ENDPOINT_ATUAL+"?redirect=123", ENDPOINT.replace("/fcm/send/", "/")):
            with self.assertRaises(ValueError):
                campo_push.validar_endpoint(url)
        with patch.object(campo_push, "_http") as transport:
            transport.return_value.request.return_value.status = 201
            for destino in (ENDPOINT, ENDPOINT_ATUAL):
                self.assertEqual(campo_push.enviar(destino,self.key,self.subject),201)
                self.assertEqual(transport.return_value.request.call_args.args, ("POST", destino))
            sent = transport.return_value.request.call_args.kwargs
            self.assertEqual(sent["body"], b"")
            self.assertFalse(sent["redirect"])

    def test_agenda_teste_com_tempo_para_fechar_e_revoga_na_saida(self):
        campo_push.inscrever(self.path,self.user,"sessao-ficticia",ENDPOINT)
        with patch.object(campo_push, "enviar",return_value=201) as send:
            campo_push.testar(self.path,1,ENDPOINT)
            with self.assertRaises(ValueError):
                campo_push.testar(self.path,1,ENDPOINT)
            campo_push.verificar_resultados(self.path,self.key,self.subject)
            send.assert_not_called()
            espera = campo_push.TESTE_ESPERA
            campo_push.verificar_resultados(self.path,self.key,self.subject,datetime.now()+timedelta(seconds=espera+1))
            send.assert_called_once_with(ENDPOINT,self.key,self.subject)
            campo_push.verificar_resultados(self.path,self.key,self.subject,datetime.now()+timedelta(seconds=espera+2))
            self.assertEqual(send.call_count,1)
        conn = db.connect(self.path)
        try:
            with conn:
                campo_push.revogar_sessao(conn,sessoes.digest("sessao-ficticia"),1)
        finally:
            conn.close()
        self.assertIsNone(campo_push.status(self.path, 1)["aparelho"])

    def test_resultados_proprios_agrupados_retentativa_sem_repetir_envio_aceito(self):
        now = datetime.now()
        data = now.date().isoformat()
        campo_push.inscrever(self.path,self.user,"sessao-ficticia",ENDPOINT)
        for num, agent, offset in ((901,1,10),(902,1,12),(903,2,13),(904,1,-60)):
            self.f.sql("""INSERT INTO visitas(id_visita,kobo_uuid,tipo,data,processado_em)
                          VALUES (?,?,'PE',?,?)""",(str(num),str(num),data,now.isoformat()))
            self.f.sql("INSERT INTO visita_agentes(id_visita,id_agente) VALUES (?,?)",(str(num),agent))
            self.f.sql("INSERT INTO coletas(id_coleta,id_visita,num_tubo) VALUES (?,?,?)",(str(num),str(num),str(num)))
            self.f.sql("""INSERT INTO resultados_laboratorio(id_coleta,num_tubo,data_coleta,data_leitura,atualizado_em)
                          VALUES (?,?,?,?,?)""",(str(num),str(num),data,data,(now+timedelta(seconds=offset)).isoformat()))
        with patch.object(campo_push, "enviar",side_effect=[503,201,410]) as send:
            for _ in range(3):
                campo_push.verificar_resultados(self.path,self.key,self.subject,now+timedelta(seconds=30))
            self.assertEqual(send.call_count,2)
            self.assertEqual(db.scalar(self.path,"SELECT COUNT(*) FROM campo_push_entregas"),2)
            self.f.sql("UPDATE resultados_laboratorio SET atualizado_em=? WHERE num_tubo='902'",
                       ((now+timedelta(seconds=32)).isoformat(),))
            campo_push.verificar_resultados(self.path,self.key,self.subject,now+timedelta(seconds=35))
            self.assertIsNone(campo_push.status(self.path, 1)["aparelho"])

    def test_teste_sem_confirmação_expira(self):
        campo_push.inscrever(self.path, self.user, "sessao-ficticia", ENDPOINT_ATUAL)
        campo_push.testar(self.path, 1, ENDPOINT_ATUAL)
        with patch.object(campo_push, "enviar") as send:
            campo_push.verificar_resultados(self.path, self.key, self.subject,
                                           datetime.now()+timedelta(seconds=campo_push.TESTE_ESPERA+301))
            send.assert_not_called()
        self.assertEqual(campo_push.status(self.path, 1)["teste_estado"], "expirado")
