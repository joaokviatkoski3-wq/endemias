import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from jinja2 import Environment, FileSystemLoader

from app_core import backup as backup_core
from app_core import backup_health
from app_core import backup_tasks
from app_core import db as db_core
from app_core import diagnostico
from blueprints import admin


ROOT = Path(__file__).resolve().parents[1]

CONTEUDO_DUMP = b"PGDMP conteudo de teste"


def _criar_dump(destino, database="endemias", nome="endemias_20260803_020000.dump"):
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / nome
    arquivo.write_bytes(CONTEUDO_DUMP)
    arquivo.with_suffix(".dump.json").write_text(
        json.dumps({
            "backend": "postgresql",
            "validado": True,
            "integridade": "catalogo validado",
            "sha256": backup_core.calcular_sha256(arquivo),
            "origem": {"database": database},
        }),
        encoding="utf-8",
    )
    return arquivo


def _criar_zip_completo(
    destino,
    database="endemias",
    nome="endemias_completo_20260803_030000.zip",
    corromper=False,
    backend="postgresql",
):
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / nome
    interno = b"PGDMP dump interno"
    digest = hashlib.sha256(interno).hexdigest()
    manifesto = {
        "tipo": "backup_completo_endemias",
        "backend_banco": backend,
        "banco_origem": database,
        "integridade_banco": "catalogo validado",
        "incluidos": [{
            "destino_zip": "banco/endemias_20260803.dump",
            "sha256": "0" * 64 if corromper else digest,
        }],
    }
    with zipfile.ZipFile(arquivo, "w") as zf:
        zf.writestr("banco/endemias_20260803.dump", interno)
        zf.writestr("manifesto_backup.json", json.dumps(manifesto))
    return arquivo


def _envelhecer(arquivo, horas):
    momento = (datetime.now() - timedelta(hours=horas)).timestamp()
    import os

    os.utime(arquivo, (momento, momento))


def _tarefa_bruta(nome, **campos):
    base = {
        "nome": nome,
        "encontrada": True,
        "estado": "Ready",
        "ultima_execucao": "",
        "proxima_execucao": "",
        "resultado": 0,
        "erro": "",
        "erro_id": "",
        "privilegiado": True,
    }
    base.update(campos)
    return base


