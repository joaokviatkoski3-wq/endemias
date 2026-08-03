"""Consulta somente leitura das tarefas de backup no Agendador do Windows.

Este modulo nunca cria, altera, inicia ou remove tarefas. Ele apenas le o
estado publicado pelo Agendador para alimentar a Central do Sistema e o
diagnostico administrativo.
"""

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime


TAREFA_DUMP_DIARIO = "Endemias - Backup PostgreSQL Diario"
TAREFA_BACKUP_COMPLETO = "Endemias - Backup Completo PostgreSQL"
TAREFAS_BACKUP = (TAREFA_DUMP_DIARIO, TAREFA_BACKUP_COMPLETO)

TIMEOUT_PADRAO_SEGUNDOS = 20

NIVEL_OK = "ok"
NIVEL_AVISO = "aviso"
NIVEL_ERRO = "erro"
NIVEL_DESCONHECIDO = "desconhecido"

# Codigos SCHED_S_* documentados pelo Agendador de Tarefas do Windows.
RESULTADO_SUCESSO = 0
RESULTADO_PRONTA = 267008           # 0x00041300 SCHED_S_TASK_READY
RESULTADO_EM_EXECUCAO = 267009      # 0x00041301 SCHED_S_TASK_RUNNING
RESULTADO_DESABILITADA = 267010     # 0x00041302 SCHED_S_TASK_DISABLED
RESULTADO_NUNCA_EXECUTADA = 267011  # 0x00041303 SCHED_S_TASK_HAS_NOT_RUN
RESULTADO_SEM_MAIS_EXECUCOES = 267012  # 0x00041304 SCHED_S_TASK_NO_MORE_RUNS

_RESULTADOS_NEUTROS = {
    RESULTADO_PRONTA,
}

_VARIAVEL_TAREFAS = "ENDEMIAS_TAREFAS_CONSULTA_JSON"

CACHE_PADRAO_SEGUNDOS = 60
_cache_lock = threading.Lock()
_cache = {}

# Os nomes das tarefas viajam por variavel de ambiente, uma por linha, para que
# nada seja interpolado na linha de comando do PowerShell. A separacao por linha
# e segura porque nomes com quebra de linha sao rejeitados antes da consulta.
_CONSULTA_POWERSHELL = """
$ErrorActionPreference = 'Stop'
$nomes = @($env:{variavel} -split "`n" | ForEach-Object {{ $_.Trim() }} | Where-Object {{ $_ }})
$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidade)
$privilegiado = $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
$saida = @()
foreach ($nome in $nomes) {{
    $item = [ordered]@{{
        nome = [string]$nome
        encontrada = $false
        estado = ''
        ultima_execucao = ''
        proxima_execucao = ''
        resultado = $null
        erro = ''
        erro_id = ''
        privilegiado = [bool]$privilegiado
    }}
    try {{
        $tarefa = Get-ScheduledTask -TaskName $nome -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $nome -ErrorAction Stop
        $item.encontrada = $true
        $item.estado = [string]$tarefa.State
        if ($info.LastRunTime) {{ $item.ultima_execucao = $info.LastRunTime.ToString('o') }}
        if ($info.NextRunTime) {{ $item.proxima_execucao = $info.NextRunTime.ToString('o') }}
        $item.resultado = [int]$info.LastTaskResult
    }} catch {{
        $item.erro = [string]$_.Exception.Message
        $item.erro_id = [string]$_.FullyQualifiedErrorId
    }}
    $saida += [pscustomobject]$item
}}
ConvertTo-Json -InputObject @($saida) -Depth 4 -Compress
""".strip()


class TarefasIndisponiveis(RuntimeError):
    """O Agendador nao pode ser consultado neste ambiente."""


def _e_windows():
    return os.name == "nt"


def _localizar_powershell():
    for nome in ("powershell.exe", "pwsh.exe"):
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return None


def _validar_nomes(nomes):
    validos = []
    for nome in nomes or ():
        texto = str(nome or "").strip()
        if not texto:
            continue
        if any(caractere in texto for caractere in ("\r", "\n", "\x00")):
            raise ValueError("Nome de tarefa invalido para consulta.")
        validos.append(texto)
    if not validos:
        raise ValueError("Informe ao menos uma tarefa para consultar.")
    return validos


