import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app_core import esporotricose as esporotricose_core
from app_core import esporotricose_humanos as humanos
from blueprints.esporotricose import bp


ROOT = Path(__file__).resolve().parents[1]


class EsporotricoseHumanosCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "humanos.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, cod_localidade INTEGER)")
        conn.execute("CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE)")
        conn.execute("INSERT INTO localidades(nome) VALUES ('São Venâncio')")
        humanos.ensure_schema(conn)
        conn.commit()
        conn.close()

    def test_cadastro_preserva_sus_mascara_lista_e_atualiza_status(self):
        paciente_id = humanos.salvar_paciente(self.db_path, {
            "nome": "Paciente Teste",
            "data_nascimento": "1980-05-03",
            "cartao_sus": "001234567890123",
            "nome_mae": "Mãe Teste",
            "status": "Em tratamento",
            "localidade": "Sao Venancio",
            "logradouro": "Rua das Flores",
            "numero": "25",
            "latitude": "-25,123",
            "longitude": "-49,456",
        }, "Administrador")

        detalhe = humanos.obter_paciente(self.db_path, paciente_id)
        mais_recente = humanos.salvar_paciente(self.db_path, {
            "nome": "Paciente com notificação",
            "status": "Em tratamento",
            "data_notificacao": "2026-09-20",
        }, "Administrador")
        lista = humanos.listar_pacientes(self.db_path, {"busca": "Paciente"})
        item_original = next(
            item for item in lista["registros"] if item["id_paciente"] == paciente_id
        )
        self.assertEqual(detalhe["cartao_sus"], "001234567890123")
        self.assertTrue(item_original["cartao_sus"].endswith("0123"))
        self.assertNotIn("001234567890123", item_original["cartao_sus"])
        self.assertIsNotNone(detalhe["id_localidade"])
        self.assertEqual(lista["registros"][0]["id_paciente"], mais_recente)

        humanos.salvar_acompanhamento(self.db_path, paciente_id, {
            "data": "2026-09-22", "status": "Acabou tratamento", "observacoes": "Alta informada pela UBS."
        }, "Administrador")
        atualizado = humanos.obter_paciente(self.db_path, paciente_id)
        self.assertEqual(atualizado["status"], "Acabou tratamento")
        self.assertEqual(len(atualizado["acompanhamentos"]), 1)

    def test_outros_exige_descricao_e_sus_nao_duplica(self):
        with self.assertRaises(humanos.ValidationError):
            humanos.salvar_paciente(self.db_path, {"nome": "A", "status": "Outros"}, "Admin")
        humanos.salvar_paciente(self.db_path, {"nome": "A", "status": "Outros", "status_outro": "Em investigação", "cartao_sus": "0001"}, "Admin")
        with self.assertRaises(humanos.ValidationError):
            humanos.salvar_paciente(self.db_path, {"nome": "B", "status": "Em tratamento", "cartao_sus": "0001"}, "Admin")

    def test_sugestoes_so_vinculam_apos_confirmacao(self):
        paciente_id = humanos.salvar_paciente(self.db_path, {
            "nome": "Paciente", "status": "Em tratamento", "localidade": "São Venâncio",
            "quarteirao": "1072", "logradouro": "Rua das Flores", "numero": "25",
        }, "Admin")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO esporotricose_visitas(id_visita,kobo_uuid,data,localidade,id_localidade,quarteirao,logradouro,numero,origem_estrutura,processado_em) VALUES ('v1','u1','2026-09-01','São Venâncio',1,1072,'Rua das Flores','25','nova','2026-09-01T10:00:00')")
        conn.execute("INSERT INTO esporotricose_imoveis(id_localidade,localidade,quarteirao,logradouro_chave,numero_chave,chave,criado_em,atualizado_em) VALUES (1,'São Venâncio','1072','rua das flores','25','1|1072|rua das flores|25','agora','agora')")
        imovel_id = conn.execute("SELECT id_imovel FROM esporotricose_imoveis").fetchone()[0]
        conn.execute("INSERT INTO esporotricose_visita_imoveis(id_visita,id_imovel,origem,confianca,vinculado_em) VALUES ('v1',?,'manual',100,'agora')", (imovel_id,))
        conn.execute("INSERT INTO esporotricose_doentes_animais(chave,tutor,nome,especie,localidade,quarteirao,endereco,status,criado_em,atualizado_em) VALUES ('a1','Tutor','Mimi','Gato','São Venâncio','1072','Rua das Flores, 25','Em tratamento','agora','agora')")
        animal_id = conn.execute("SELECT id_animal_doente FROM esporotricose_doentes_animais").fetchone()[0]
        conn.commit()
        conn.close()

        sugestoes = humanos.sugestoes_vinculos(self.db_path, paciente_id)
        self.assertEqual(sugestoes["imoveis"][0]["id_imovel"], imovel_id)
        self.assertEqual(sugestoes["animais"][0]["id_animal_doente"], animal_id)
        self.assertEqual(humanos.obter_paciente(self.db_path, paciente_id)["imoveis"], [])

        humanos.alterar_vinculo(self.db_path, paciente_id, "imovel", imovel_id, "Admin")
        humanos.alterar_vinculo(self.db_path, paciente_id, "animal", animal_id, "Admin")
        detalhe = humanos.obter_paciente(self.db_path, paciente_id)
        self.assertEqual(len(detalhe["imoveis"]), 1)
        self.assertEqual(len(detalhe["animais"]), 1)


class EsporotricoseHumanosPermissoesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "permissoes.db"
        self.app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
        self.app.config.update(TESTING=True, SECRET_KEY="teste", DB_PATH=str(self.db_path), ANEXOS_DIR=str(Path(self.tmp.name) / "anexos"))
        self.app.jinja_env.globals["csrf_token"] = lambda: "teste"
        self.app.jinja_env.filters["data_br"] = lambda valor: valor or ""
        self.app.context_processor(lambda: {
            "TIPO_CORES": {}, "TIPO_LABELS": {}, "AGENDA_TIPO_LABELS": {},
            "AMBIENTE_TESTE": False, "sidebar_groups": [], "usuario_atual": None,
            "APP_VERSION_LABEL": "Teste", "APP_VERSION": "teste", "nav_pendentes": 0,
        })
        self.app.register_blueprint(bp)
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE usuarios (id_usuario INTEGER PRIMARY KEY, usuario TEXT, nome TEXT, nivel TEXT, ativo INTEGER)")
        conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, cod_localidade INTEGER)")
        conn.execute("CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE)")
        conn.executemany("INSERT INTO usuarios VALUES (?,?,?,?,1)", [(1,"operador","Operador","operador"),(2,"admin","Admin","admin")])
        conn.execute("INSERT INTO localidades(nome) VALUES ('São Venâncio')")
        conn.commit()
        conn.close()

    def _client(self, uid):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["uid"] = uid
        return client

    def test_operador_nao_consulta_nem_altera_casos_humanos(self):
        client = self._client(1)
        with patch("app_core.auth.render_template", return_value="Sem permissão"):
            for metodo, rota in [
                ("GET", "/esporotricose/humanos"),
                ("GET", "/api/esporotricose/humanos"),
                ("POST", "/api/esporotricose/humanos"),
                ("GET", "/api/esporotricose/humanos/1"),
                ("POST", "/api/esporotricose/humanos/1/acompanhamentos"),
                ("GET", "/api/esporotricose/humanos/1/sugestoes-vinculos"),
                ("POST", "/api/esporotricose/humanos/1/vinculos/imovel/1"),
                ("POST", "/api/esporotricose/humanos/1/anexos"),
                ("GET", "/esporotricose/humanos/anexos/1/download"),
            ]:
                with self.subTest(rota=rota):
                    self.assertEqual(client.open(rota, method=metodo, json={}).status_code, 403)

    def test_admin_cria_e_abre_as_telas_do_paciente(self):
        client = self._client(2)
        resposta = client.post("/api/esporotricose/humanos", json={
            "nome": "Paciente administrativo",
            "status": "Em tratamento",
            "cartao_sus": "0000123",
            "localidade": "São Venâncio",
        })
        self.assertEqual(resposta.status_code, 201)
        paciente_id = resposta.get_json()["id_paciente"]
        self.assertEqual(client.get("/esporotricose/humanos").status_code, 200)
        self.assertEqual(client.get("/esporotricose/humanos/novo").status_code, 200)
        self.assertEqual(client.get(f"/esporotricose/humanos/{paciente_id}").status_code, 200)
        self.assertEqual(client.get(f"/esporotricose/humanos/{paciente_id}/editar").status_code, 200)


if __name__ == "__main__":
    unittest.main()
