"""Camada compartilhada de saude dos backups do Sistema Endemias.

Este modulo concentra a avaliacao usada pelo verificador de linha de comando,
pela Central do Sistema e pelo diagnostico administrativo, evitando manter a
mesma regra em mais de um lugar.

Existem dois modos:

``MODO_RAPIDO``
    Le apenas metadados baratos (arquivos, datas, tamanhos, JSON de
    acompanhamento e manifesto do ZIP). Serve para abrir a Central sem
    recalcular hashes de arquivos grandes nem executar ``pg_restore``.

``MODO_COMPLETO``
    Faz a validacao integral: recalcula o SHA-256 do dump, confere o catalogo
    com ``pg_restore --list``, testa o ZIP e recalcula o SHA-256 do dump
    interno.

Uma falha de ambiente (acesso negado, pasta inacessivel, Agendador
indisponivel) nunca vira alarme de backup: ela produz o nivel
``desconhecido``, para que a interface diferencie "nao consegui verificar" de
"verifiquei e esta com problema".
"""

import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from app_core import backup as backup_core
from app_core import backup_completo
from app_core import backup_tasks
from app_core import postgresql_backup


MODO_RAPIDO = "rapido"
MODO_COMPLETO = "completo"

NIVEL_OK = "ok"
NIVEL_AVISO = "aviso"
NIVEL_ERRO = "erro"
NIVEL_DESCONHECIDO = "desconhecido"

MAX_DUMP_HORAS_PADRAO = 36
MAX_COMPLETO_DIAS_PADRAO = 8

_ORDEM_NIVEIS = {
    NIVEL_ERRO: 3,
    NIVEL_AVISO: 2,
    NIVEL_DESCONHECIDO: 1,
    NIVEL_OK: 0,
}

# Remove qualquer segredo que porventura apareca em mensagens de ferramentas.
_PADROES_SENSIVEIS = (
    re.compile(r"(?i)\b(password|senha|pgpassword)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bpgpass(?:file)?\s*[=:]\s*\S+"),
)


def sanitizar_mensagem(mensagem, limite=400):
    """Remove segredos e limita o tamanho antes de exibir uma mensagem."""
    texto = str(mensagem or "").strip()
    for padrao in _PADROES_SENSIVEIS:
        texto = padrao.sub("[oculto]", texto)
    if len(texto) > limite:
        texto = texto[:limite].rstrip() + "..."
    return texto


def _idade_horas(path, agora):
    modificado = datetime.fromtimestamp(Path(path).stat().st_mtime)
    return max(0.0, (agora - modificado).total_seconds() / 3600)


def pior_nivel(niveis):
    pior = NIVEL_OK
    for nivel in niveis:
        if _ORDEM_NIVEIS.get(nivel, 0) > _ORDEM_NIVEIS.get(pior, 0):
            pior = nivel
    return pior


class _ProblemaBackup(RuntimeError):
    """Falha real e comprovada em um artefato de backup."""


class _BackupIndisponivel(RuntimeError):
    """O artefato nao pode ser inspecionado neste ambiente."""


# ---------------------------------------------------------------------------
# Dump diario
# ---------------------------------------------------------------------------


def _coletar_dump(destino, database, max_horas, agora, modo, env):
    try:
        backups = postgresql_backup.listar_backups(destino, limite=1)
    except PermissionError as exc:
        raise _BackupIndisponivel(
            "Sem permissao para ler a pasta de dumps PostgreSQL."
        ) from exc
    except OSError as exc:
        raise _BackupIndisponivel(
            f"Nao foi possivel ler a pasta de dumps: {sanitizar_mensagem(exc)}"
        ) from exc

    if not backups:
        raise _ProblemaBackup("Nenhum dump PostgreSQL foi encontrado.")

    info = backups[0]
    arquivo = Path(info["arquivo"])
    origem = info.get("origem") or {}
    if origem.get("database") != database:
        raise _ProblemaBackup(
            "O dump mais recente pertence a outro banco PostgreSQL."
        )
    if info.get("validado") is not True or not info.get("sha256"):
        raise _ProblemaBackup("O dump mais recente nao possui metadados validados.")

    resultado = {
        "arquivo": str(arquivo),
        "nome": arquivo.name,
        "tamanho_bytes": info.get("tamanho_bytes"),
        "sha256": info.get("sha256"),
        "integridade": "metadados conferidos",
    }

    if modo == MODO_COMPLETO:
        hash_atual = backup_core.calcular_sha256(arquivo)
        if hash_atual != info["sha256"]:
            raise _ProblemaBackup(
                "O dump mais recente falhou na verificacao SHA-256."
            )
        postgresql_backup.validar_backup(arquivo, env=env)
        resultado["sha256"] = hash_atual
        resultado["integridade"] = "catalogo e SHA-256 validados"

    idade = _idade_horas(arquivo, agora)
    resultado["idade_horas"] = round(idade, 2)
    resultado["tamanho_bytes"] = arquivo.stat().st_size
    if idade > float(max_horas):
        raise _ProblemaBackup(
            f"O dump PostgreSQL mais recente tem {idade:.1f} horas."
        )
    return resultado


