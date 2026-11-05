"""Redução de dados para auditoria e diagnóstico, sem mensagens livres."""
import json
import logging
import math
import re
import traceback
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

OCULTO = "[conteúdo omitido]"
_PROIBIDOS = ("senha", "password", "token", "secret", "cookie", "authorization", "csrf",
              "sessao", "session", "chave", "credencial", "dsn", "url", "link",
              "observac", "descric", "diagnost", "prescric", "receita", "paciente",
              "morador", "telefone", "endereco", "logradouro", "cpf", "cnpj", "email")
_TEXTOS = {"campo", "acao", "entidade", "tipo", "status", "situacao", "nivel", "setor",
           "formato", "origem", "modulo", "codigo", "versao", "versao_formulario",
           "arquivo", "backup_pre_import", "usuario", "valor_novo", "valor_anterior",
           "motivo_codigo", "movimento", "campos", "rota", "endpoint", "metodo",
           "correlacao", "erro_tipo", "tipo_trabalho", "destino_tratamento"}


def identificador(value, limite=100):
    texto = str(value or "")[:limite]
    return texto if re.fullmatch(r"[\w.:/<> -]*", texto, re.ASCII) else "[identificador omitido]"


def _chave(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).casefold())
                   if not unicodedata.combining(c))


def detalhes_seguros(value, campo="", profundidade=0):
    if profundidade > 10:
        return "[limite de profundidade]"
    key = _chave(campo)
    if any(p in key for p in _PROIBIDOS):
        return OCULTO
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if not isinstance(value, float) or math.isfinite(value) else None
    if isinstance(value, dict):
        # Nas alterações por campo, antes/depois herdam a classificação do campo.
        contexto = str(value.get("campo", ""))
        result = {}
        for k, v in list(value.items())[:100]:
            nome = str(k)[:100]
            result[nome] = detalhes_seguros(v, contexto if nome in {"antes", "depois", "valor", "valor_novo", "valor_antigo", "valor_anterior", "valor_ant"} and contexto else nome, profundidade + 1)
        if len(value) > 100:
            result["_chaves_omitidas"] = len(value) - 100
        return result
    if isinstance(value, (list, tuple, set)):
        itens = list(value)
        result = [detalhes_seguros(v, campo, profundidade + 1) for v in itens[:200]]
        if len(itens) > 200:
            result.append({"_itens_omitidos": len(itens) - 200})
        return result
    if isinstance(value, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?|\d{2}:\d{2}(?::\d{2})?", value):
            return value
        if re.fullmatch(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", value, re.I):
            return value
        if key not in _TEXTOS and not key.startswith("id_") and not key.endswith("_id"):
            if not (key.startswith(("tipo_", "codigo_", "status_", "nivel_", "data_", "hora_"))
                    and re.fullmatch(r"[\w .:/-]{1,80}", value)):
                return OCULTO
        # Mesmo metadados permitidos não carregam URLs, controles ou textos longos.
        if len(value) > 180 or re.search(r"[\x00-\x1f]|https?://|Bearer |eyJ[A-Za-z0-9_-]+\.", value, re.I):
            return OCULTO
        return value
    return OCULTO


def limitar_detalhes(value, max_bytes=32768):
    seguro = detalhes_seguros(value)
    encoded = json.dumps(seguro, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return seguro
    # Mantém uma indicação explícita; nunca publica silenciosamente um JSON cortado.
    return {"_detalhes_limitados": True, "_bytes_reduzidos": len(encoded.encode("utf-8")),
            "_campos": [identificador(k) for k in value][:100] if isinstance(value, dict) else []}


def erro_seguro(record):
    result = {"logger": identificador(record.name), "modulo": identificador(record.module),
              "funcao": identificador(record.funcName), "linha": record.lineno}
    if record.exc_info and record.exc_info[0]:
        result["erro_tipo"] = identificador(record.exc_info[0].__name__)
        result["frames"] = [{"arquivo": identificador(Path(f.filename).name),
                             "linha": f.lineno, "funcao": identificador(f.name)}
                            for f in traceback.extract_tb(record.exc_info[2])[-10:]]
    return result


class FormatoTecnicoSeguro(logging.Formatter):
    """Não usa getMessage/args/exception text: podem conter SQL e credenciais."""
    def format(self, record):
        return json.dumps({"instante": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                           "nivel": record.levelname, **erro_seguro(record)}, ensure_ascii=False)
