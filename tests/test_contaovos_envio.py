import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from app_core import contaovos_client
from app_core import contaovos_envio
from app_core import contaovos_fila
from app_core import db as db_core
from scripts import enviar_contagem_contaovos
from scripts import testar_contaovos_envio_postgresql


class ContaOvosEnvioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "envio.db"
        self.conn = db_core.connect(self.db_path)
        self.conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE ovitrampas_laboratorio_lotes (
                id_lote INTEGER PRIMARY KEY,
                data_movimento TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE ovitrampas_laboratorio_itens (
                id_item INTEGER PRIMARY KEY,
                id_lote INTEGER NOT NULL REFERENCES ovitrampas_laboratorio_lotes(id_lote),
                ovitrampa_id TEXT NOT NULL,
                ovos INTEGER NOT NULL,
                ocorrencia INTEGER
            );
            CREATE TABLE ovitrampas_armadilhas (
                ovitrampa_id TEXT PRIMARY KEY,
                latitude REAL,
                longitude REAL
            );
            CREATE TABLE ovitrampas_ocorrencias_conta_ovos (
                id_contagem TEXT PRIMARY KEY,
                ovitrampa_id TEXT NOT NULL,
                data TEXT,
                ano INTEGER,
                semana INTEGER,
                ovos INTEGER,
                ocorrencia_codigo INTEGER
            );
            CREATE TABLE auditoria_eventos (
                id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
                acao TEXT NOT NULL,
                entidade TEXT,
                entidade_id TEXT,
                usuario_id INTEGER,
                usuario_nome TEXT,
                ip TEXT,
                detalhes_json TEXT NOT NULL DEFAULT '{}',
                criado_em TEXT NOT NULL
            );
            INSERT INTO ovitrampas_laboratorio_lotes
                VALUES (1,'2026-08-02','concluido');
            INSERT INTO ovitrampas_laboratorio_itens
                VALUES (11,1,'97',7,5);
            INSERT INTO ovitrampas_armadilhas
                VALUES ('97',-25.1,-49.2);
            """
        )
        contaovos_fila.ensure_schema_connection(self.conn)
        contaovos_fila.prepare_and_reconcile(
            self.conn, 1, now=datetime(2026, 8, 3, 12, 0, 0)
        )
        self.conn.commit()
        self.queue_id = self.conn.execute(
            "SELECT id_fila FROM contaovos_fila_contagens"
        ).fetchone()[0]
        self.ovitrap_patcher = mock.patch.object(
            contaovos_client,
            "public_ovitraps_page",
            side_effect=lambda **params: (
                [self._remote_ovitrap()] if params["page"] == 1 else []
            ),
        )
        self.ovitrap_patcher.start()

    def tearDown(self):
        self.ovitrap_patcher.stop()
        self.conn.close()
        self.temp.cleanup()

    @staticmethod
    def _remote(remote_id="990", eggs=7, observation=6, latitude=-25.1):
        return {
            "counting_id": remote_id,
            "ovitrap_id": "97",
            "municipality_code": "4100400",
            "state_code": "PR",
            "date": "2026-08-02",
            "year": 2026,
            "week": 31,
            "eggs": eggs,
            "counting_observation_id": observation,
            "latitude": latitude,
            "longitude": -49.2,
        }

    @staticmethod
    def _remote_ovitrap(group_id="97", latitude=-25.1, longitude=-49.2):
        return {
            "ovitrap_group_id": group_id,
            "ovitrap_lat": latitude,
            "ovitrap_lng": longitude,
            "municipality_code": "4100400",
            "state_code": "PR",
        }

    def _fetch_rounds(self, rounds):
        state = {"round": -1}

        def fetcher(key, **params):
            if params["page"] == 1:
                state["round"] += 1
            rows = rounds[min(state["round"], len(rounds) - 1)]
            return rows if params["page"] == 1 else []

        return fetcher

    def test_envio_commita_enviando_antes_do_post_e_confirma_por_get(self):
        observed = {}

        def poster(key, payload, **kwargs):
            check = sqlite3.connect(self.db_path)
            try:
                observed["status"] = check.execute(
                    "SELECT status FROM contaovos_fila_contagens"
                ).fetchone()[0]
                observed["audit"] = check.execute(
                    "SELECT acao FROM auditoria_eventos ORDER BY id_evento"
                ).fetchone()[0]
            finally:
                check.close()
            return {"accepted": True, "status_code": 200}

        result = contaovos_envio.send_one(
            connection=self.conn,
            queue_id=self.queue_id,
            operator_name="Operador Teste",
            key="segredo",
            allow_remote_write=True,
            page_fetcher=self._fetch_rounds([[], [self._remote()]]),
            poster=poster,
            now=datetime(2026, 8, 3, 13, 0, 0),
        )
        self.assertTrue(result["sent"])
        self.assertEqual("enviando", observed["status"])
        self.assertEqual("conta_ovos_envio_contagem_iniciado", observed["audit"])
        row = self.conn.execute(
            "SELECT status, tentativas, id_remoto FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual(("confirmado", 1, "990"), tuple(row))
        audits = self.conn.execute(
            "SELECT acao, usuario_nome FROM auditoria_eventos ORDER BY id_evento"
        ).fetchall()
        self.assertEqual(2, len(audits))
        self.assertEqual("Operador Teste", audits[-1]["usuario_nome"])

    def test_reconciliacao_previa_confirma_sem_post(self):
        poster = mock.Mock()
        result = contaovos_envio.send_one(
            connection=self.conn,
            queue_id=self.queue_id,
            operator_name="Operador",
            key="segredo",
            allow_remote_write=True,
            page_fetcher=self._fetch_rounds([[self._remote("991")]]),
            poster=poster,
        )
        self.assertFalse(result["sent"])
        self.assertEqual("991", result["id_remoto"])
        poster.assert_not_called()

    def test_conflito_previo_vira_erro_sem_post(self):
        poster = mock.Mock()
        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[self._remote(eggs=99)]]),
                poster=poster,
            )
        self.assertEqual("remote_conflict", ctx.exception.kind)
        poster.assert_not_called()
        self.assertEqual(
            "erro",
            self.conn.execute(
                "SELECT status FROM contaovos_fila_contagens"
            ).fetchone()[0],
        )

    def test_falha_de_rede_ausente_no_get_fica_inconclusiva(self):
        def poster(*args, **kwargs):
            raise contaovos_client.ContaOvosError(
                "falha de rede",
                kind="write_network_error",
                outcome_uncertain=True,
            )

        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[], []]),
                poster=poster,
            )
        self.assertTrue(ctx.exception.outcome_uncertain)
        row = self.conn.execute(
            "SELECT status, tentativas, erro_sanitizado FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual("enviando", row["status"])
        self.assertEqual(1, row["tentativas"])
        self.assertIn("Nao reenvie", row["erro_sanitizado"])

    def test_recuperacao_de_inconclusivo_reconcilia_sem_reenviar(self):
        self.conn.execute(
            "UPDATE contaovos_fila_contagens SET status='enviando', tentativas=1"
        )
        self.conn.commit()
        poster = mock.Mock()
        result = contaovos_envio.send_one(
            connection=self.conn,
            queue_id=self.queue_id,
            operator_name="Operador",
            key="segredo",
            allow_remote_write=True,
            page_fetcher=self._fetch_rounds([[self._remote("992")]]),
            poster=poster,
        )
        self.assertFalse(result["sent"])
        poster.assert_not_called()
        self.assertEqual("992", result["id_remoto"])

    def test_inconclusivo_nao_localizado_vira_erro_sem_reenvio(self):
        self.conn.execute("UPDATE contaovos_fila_contagens SET status='enviando'")
        self.conn.commit()
        poster = mock.Mock()
        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[]]),
                poster=poster,
            )
        self.assertEqual("uncertain_not_found", ctx.exception.kind)
        poster.assert_not_called()
        self.assertEqual(
            "erro",
            self.conn.execute(
                "SELECT status FROM contaovos_fila_contagens"
            ).fetchone()[0],
        )

    def test_http_404_so_confirma_se_get_encontrar(self):
        def rejected(*args, **kwargs):
            raise contaovos_client.ContaOvosError(
                "HTTP 404", status_code=404, kind="write_http_error"
            )

        result = contaovos_envio.send_one(
            connection=self.conn,
            queue_id=self.queue_id,
            operator_name="Operador",
            key="segredo",
            allow_remote_write=True,
            page_fetcher=self._fetch_rounds([[], [self._remote("993")]]),
            poster=rejected,
        )
        self.assertEqual("993", result["id_remoto"])
        self.assertEqual("confirmado", result["status"])

    def test_http_400_sem_reconciliacao_vira_erro_humano(self):
        def rejected(*args, **kwargs):
            raise contaovos_client.ContaOvosError(
                "HTTP 400", status_code=400, kind="write_http_error"
            )

        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[], []]),
                poster=rejected,
            )
        self.assertEqual("write_rejected", ctx.exception.kind)
        self.assertFalse(ctx.exception.outcome_uncertain)
        self.assertEqual(
            "erro",
            self.conn.execute(
                "SELECT status FROM contaovos_fila_contagens"
            ).fetchone()[0],
        )

    def test_sucesso_sem_reconciliacao_fica_inconclusivo(self):
        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[], []]),
                poster=lambda *args, **kwargs: {"accepted": True},
            )
        self.assertTrue(ctx.exception.outcome_uncertain)
        self.assertEqual(
            "enviando",
            self.conn.execute(
                "SELECT status FROM contaovos_fila_contagens"
            ).fetchone()[0],
        )

    def test_payload_alterado_bloqueia_antes_da_rede(self):
        self.conn.execute(
            "UPDATE ovitrampas_laboratorio_itens SET ovos=8 WHERE id_item=11"
        )
        self.conn.commit()
        fetcher = mock.Mock()
        poster = mock.Mock()
        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=fetcher,
                poster=poster,
            )
        self.assertEqual("payload_changed", ctx.exception.kind)
        fetcher.assert_not_called()
        poster.assert_not_called()

    def test_coordenada_remota_divergente_exige_confirmacao_antes_do_post(self):
        poster = mock.Mock()
        fetcher = lambda **params: (
            [self._remote_ovitrap(latitude=-25.2)] if params["page"] == 1 else []
        )
        with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
            contaovos_envio.send_one(
                connection=self.conn,
                queue_id=self.queue_id,
                operator_name="Operador",
                key="segredo",
                allow_remote_write=True,
                page_fetcher=self._fetch_rounds([[]]),
                ovitrap_fetcher=fetcher,
                poster=poster,
            )
        self.assertEqual(
            "coordinate_change_confirmation_required", ctx.exception.kind
        )
        self.assertIn("MOVER OVITRAMPA", ctx.exception.required_confirmation)
        poster.assert_not_called()
        row = self.conn.execute(
            "SELECT status, tentativas FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual(("pendente", 0), tuple(row))

    def test_mudanca_de_coordenada_autorizada_fica_na_auditoria(self):
        fetcher = lambda **params: (
            [self._remote_ovitrap(latitude=-25.2)] if params["page"] == 1 else []
        )
        position = {
            "remote_lat": -25.2,
            "remote_lng": -49.2,
            "local_lat": -25.1,
            "local_lng": -49.2,
        }
        phrase = contaovos_envio._coordinate_confirmation(self.queue_id, position)
        result = contaovos_envio.send_one(
            connection=self.conn,
            queue_id=self.queue_id,
            operator_name="Operador",
            key="segredo",
            allow_remote_write=True,
            coordinate_authorization=phrase,
            page_fetcher=self._fetch_rounds([[], [self._remote()]]),
            ovitrap_fetcher=fetcher,
            poster=lambda *args, **kwargs: {"accepted": True},
        )
        self.assertTrue(result["sent"])
        details = json.loads(
            self.conn.execute(
                "SELECT detalhes_json FROM auditoria_eventos "
                "WHERE acao='conta_ovos_envio_contagem_iniciado'"
            ).fetchone()[0]
        )
        self.assertTrue(details["mudanca_coordenadas"]["autorizada"])
        self.assertEqual(-25.2, details["mudanca_coordenadas"]["latitude_remota"])

    def test_ovitrampa_ausente_ou_id_exato_divergente_bloqueia_criacao(self):
        cases = (
            (lambda **params: [], "remote_ovitrap_not_found"),
            (
                lambda **params: (
                    [self._remote_ovitrap(group_id="097")]
                    if params["page"] == 1
                    else []
                ),
                "remote_ovitrap_id_mismatch",
            ),
        )
        for fetcher, expected_kind in cases:
            with self.subTest(expected_kind=expected_kind):
                with self.assertRaises(contaovos_envio.ContaOvosSendError) as ctx:
                    contaovos_envio.send_one(
                        connection=self.conn,
                        queue_id=self.queue_id,
                        operator_name="Operador",
                        key="segredo",
                        allow_remote_write=True,
                        page_fetcher=self._fetch_rounds([[]]),
                        ovitrap_fetcher=fetcher,
                        poster=mock.Mock(),
                    )
                self.assertEqual(expected_kind, ctx.exception.kind)

    def test_script_recusa_sem_confirmacoes_antes_de_ler_chave(self):
        with (
            mock.patch.object(
                enviar_contagem_contaovos.contaovos_credencial, "read_key"
            ) as read_key,
            mock.patch("builtins.print"),
        ):
            result = enviar_contagem_contaovos.main(
                ["--id-fila", str(self.queue_id), "--operador", "Teste"]
            )
        self.assertEqual(2, result)
        read_key.assert_not_called()

    def test_modo_interativo_nao_interpela_entrada_no_batch(self):
        root = Path(__file__).resolve().parents[1]
        batch = (root / "enviar_contagem_contaovos.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("--interativo", batch)
        self.assertNotIn("set /p", batch.lower())
        self.assertNotIn("%OPERADOR%", batch)

    def test_modo_interativo_cancela_antes_de_ler_chave(self):
        with (
            mock.patch.object(
                enviar_contagem_contaovos, "_list", return_value=1
            ),
            mock.patch("builtins.input", side_effect=["1", "Operador", "ERRADO"]),
            mock.patch.object(
                enviar_contagem_contaovos.contaovos_credencial, "read_key"
            ) as read_key,
            mock.patch("builtins.print"),
        ):
            result = enviar_contagem_contaovos.main(["--interativo"])
        self.assertEqual(2, result)
        read_key.assert_not_called()

    def test_modo_interativo_para_quando_fila_esta_vazia(self):
        with (
            mock.patch.object(enviar_contagem_contaovos, "_list", return_value=0),
            mock.patch("builtins.input") as user_input,
            mock.patch.object(
                enviar_contagem_contaovos.contaovos_credencial, "read_key"
            ) as read_key,
            mock.patch("builtins.print"),
        ):
            result = enviar_contagem_contaovos.main(["--interativo"])
        self.assertEqual(0, result)
        user_input.assert_not_called()
        read_key.assert_not_called()

    def test_modo_interativo_repete_preflight_com_autorizacao_de_coordenada(self):
        phrase = "MOVER OVITRAMPA DA FILA 1 DE -25.200000,-49.200000 PARA -25.100000,-49.200000"
        coordinate_error = contaovos_envio.ContaOvosSendError(
            "coordenadas divergentes",
            kind="coordinate_change_confirmation_required",
            required_confirmation=phrase,
            details={
                "remote_lat": -25.2,
                "remote_lng": -49.2,
                "local_lat": -25.1,
                "local_lng": -49.2,
            },
        )
        args = enviar_contagem_contaovos._parser().parse_args(
            [
                "--interativo",
                "--id-fila",
                "1",
                "--operador",
                "Operador",
            ]
        )
        with (
            mock.patch.object(
                enviar_contagem_contaovos.contaovos_envio,
                "send_one",
                side_effect=[
                    coordinate_error,
                    {"ok": True, "sent": True, "id_remoto": "999"},
                ],
            ) as send,
            mock.patch("builtins.input", return_value=phrase),
            mock.patch("builtins.print"),
        ):
            result = enviar_contagem_contaovos._send(args, "segredo")
        self.assertTrue(result["sent"])
        self.assertEqual(2, send.call_count)
        self.assertEqual(
            phrase, send.call_args_list[1].kwargs["coordinate_authorization"]
        )

    def test_ensaio_postgresql_recusa_banco_oficial(self):
        with mock.patch.object(
            testar_contaovos_envio_postgresql.postgresql, "connect"
        ) as connect:
            result = testar_contaovos_envio_postgresql.main(
                ["--database", "endemias"]
            )
        self.assertEqual(2, result)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