def _executar_consulta(nomes, timeout, executavel):
    ambiente = dict(os.environ)
    ambiente[_VARIAVEL_TAREFAS] = "\n".join(nomes)
    comando = [
        executavel,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _CONSULTA_POWERSHELL.format(variavel=_VARIAVEL_TAREFAS),
    ]
    try:
        processo = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=ambiente,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TarefasIndisponiveis(
            "A consulta ao Agendador excedeu o tempo limite."
        ) from exc
    except OSError as exc:
        raise TarefasIndisponiveis(
            "Nao foi possivel iniciar a consulta ao Agendador."
        ) from exc

    saida = (processo.stdout or "").strip()
    if processo.returncode != 0 and not saida:
        detalhe = (processo.stderr or "").strip()
        raise TarefasIndisponiveis(
            "A consulta ao Agendador falhou."
            + (f" {detalhe[:300]}" if detalhe else "")
        )
    if not saida:
        raise TarefasIndisponiveis("O Agendador nao retornou dados.")
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError as exc:
        raise TarefasIndisponiveis(
            "A resposta do Agendador nao pode ser interpretada."
        ) from exc
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        raise TarefasIndisponiveis("A resposta do Agendador veio em formato inesperado.")
    return dados


def _data_valida(texto):
    texto = str(texto or "").strip()
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    # O Agendador usa 1899-12-30 para tarefas que nunca executaram.
    if momento.year < 2000:
        return None
    return momento.replace(tzinfo=None).isoformat(timespec="seconds")


def _classificar_erro(erro_id, mensagem):
    referencia = f"{erro_id or ''} {mensagem or ''}".lower()
    if "notfound" in referencia or "not found" in referencia:
        return "nao_encontrada"
    if (
        "accessdenied" in referencia
        or "unauthorized" in referencia
        or "denied" in referencia
        or "negado" in referencia
    ):
        return "acesso_negado"
    return "indeterminado"


def _classificar_tarefa(bruto):
    nome = str(bruto.get("nome") or "").strip()
    tarefa = {
        "nome": nome,
        "encontrada": bool(bruto.get("encontrada")),
        "estado": str(bruto.get("estado") or "").strip(),
        "ultima_execucao": _data_valida(bruto.get("ultima_execucao")),
        "proxima_execucao": _data_valida(bruto.get("proxima_execucao")),
        "resultado": None,
        "nivel": NIVEL_DESCONHECIDO,
        "situacao": "",
        "detalhe": "",
    }

    if not tarefa["encontrada"]:
        categoria = _classificar_erro(bruto.get("erro_id"), bruto.get("erro"))
        privilegiado = bool(bruto.get("privilegiado"))
        if categoria == "nao_encontrada" and not privilegiado:
            # Uma conta comum recebe "nao encontrada" tanto para tarefa
            # inexistente quanto para tarefa de SYSTEM que ela nao enxerga.
            # Sem privilegio nao da para distinguir, entao nao se acusa falha.
            tarefa["situacao"] = "Nao foi possivel confirmar"
            tarefa["detalhe"] = (
                "A conta atual nao tem privilegio para enxergar tarefas do "
                "SYSTEM. Execute o diagnostico pelo servico para confirmar."
            )
        elif categoria == "nao_encontrada":
            tarefa["nivel"] = NIVEL_AVISO
            tarefa["situacao"] = "Tarefa nao encontrada"
            tarefa["detalhe"] = (
                "O Agendador nao possui esta tarefa. Os backups automaticos "
                "podem nao estar instalados."
            )
        elif categoria == "acesso_negado":
            tarefa["situacao"] = "Sem permissao para consultar"
            tarefa["detalhe"] = (
                "A conta atual nao pode ler esta tarefa. Isso nao significa "
                "que o backup falhou."
            )
        else:
            tarefa["situacao"] = "Estado indeterminado"
            tarefa["detalhe"] = (
                "Nao foi possivel confirmar o estado desta tarefa. Isso nao "
                "significa que o backup falhou."
            )
        return tarefa

    resultado = bruto.get("resultado")
    try:
        resultado = int(resultado)
    except (TypeError, ValueError):
        resultado = None
    tarefa["resultado"] = resultado

    estado_normalizado = tarefa["estado"].strip().lower()
    if estado_normalizado == "disabled":
        tarefa["nivel"] = NIVEL_AVISO
        tarefa["situacao"] = "Tarefa desabilitada"
        tarefa["detalhe"] = "A tarefa existe, mas nao sera executada."
        return tarefa

    if resultado is None:
        tarefa["situacao"] = "Estado indeterminado"
        tarefa["detalhe"] = "O Agendador nao informou o resultado da ultima execucao."
        return tarefa

    if estado_normalizado == "running" or resultado == RESULTADO_EM_EXECUCAO:
        tarefa["nivel"] = NIVEL_OK
        tarefa["situacao"] = "Em execucao"
        return tarefa

    if resultado == RESULTADO_SEM_MAIS_EXECUCOES:
        tarefa["nivel"] = NIVEL_AVISO
        tarefa["situacao"] = "Sem proximas execucoes"
        tarefa["detalhe"] = (
            "A tarefa nao possui outro disparo agendado. Revise o gatilho."
        )
        return tarefa

    if resultado == RESULTADO_SUCESSO:
        if tarefa["ultima_execucao"]:
            if tarefa["proxima_execucao"]:
                tarefa["nivel"] = NIVEL_OK
                tarefa["situacao"] = "Ultima execucao concluida"
            else:
                tarefa["nivel"] = NIVEL_AVISO
                tarefa["situacao"] = "Sem proxima execucao"
                tarefa["detalhe"] = (
                    "A ultima execucao terminou, mas nao ha outro disparo "
                    "agendado. Revise o gatilho."
                )
        else:
            tarefa["nivel"] = NIVEL_AVISO
            tarefa["situacao"] = "Ainda nao executou"
            tarefa["detalhe"] = "A tarefa esta registrada, mas ainda nao rodou."
        return tarefa

    if resultado == RESULTADO_NUNCA_EXECUTADA:
        tarefa["nivel"] = NIVEL_AVISO
        tarefa["situacao"] = "Ainda nao executou"
        tarefa["detalhe"] = "A tarefa esta registrada, mas ainda nao rodou."
        return tarefa

    if resultado in _RESULTADOS_NEUTROS:
        if not tarefa["proxima_execucao"]:
            tarefa["nivel"] = NIVEL_AVISO
            tarefa["situacao"] = "Sem proxima execucao"
            tarefa["detalhe"] = (
                "O Agendador informa que a tarefa esta pronta, mas nao ha "
                "outro disparo agendado. Revise o gatilho."
            )
        else:
            tarefa["nivel"] = (
                NIVEL_OK if tarefa["ultima_execucao"] else NIVEL_DESCONHECIDO
            )
            tarefa["situacao"] = "Aguardando gatilho"
        return tarefa

    tarefa["nivel"] = NIVEL_ERRO
    tarefa["situacao"] = "Ultima execucao falhou"
    tarefa["detalhe"] = f"O Agendador registrou o codigo {resultado}."
    return tarefa