class SaudeDosArtefatosTests(unittest.TestCase):
    def setUp(self):
        backup_tasks.limpar_cache()

    def test_backups_validos_e_recentes_ficam_ok(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_dump(raiz / "banco")
            _criar_zip_completo(raiz / "completos")

            resultado = backup_health.avaliar(
                raiz / "banco",
                raiz / "completos",
                database="endemias",
                modo=backup_health.MODO_RAPIDO,
                tarefas=[],
            )

        self.assertEqual(resultado["nivel"], backup_health.NIVEL_OK)
        self.assertEqual(resultado["dump"]["nivel"], backup_health.NIVEL_OK)
        self.assertEqual(resultado["completo"]["nivel"], backup_health.NIVEL_OK)

    def test_dump_ausente_e_reportado_como_erro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_zip_completo(raiz / "completos")

            resultado = backup_health.avaliar(
                raiz / "banco",
                raiz / "completos",
                tarefas=[],
            )

        self.assertEqual(resultado["dump"]["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("Nenhum dump", resultado["dump"]["detalhe"])
        self.assertEqual(resultado["nivel"], backup_health.NIVEL_ERRO)

    def test_dump_antigo_e_reportado_como_erro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            arquivo = _criar_dump(raiz / "banco")
            _envelhecer(arquivo, horas=80)

            bloco = backup_health.avaliar_dump(raiz / "banco", max_horas=36)

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("horas", bloco["detalhe"])

    def test_dump_de_outro_banco_e_recusado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_dump(raiz / "banco", database="endemias_teste")

            bloco = backup_health.avaliar_dump(raiz / "banco", database="endemias")

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("outro banco", bloco["detalhe"])

    def test_zip_com_dump_interno_corrompido_e_recusado_no_modo_completo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_zip_completo(raiz / "completos", corromper=True)

            bloco = backup_health.avaliar_backup_completo(
                raiz / "completos",
                modo=backup_health.MODO_COMPLETO,
            )

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("diverge", bloco["detalhe"])

    def test_zip_ausente_e_reportado_como_erro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bloco = backup_health.avaliar_backup_completo(Path(tmpdir))

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("Nenhum backup completo", bloco["detalhe"])

    def test_pasta_de_completos_sem_permissao_nao_vira_alarme(self):
        with (
            mock.patch.object(
                backup_health.backup_completo,
                "listar_backups_completos",
                return_value=[],
            ),
            mock.patch.object(
                backup_health.os, "scandir", side_effect=PermissionError("negado")
            ),
            mock.patch.object(backup_health.Path, "is_dir", return_value=True),
        ):
            bloco = backup_health.avaliar_backup_completo("pasta-protegida")

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_DESCONHECIDO)
        self.assertIn("permissao", bloco["detalhe"].lower())

    def test_zip_antigo_e_reportado_como_erro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            arquivo = _criar_zip_completo(raiz / "completos")
            _envelhecer(arquivo, horas=24 * 20)

            bloco = backup_health.avaliar_backup_completo(
                raiz / "completos",
                max_dias=8,
            )

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("dias", bloco["detalhe"])

    def test_zip_postgresql_mais_recente_de_outro_banco_e_recusado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir) / "completos"
            correto = _criar_zip_completo(
                raiz,
                database="endemias",
                nome="endemias_completo_correto.zip",
            )
            _envelhecer(correto, horas=1)
            _criar_zip_completo(
                raiz,
                database="endemias_teste",
                nome="endemias_completo_errado.zip",
            )

            bloco = backup_health.avaliar_backup_completo(
                raiz,
                database="endemias",
            )

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("outro banco", bloco["detalhe"])

    def test_zip_sqlite_legado_mais_recente_e_ignorado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir) / "completos"
            correto = _criar_zip_completo(
                raiz,
                database="endemias",
                nome="endemias_completo_postgresql.zip",
            )
            _envelhecer(correto, horas=1)
            _criar_zip_completo(
                raiz,
                database="endemias.db",
                nome="endemias_completo_sqlite_legado.zip",
                backend="sqlite",
            )

            bloco = backup_health.avaliar_backup_completo(
                raiz,
                database="endemias",
            )

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_OK)
        self.assertEqual(bloco["nome"], correto.name)

    def test_acesso_negado_nao_vira_alarme_de_backup(self):
        with mock.patch.object(
            backup_health.postgresql_backup,
            "listar_backups",
            side_effect=PermissionError("acesso negado"),
        ):
            bloco = backup_health.avaliar_dump("qualquer")

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_DESCONHECIDO)
        self.assertIn("permissao", bloco["detalhe"].lower())

    def test_pasta_sem_permissao_de_listagem_nao_vira_alarme(self):
        # Path.glob engole PermissionError e devolve lista vazia, entao a pasta
        # protegida por ACL do SYSTEM chegava aqui como "nenhum dump".
        with (
            mock.patch.object(
                backup_health.postgresql_backup, "listar_backups", return_value=[]
            ),
            mock.patch.object(
                backup_health.os, "scandir", side_effect=PermissionError("negado")
            ),
            mock.patch.object(backup_health.Path, "is_dir", return_value=True),
        ):
            bloco = backup_health.avaliar_dump("pasta-protegida")

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_DESCONHECIDO)
        self.assertIn("permissao", bloco["detalhe"].lower())

    def test_pasta_legivel_e_vazia_continua_sendo_erro_real(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bloco = backup_health.avaliar_dump(tmpdir)

        self.assertEqual(bloco["nivel"], backup_health.NIVEL_ERRO)
        self.assertIn("Nenhum dump", bloco["detalhe"])

    def test_mensagem_de_erro_nao_expoe_segredos(self):
        with mock.patch.object(
            backup_health.postgresql_backup,
            "listar_backups",
            side_effect=RuntimeError("falhou password=SegredoDoSetor host=x"),
        ):
            bloco = backup_health.avaliar_dump("qualquer")

        self.assertNotIn("SegredoDoSetor", bloco["detalhe"])
        self.assertIn("[oculto]", bloco["detalhe"])


class ModoRapidoEComplretoTests(unittest.TestCase):
    def setUp(self):
        backup_tasks.limpar_cache()

    def test_modo_rapido_nao_recalcula_hash_nem_chama_pg_restore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_dump(raiz / "banco")
            _criar_zip_completo(raiz / "completos")

            with (
                mock.patch.object(
                    backup_health.backup_core,
                    "calcular_sha256",
                ) as sha,
                mock.patch.object(
                    backup_health.postgresql_backup,
                    "validar_backup",
                ) as validar,
                mock.patch.object(
                    zipfile.ZipFile,
                    "testzip",
                    autospec=True,
                ) as testzip,
            ):
                resultado = backup_health.avaliar(
                    raiz / "banco",
                    raiz / "completos",
                    modo=backup_health.MODO_RAPIDO,
                    tarefas=[],
                )

        self.assertEqual(resultado["nivel"], backup_health.NIVEL_OK)
        sha.assert_not_called()
        validar.assert_not_called()
        testzip.assert_not_called()

    def test_modo_completo_valida_hash_catalogo_e_conteudo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _criar_dump(raiz / "banco")
            _criar_zip_completo(raiz / "completos")

            with (
                mock.patch.object(
                    backup_health.postgresql_backup,
                    "validar_backup",
                    return_value=(True, "catalogo validado"),
                ) as validar,
                mock.patch.object(
                    zipfile.ZipFile,
                    "testzip",
                    autospec=True,
                    return_value=None,
                ) as testzip,
            ):
                resultado = backup_health.avaliar(
                    raiz / "banco",
                    raiz / "completos",
                    modo=backup_health.MODO_COMPLETO,
                    tarefas=[],
                )

        self.assertEqual(resultado["nivel"], backup_health.NIVEL_OK)
        validar.assert_called_once()
        testzip.assert_called_once()
        self.assertIn("SHA-256", resultado["dump"]["integridade"])


class TarefasAgendadasTests(unittest.TestCase):
    def setUp(self):
        backup_tasks.limpar_cache()

    def test_tarefa_bem_sucedida(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            ultima_execucao="2026-08-03T02:00:00",
            proxima_execucao="2026-08-04T02:00:00",
            resultado=0,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_OK)
        self.assertEqual(tarefas[0]["ultima_execucao"], "2026-08-03T02:00:00")
        self.assertEqual(tarefas[0]["proxima_execucao"], "2026-08-04T02:00:00")

    def test_tarefa_nunca_executada(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            ultima_execucao="1899-12-30T00:00:00",
            resultado=backup_tasks.RESULTADO_NUNCA_EXECUTADA,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_AVISO)
        self.assertIsNone(tarefas[0]["ultima_execucao"])
        self.assertIn("ainda nao rodou", tarefas[0]["detalhe"])

    def test_tarefa_com_falha(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_BACKUP_COMPLETO,
            ultima_execucao="2026-08-03T03:00:00",
            resultado=1,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_BACKUP_COMPLETO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_ERRO)
        self.assertIn("1", tarefas[0]["detalhe"])

    def test_tarefa_sem_mais_execucoes_gera_aviso(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_BACKUP_COMPLETO,
            ultima_execucao="2026-08-03T03:00:00",
            resultado=backup_tasks.RESULTADO_SEM_MAIS_EXECUCOES,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_BACKUP_COMPLETO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_AVISO)
        self.assertIn("sem proximas", tarefas[0]["situacao"].lower())

    def test_tarefa_concluida_sem_proxima_execucao_gera_aviso(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            ultima_execucao="2026-08-03T02:00:00",
            proxima_execucao="",
            resultado=0,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_AVISO)
        self.assertIn("sem proxima", tarefas[0]["situacao"].lower())

    def test_tarefa_em_execucao_sem_proxima_data_nao_gera_aviso(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            estado="Running",
            ultima_execucao="2026-08-03T02:00:00",
            proxima_execucao="",
            # Durante a execucao, o Agendador pode conservar o resultado
            # anterior ate o processo terminar.
            resultado=0,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_OK)
        self.assertEqual(tarefas[0]["situacao"], "Em execucao")

    def test_tarefa_desabilitada_gera_aviso(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            estado="Disabled",
            resultado=0,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_AVISO)
        self.assertIn("desabilitada", tarefas[0]["situacao"].lower())

    def test_tarefa_ausente_com_privilegio_vira_aviso(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            encontrada=False,
            erro_id="CmdletizationQuery_NotFound_TaskName,Get-ScheduledTask",
            privilegiado=True,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_AVISO)
        self.assertIn("nao encontrada", tarefas[0]["situacao"].lower())

    def test_tarefa_ausente_sem_privilegio_fica_indeterminada(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            encontrada=False,
            erro_id="CmdletizationQuery_NotFound_TaskName,Get-ScheduledTask",
            privilegiado=False,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_DESCONHECIDO)
        self.assertIn("privilegio", tarefas[0]["detalhe"])

    def test_acesso_negado_fica_indeterminado(self):
        brutos = [_tarefa_bruta(
            backup_tasks.TAREFA_DUMP_DIARIO,
            encontrada=False,
            erro_id="AccessDenied,Get-ScheduledTask",
            erro="Acesso negado",
            privilegiado=True,
        )]
        tarefas = backup_tasks.consultar_tarefas(
            nomes=[backup_tasks.TAREFA_DUMP_DIARIO],
            consultar=lambda _: brutos,
        )

        self.assertEqual(tarefas[0]["nivel"], backup_tasks.NIVEL_DESCONHECIDO)
        self.assertIn("permissao", tarefas[0]["situacao"].lower())

    def test_ambiente_nao_windows_nao_gera_alarme(self):
        with mock.patch.object(backup_tasks, "_e_windows", return_value=False):
            tarefas = backup_tasks.consultar_tarefas()

        self.assertEqual(len(tarefas), len(backup_tasks.TAREFAS_BACKUP))
        for tarefa in tarefas:
            self.assertEqual(tarefa["nivel"], backup_tasks.NIVEL_DESCONHECIDO)
            self.assertIn("Windows", tarefa["detalhe"])

    def test_timeout_da_consulta_nao_gera_alarme(self):
        def estourar(_alvos):
            raise backup_tasks.TarefasIndisponiveis(
                "A consulta ao Agendador excedeu o tempo limite."
            )

        tarefas = backup_tasks.consultar_tarefas(consultar=estourar)

        for tarefa in tarefas:
            self.assertEqual(tarefa["nivel"], backup_tasks.NIVEL_DESCONHECIDO)
            self.assertIn("tempo limite", tarefa["detalhe"])

    def test_consulta_usa_cache_curto_quando_solicitado(self):
        chamadas = []

        def contar(alvos):
            chamadas.append(alvos)
            return [_tarefa_bruta(backup_tasks.TAREFA_DUMP_DIARIO)]

        nomes = [backup_tasks.TAREFA_DUMP_DIARIO]
        backup_tasks.consultar_tarefas(
            nomes=nomes, consultar=contar, cache_segundos=60
        )
        backup_tasks.consultar_tarefas(
            nomes=nomes, consultar=contar, cache_segundos=60
        )

        self.assertEqual(len(chamadas), 1)

    def test_nome_com_quebra_de_linha_e_rejeitado(self):
        with self.assertRaises(ValueError):
            backup_tasks.consultar_tarefas(nomes=["Tarefa\nmaliciosa"])


class DiagnosticoIntegradoTests(unittest.TestCase):
    def setUp(self):
        backup_tasks.limpar_cache()

    def _conn(self, backend):
        conn = mock.Mock()
        conn.backend = backend
        conn.execute.return_value = mock.Mock(
            fetchone=mock.Mock(return_value=("endemias", "18.0")),
            fetchall=mock.Mock(return_value=[]),
            __iter__=mock.Mock(return_value=iter([])),
        )
        return conn

    def test_diagnostico_postgresql_publica_saude_dos_backups(self):
        saude = {
            "backend": "postgresql",
            "modo": "rapido",
            "nivel": backup_health.NIVEL_AVISO,
            "dump": {
                "nivel": backup_health.NIVEL_OK,
                "titulo": "Dump diario disponivel",
                "detalhe": "recente",
                "nome": "endemias.dump",
            },
            "completo": {
                "nivel": backup_health.NIVEL_ERRO,
                "titulo": "Backup completo com problema",
                "detalhe": "Nenhum backup completo PostgreSQL foi encontrado.",
            },
            "tarefas": [{
                "nome": backup_tasks.TAREFA_DUMP_DIARIO,
                "nivel": backup_health.NIVEL_DESCONHECIDO,
                "situacao": "Nao foi possivel confirmar",
                "detalhe": "sem privilegio",
                "estado": "",
                "ultima_execucao": None,
                "proxima_execucao": None,
                "resultado": None,
            }],
        }
        itens = []
        diagnostico._check_saude_backups(itens, saude)

        niveis = {item["titulo"]: item["nivel"] for item in itens}
        self.assertEqual(niveis["Dump diario disponivel"], "ok")
        self.assertEqual(niveis["Backup completo com problema"], "erro")
        # Estado indeterminado entra como informativo e nao contamina o resumo.
        indeterminado = [i for i in itens if i["titulo"].startswith("Endemias")]
        self.assertEqual(indeterminado[0]["nivel"], "info")

    def test_diagnostico_sqlite_preserva_verificacao_antiga(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            itens = []
            diagnostico._check_backups(tmpdir, itens, "sqlite")

        self.assertEqual(itens[0]["titulo"], "Nenhum backup encontrado.")

    def test_gerar_sqlite_nao_avalia_saude_postgresql(self):
        conn = self._conn("sqlite")
        with (
            mock.patch.object(diagnostico, "_tables", return_value=set()),
            mock.patch.object(diagnostico, "_check_integridade"),
            mock.patch.object(diagnostico, "_check_vinculos_principais"),
            mock.patch.object(diagnostico, "_check_dados_operacionais"),
            mock.patch.object(diagnostico, "_check_duplicidades_textuais"),
            mock.patch.object(diagnostico.backup_health, "avaliar") as avaliar,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            resultado = diagnostico.gerar(conn, backup_dir=tmpdir)

        avaliar.assert_not_called()
        self.assertNotIn("saude_backups", resultado)


class CentralDoSistemaTests(unittest.TestCase):
    def setUp(self):
        backup_tasks.limpar_cache()

    def test_template_da_central_compila_e_traz_o_painel(self):
        env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
        # Compilar detecta erro de sintaxe Jinja no painel novo.
        env.get_template("admin_sistema.html")

        fonte = (ROOT / "templates" / "admin_sistema.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Saude dos backups automaticos", fonte)
        self.assertIn("{% if postgresql_operations and saude_backups %}", fonte)
        self.assertIn("saude_backups.tarefas", fonte)

    def _preparar_central(self, backend, saude_esperada=None):
        import app as endemias_app

        alvo = (
            db_core.DatabaseTarget("postgresql", "endemias")
            if backend == "postgresql"
            else db_core.DatabaseTarget("sqlite", "endemias.db")
        )
        contexto = {}

        def capturar(_template, **kwargs):
            contexto.update(kwargs)
            return "ok"

        patches = [
            mock.patch.object(admin, "render_template", side_effect=capturar),
            mock.patch.object(admin, "_db_target", return_value=alvo),
            mock.patch.object(admin, "_db_status", return_value={}),
            mock.patch.object(admin, "_contagens_sistema", return_value={}),
            mock.patch.object(admin, "_listar_backups_ativos", return_value=[]),
            mock.patch.object(
                admin.backup_completo_core,
                "listar_backups_completos",
                return_value=[],
            ),
            mock.patch.object(
                admin.import_history,
                "listar_importacoes_recentes",
                return_value=[],
            ),
            mock.patch.object(admin.audit, "listar_eventos", return_value=[]),
            mock.patch.object(admin.bh, "get_db", return_value=mock.Mock()),
            mock.patch.object(
                admin.diagnostico_core,
                "gerar",
                return_value={"resumo": {}, "itens": []},
            ),
        ]
        if saude_esperada is not None:
            patches.append(
                mock.patch.object(
                    admin.backup_health,
                    "avaliar",
                    return_value=saude_esperada,
                )
            )
        return endemias_app, contexto, patches

    def test_central_postgresql_entrega_saude_ao_template(self):
        saude = {
            "backend": "postgresql",
            "modo": "rapido",
            "nivel": backup_health.NIVEL_OK,
            "dump": {"nivel": "ok", "titulo": "Dump diario disponivel"},
            "completo": {"nivel": "ok", "titulo": "Backup completo disponivel"},
            "tarefas": [],
        }
        endemias_app, contexto, patches = self._preparar_central(
            "postgresql",
            saude,
        )
        flask_app = endemias_app.create_app({"TESTING": True})
        with flask_app.test_request_context("/admin/sistema"):
            with self._aplicar(patches):
                vista = admin.admin_sistema
                while hasattr(vista, "__wrapped__"):
                    vista = vista.__wrapped__
                vista()

        self.assertTrue(contexto["postgresql_operations"])
        self.assertEqual(contexto["saude_backups"], saude)

    def test_central_sqlite_nao_mostra_painel_postgresql(self):
        endemias_app, contexto, patches = self._preparar_central("sqlite")
        flask_app = endemias_app.create_app({"TESTING": True})
        with flask_app.test_request_context("/admin/sistema"):
            with self._aplicar(patches):
                vista = admin.admin_sistema
                while hasattr(vista, "__wrapped__"):
                    vista = vista.__wrapped__
                vista()

        self.assertFalse(contexto["postgresql_operations"])
        self.assertIsNone(contexto["saude_backups"])

    def _aplicar(self, patches):
        class _Conjunto:
            def __enter__(self_nao_usado):
                for patch in patches:
                    patch.start()
                return self_nao_usado

            def __exit__(self_nao_usado, *args):
                for patch in reversed(patches):
                    patch.stop()
                return False

        return _Conjunto()

    def test_falha_inesperada_na_avaliacao_nao_derruba_a_central(self):
        flask_app = mock.MagicMock()
        with mock.patch.object(
            admin,
            "backup_health",
            wraps=backup_health,
        ) as saude_mock:
            saude_mock.avaliar.side_effect = RuntimeError("falha interna")
            saude_mock.NIVEL_DESCONHECIDO = backup_health.NIVEL_DESCONHECIDO
            with mock.patch.object(admin, "current_app", flask_app):
                resultado = admin._saude_backups(
                    db_core.DatabaseTarget("postgresql", "endemias"),
                    "banco",
                    "completos",
                    backup_health.MODO_RAPIDO,
                )

        self.assertEqual(resultado["nivel"], backup_health.NIVEL_DESCONHECIDO)
        self.assertEqual(resultado["tarefas"], [])


if __name__ == "__main__":
    unittest.main()
