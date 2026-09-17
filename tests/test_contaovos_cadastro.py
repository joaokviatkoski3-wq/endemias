import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import contaovos_cadastro
from app_core import contaovos_client
from app_core import contaovos_fila
from app_core import db as db_core
from app_core import ovitrampas
from app_core import ovitrampas_laboratorio
from app_core import schema_metadata


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok":true}'


class ContaOvosCadastroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cadastro.db"
        conn = db_core.connect(self.path)
        conn.executescript("""
            CREATE TABLE usuarios (id_usuario INTEGER PRIMARY KEY, nome TEXT, nivel TEXT, ativo INTEGER DEFAULT 1);
            CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER DEFAULT 1);
            INSERT INTO usuarios VALUES (1,'Admin','admin',1);
        """)
        ovitrampas.ensure_schema(conn)
        ovitrampas_laboratorio._ensure_schema_conn(conn)
        contaovos_cadastro.ensure_schema_connection(conn)
        now = "2026-09-17T10:00:00"
        diario = conn.execute(
            "INSERT INTO ovitrampas_diarios(nome,ativo,criado_em,atualizado_em) VALUES ('Roma',1,?,?)", (now, now)
        ).lastrowid
        evento = conn.execute(
            "INSERT INTO ovitrampas_calendario_eventos(data,movimento,criado_em,atualizado_em) VALUES ('2026-09-17','troca',?,?)", (now, now)
        ).lastrowid
        lot = conn.execute(
            """INSERT INTO ovitrampas_laboratorio_lotes
               (id_evento,id_diario,diario_nome,data_movimento,movimento,status,criado_em,atualizado_em)
               VALUES (?,?,'Roma','2026-09-17','troca','concluido',?,?)""", (evento, diario, now, now)
        ).lastrowid
        conn.execute(
            "UPDATE ovitrampas_calendario_eventos SET id_grupo=1 WHERE id_evento=?", (evento,)
        )
        conn.execute(
            """INSERT INTO ovitrampas_calendario_eventos
               (data,movimento,id_grupo,criado_em,atualizado_em)
               VALUES ('2026-09-10','instalacao',1,?,?)""", (now, now)
        )
        conn.execute(
            """INSERT INTO ovitrampas_armadilhas
               (ovitrampa_id,rua,numero,complemento,localizacao,localidade,responsavel,
                telefone_responsavel,quarteirao,latitude,longitude,atualizado_em)
               VALUES ('97','Rua A','10','Casa','Quintal','Roma','Maria','41999990000','0012',-25.1,-49.2,?)""", (now,)
        )
        item = conn.execute(
            "INSERT INTO ovitrampas_laboratorio_itens(id_lote,ovitrampa_id,ovos,atualizado_em) VALUES (?,'97',0,?)", (lot, now)
        ).lastrowid
        conn.commit()
        self.conn, self.lot, self.item = conn, lot, item

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _update(self, **more):
        value = {
            "id_item": self.item, "rua": "Rua Nova", "numero": "11", "complemento": "Fundos",
            "localizacao": "Garagem", "localidade": "Santa Maria", "responsavel": "Ana",
            "telefone_responsavel": "41988880000", "quarteirao": "0013", "latitude": "-25.2", "longitude": "-49.3",
        }
        value.update(more)
        return value

    def test_prepara_edicao_local_e_mapeia_localidade_nos_dois_campos_remotos(self):
        result = contaovos_cadastro.prepare_lot_updates(
            self.conn, self.lot, [self._update()], user_name="Administrador"
        )
        self.conn.commit()
        self.assertEqual({"id_lote": self.lot, "alterados_localmente": 1, "enfileirados": 1}, result)
        row = self.conn.execute(
            "SELECT payload_json,status FROM contaovos_fila_cadastro_ovitrampas WHERE id_item=?", (self.item,)
        ).fetchone()
        payload = json.loads(row["payload_json"])
        self.assertEqual("Santa Maria", payload["ovitrap_address_district"])
        self.assertEqual("Santa Maria", payload["ovitrap_address_sector"])
        self.assertNotIn("telefone_responsavel", payload)
        local = self.conn.execute("SELECT rua,telefone_responsavel FROM ovitrampas_armadilhas WHERE ovitrampa_id='97'").fetchone()
        self.assertEqual("Rua Nova", local["rua"])
        self.assertEqual("41988880000", local["telefone_responsavel"])

    def test_resultado_incerto_bloqueia_reenvio_sem_nova_preparacao(self):
        contaovos_cadastro.prepare_lot_updates(self.conn, self.lot, [self._update()])
        self.conn.commit()
        with mock.patch.object(contaovos_cadastro.contaovos_client, "send_ovitrap_edit", return_value={"ok": False, "status_code": -1, "message": "timeout"}):
            first = contaovos_cadastro.process_item(self.conn, self.item, "segredo")
        self.assertTrue(first["uncertain"])
        with mock.patch.object(contaovos_cadastro.contaovos_client, "send_ovitrap_edit") as sender:
            second = contaovos_cadastro.process_item(self.conn, self.item, "segredo")
        self.assertFalse(second["ok"])
        self.assertTrue(second["uncertain"])
        sender.assert_not_called()

    def test_cliente_envia_bearer_e_corpo_formulario(self):
        calls = []

        def opener(req, timeout):
            calls.append((req, timeout))
            return _Response()

        result = contaovos_client.send_ovitrap_edit(
            "chave-teste", {"ovitrap_group_id": "97", "ovitrap_address_sector": "Roma"}, opener=opener
        )
        self.assertTrue(result["ok"])
        req, _timeout = calls[0]
        self.assertTrue(req.full_url.endswith("/posteditovitrap"))
        self.assertEqual("Bearer chave-teste", req.get_header("Authorization"))
        self.assertIn(b"ovitrap_group_id=97", req.data)

    def test_envio_do_lote_confirma_cadastro_antes_da_leitura(self):
        contaovos_cadastro.prepare_lot_updates(self.conn, self.lot, [self._update()])
        self.conn.commit()
        ordem = []

        def editador(*_args, **_kwargs):
            ordem.append("cadastro")
            return {"ok": True, "status_code": 200, "message": "ok"}

        def contador(*_args, **_kwargs):
            ordem.append("leitura")
            return {"ok": True, "status_code": 200, "message": "ok"}

        with (
            mock.patch.object(contaovos_cadastro.contaovos_client, "send_ovitrap_edit", side_effect=editador),
            mock.patch.object(contaovos_fila.contaovos_client, "send_counting", side_effect=contador),
        ):
            result = contaovos_fila.send_lot(self.conn, self.lot, "chave")
        self.assertEqual(["cadastro", "leitura"], ordem)
        self.assertEqual(1, result["cadastros_confirmados"])
        self.assertEqual(1, result["enviados"])

    def test_migracao_de_fila_cadastral_e_metadado_interno(self):
        sql = (
            Path(__file__).resolve().parents[1]
            / "migrations/postgresql/0012_contaovos_fila_cadastro_ovitrampas.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE contaovos_fila_cadastro_ovitrampas", sql)
        self.assertIn("CHECK (status IN", sql)
        self.assertNotIn("posteditovitrap", sql.lower())
        self.assertIn("contaovos_fila_cadastro_ovitrampas", schema_metadata.INTERNAL_TABLES)