def avaliar_dump(
    destino,
    database="endemias",
    max_horas=MAX_DUMP_HORAS_PADRAO,
    agora=None,
    modo=MODO_RAPIDO,
    env=None,
):
    """Avalia o dump diario e devolve um bloco estruturado, sem levantar erro."""
    agora = agora or datetime.now()
    try:
        dados = _coletar_dump(destino, database, max_horas, agora, modo, env)
    except _BackupIndisponivel as exc:
        return {
            "nivel": NIVEL_DESCONHECIDO,
            "titulo": "Dump diario nao verificado",
            "detalhe": sanitizar_mensagem(exc),
        }
    except _ProblemaBackup as exc:
        return {
            "nivel": NIVEL_ERRO,
            "titulo": "Dump diario com problema",
            "detalhe": sanitizar_mensagem(exc),
        }
    except Exception as exc:
        return {
            "nivel": NIVEL_ERRO,
            "titulo": "Dump diario com problema",
            "detalhe": sanitizar_mensagem(exc),
        }

    dados.update({
        "nivel": NIVEL_OK,
        "titulo": "Dump diario disponivel",
        "detalhe": f"{dados['nome']} com {dados['idade_horas']:.1f} h.",
    })
    return dados


# ---------------------------------------------------------------------------
# Backup completo semanal
# ---------------------------------------------------------------------------