def _tarefa_indisponivel(nome, motivo):
    return {
        "nome": nome,
        "encontrada": False,
        "estado": "",
        "ultima_execucao": None,
        "proxima_execucao": None,
        "resultado": None,
        "nivel": NIVEL_DESCONHECIDO,
        "situacao": "Nao verificado",
        "detalhe": motivo,
    }


def limpar_cache():
    """Descarta o cache de consultas; usado por testes e pelo modo completo."""
    with _cache_lock:
        _cache.clear()


def consultar_tarefas(
    nomes=TAREFAS_BACKUP,
    timeout=TIMEOUT_PADRAO_SEGUNDOS,
    executavel=None,
    consultar=None,
    cache_segundos=0,
):
    """Le o estado das tarefas informadas sem nunca altera-las.

    Falhas de ambiente jamais viram alarme de backup: elas retornam nivel
    ``desconhecido`` com o motivo, para que a interface diferencie
    "nao consegui verificar" de "verifiquei e falhou".

    ``cache_segundos`` evita abrir um processo do PowerShell a cada
    carregamento da Central. O diagnostico completo usa sempre zero.
    """
    nomes_validos = _validar_nomes(nomes)

    cache_segundos = max(0, int(cache_segundos or 0))
    chave = tuple(nomes_validos)
    if cache_segundos:
        with _cache_lock:
            registro = _cache.get(chave)
            if registro and (time.monotonic() - registro[0]) < cache_segundos:
                return [dict(item) for item in registro[1]]

    resultado = _consultar_sem_cache(nomes_validos, timeout, executavel, consultar)

    if cache_segundos:
        with _cache_lock:
            _cache[chave] = (time.monotonic(), [dict(item) for item in resultado])
    return resultado


def _consultar_sem_cache(nomes_validos, timeout, executavel, consultar):
    if consultar is None:
        if not _e_windows():
            motivo = "O Agendador de Tarefas so existe no Windows."
            return [_tarefa_indisponivel(nome, motivo) for nome in nomes_validos]
        executavel = executavel or _localizar_powershell()
        if not executavel:
            motivo = "O PowerShell nao foi encontrado para consultar o Agendador."
            return [_tarefa_indisponivel(nome, motivo) for nome in nomes_validos]

        def consultar(alvos):
            return _executar_consulta(alvos, timeout, executavel)

    try:
        brutos = consultar(nomes_validos)
    except TarefasIndisponiveis as exc:
        return [_tarefa_indisponivel(nome, str(exc)) for nome in nomes_validos]
    except Exception as exc:  # pragma: no cover - defesa adicional
        motivo = f"Nao foi possivel consultar o Agendador: {exc}"
        return [_tarefa_indisponivel(nome, motivo) for nome in nomes_validos]

    por_nome = {}
    for bruto in brutos:
        if not isinstance(bruto, dict):
            continue
        classificada = _classificar_tarefa(bruto)
        if classificada["nome"]:
            por_nome[classificada["nome"]] = classificada

    return [
        por_nome.get(
            nome,
            _tarefa_indisponivel(
                nome,
                "O Agendador nao retornou informacoes sobre esta tarefa.",
            ),
        )
        for nome in nomes_validos
    ]