def _manifesto_postgresql(zip_path, database, verificar_conteudo=True):
    """Le o manifesto e, no modo completo, confere ZIP e dump interno."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if verificar_conteudo:
                corrompido = zf.testzip()
                if corrompido:
                    raise _ProblemaBackup(
                        f"O backup completo esta corrompido em {corrompido}."
                    )
            manifesto = json.loads(
                zf.read("manifesto_backup.json").decode("utf-8")
            )
            if manifesto.get("backend_banco") != "postgresql":
                return None
            if manifesto.get("banco_origem") != database:
                return None
            if manifesto.get("integridade_banco") != "catalogo validado":
                raise _ProblemaBackup(
                    "O backup completo PostgreSQL nao registra catalogo validado."
                )
            dumps = [
                item
                for item in manifesto.get("incluidos", [])
                if item.get("destino_zip", "").startswith("banco/")
                and item.get("destino_zip", "").endswith(".dump")
            ]
            if len(dumps) != 1 or not dumps[0].get("sha256"):
                raise _ProblemaBackup(
                    "O backup completo nao possui um dump PostgreSQL identificavel."
                )
            if verificar_conteudo:
                item = dumps[0]
                digest = hashlib.sha256()
                with zf.open(item["destino_zip"]) as stream:
                    for bloco in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(bloco)
                if digest.hexdigest() != item["sha256"]:
                    raise _ProblemaBackup(
                        "O dump interno do backup completo diverge do SHA-256."
                    )
            return manifesto
    except PermissionError as exc:
        raise _BackupIndisponivel(
            "Sem permissao para ler o backup completo."
        ) from exc
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise _ProblemaBackup("Backup completo PostgreSQL invalido.") from exc


def _coletar_backup_completo(destino, database, max_dias, agora, modo):
    verificar_conteudo = modo == MODO_COMPLETO
    try:
        candidatos = backup_completo.listar_backups_completos(destino, limite=None)
    except PermissionError as exc:
        raise _BackupIndisponivel(
            "Sem permissao para ler a pasta de backups completos."
        ) from exc
    except OSError as exc:
        raise _BackupIndisponivel(
            "Nao foi possivel ler a pasta de backups completos: "
            f"{sanitizar_mensagem(exc)}"
        ) from exc

    for info in candidatos:
        arquivo = Path(info["arquivo"])
        manifesto = _manifesto_postgresql(
            arquivo,
            database,
            verificar_conteudo=verificar_conteudo,
        )
        if manifesto is None:
            continue
        idade = _idade_horas(arquivo, agora)
        if idade > float(max_dias) * 24:
            raise _ProblemaBackup(
                f"O backup completo PostgreSQL mais recente tem {idade / 24:.1f} dias."
            )
        return {
            "arquivo": str(arquivo),
            "nome": arquivo.name,
            "idade_dias": round(idade / 24, 2),
            "tamanho_bytes": arquivo.stat().st_size,
            "integridade": (
                "ZIP, manifesto e SHA-256 interno validados"
                if verificar_conteudo
                else "manifesto conferido"
            ),
        }
    raise _ProblemaBackup("Nenhum backup completo PostgreSQL foi encontrado.")


def avaliar_backup_completo(
    destino,
    database="endemias",
    max_dias=MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
    modo=MODO_RAPIDO,
):
    """Avalia o backup completo semanal sem levantar erro."""
    agora = agora or datetime.now()
    try:
        dados = _coletar_backup_completo(destino, database, max_dias, agora, modo)
    except _BackupIndisponivel as exc:
        return {
            "nivel": NIVEL_DESCONHECIDO,
            "titulo": "Backup completo nao verificado",
            "detalhe": sanitizar_mensagem(exc),
        }
    except Exception as exc:
        return {
            "nivel": NIVEL_ERRO,
            "titulo": "Backup completo com problema",
            "detalhe": sanitizar_mensagem(exc),
        }

    dados.update({
        "nivel": NIVEL_OK,
        "titulo": "Backup completo disponivel",
        "detalhe": f"{dados['nome']} com {dados['idade_dias']:.1f} dia(s).",
    })
    return dados


# ---------------------------------------------------------------------------
# Avaliacao agregada
# ---------------------------------------------------------------------------


def avaliar(
    backup_dir,
    completo_dir,
    database="endemias",
    modo=MODO_RAPIDO,
    max_dump_horas=MAX_DUMP_HORAS_PADRAO,
    max_completo_dias=MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
    env=None,
    tarefas=None,
):
    """Consolida dump, backup completo e tarefas agendadas."""
    agora = agora or datetime.now()
    modo = MODO_COMPLETO if modo == MODO_COMPLETO else MODO_RAPIDO

    dump = avaliar_dump(
        backup_dir,
        database=database,
        max_horas=max_dump_horas,
        agora=agora,
        modo=modo,
        env=env,
    )
    completo = avaliar_backup_completo(
        completo_dir,
        database=database,
        max_dias=max_completo_dias,
        agora=agora,
        modo=modo,
    )
    if tarefas is None:
        # O modo completo sempre reconsulta; o rapido aproveita o cache curto
        # para nao abrir um processo do PowerShell a cada abertura da pagina.
        tarefas = backup_tasks.consultar_tarefas(
            cache_segundos=(
                0 if modo == MODO_COMPLETO else backup_tasks.CACHE_PADRAO_SEGUNDOS
            )
        )

    niveis = [dump["nivel"], completo["nivel"]] + [t["nivel"] for t in tarefas]
    nivel = pior_nivel(niveis)
    return {
        "backend": "postgresql",
        "modo": modo,
        "verificado_em": agora.isoformat(timespec="seconds"),
        "nivel": nivel,
        "dump": dump,
        "completo": completo,
        "tarefas": list(tarefas),
    }


# ---------------------------------------------------------------------------
# API estrita usada pelo verificador de linha de comando
# ---------------------------------------------------------------------------


def verificar_dump(
    destino,
    database="endemias",
    max_horas=MAX_DUMP_HORAS_PADRAO,
    agora=None,
    env=None,
):
    """Validacao integral do dump; levanta ``RuntimeError`` em caso de falha."""
    agora = agora or datetime.now()
    try:
        dados = _coletar_dump(
            destino,
            database,
            max_horas,
            agora,
            MODO_COMPLETO,
            env,
        )
    except (_ProblemaBackup, _BackupIndisponivel) as exc:
        raise RuntimeError(str(exc)) from exc
    return {
        "arquivo": dados["arquivo"],
        "idade_horas": dados["idade_horas"],
        "tamanho_bytes": dados["tamanho_bytes"],
        "sha256": dados["sha256"],
        "integridade": "catalogo e SHA-256 validados",
    }


def verificar_backup_completo(
    destino,
    database="endemias",
    max_dias=MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
):
    """Validacao integral do backup completo; levanta ``RuntimeError``."""
    agora = agora or datetime.now()
    try:
        dados = _coletar_backup_completo(
            destino,
            database,
            max_dias,
            agora,
            MODO_COMPLETO,
        )
    except (_ProblemaBackup, _BackupIndisponivel) as exc:
        raise RuntimeError(str(exc)) from exc
    return {
        "arquivo": dados["arquivo"],
        "idade_dias": dados["idade_dias"],
        "tamanho_bytes": dados["tamanho_bytes"],
        "integridade": "ZIP, manifesto e SHA-256 interno validados",
    }


def verificar_tudo(
    backup_dir,
    complete_dir,
    database="endemias",
    max_dump_horas=MAX_DUMP_HORAS_PADRAO,
    max_completo_dias=MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
    env=None,
):
    """Validacao integral dos dois artefatos, no formato do verificador."""
    return {
        "verificado_em": (agora or datetime.now()).isoformat(timespec="seconds"),
        "dump": verificar_dump(
            backup_dir,
            database=database,
            max_horas=max_dump_horas,
            agora=agora,
            env=env,
        ),
        "completo": verificar_backup_completo(
            complete_dir,
            database=database,
            max_dias=max_completo_dias,
            agora=agora,
        ),
    }
