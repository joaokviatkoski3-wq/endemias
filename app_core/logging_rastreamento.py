"""Trilha privada e limitada de requisições. Não grava corpos ou query strings."""
import atexit
import json
import ipaddress
import logging
import os
import re
import secrets
import threading
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g, has_app_context, has_request_context, request, session

from app_core.logging_seguranca import erro_seguro, identificador
from app_core import auth
from app_core.version import APP_VERSION

MAX_EXPORTACAO = 10000
_locks = {}
_registry_lock = threading.Lock()
_writers = {}
_handler = None
_fallback_config = None
_polling = {"auth.presenca", "admin.presencas", "static"}


def _instante():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _setor(config):
    value = config.get("SETOR") if config.get("SETORES_ENABLED") else "sistema"
    return value if value in {"endemias", "ambiental", "portal"} else "sistema"


class Trilha:
    def __init__(self, root, setor, max_bytes=5*1024*1024, backups=5, dias=30):
        self.directory = Path(root) / "logs_privados" / setor
        self.setor = setor
        self.path = self.directory / "requisicoes.jsonl"
        self.max_bytes, self.backups, self.dias = max_bytes, backups, dias
        self.falhas = 0
        self.ultima_falha = None
        self._limpeza = 0
        with _registry_lock:
            self.lock = _locks.setdefault(str(self.path.resolve()), threading.RLock())

    @contextmanager
    def _exclusivo(self):
        with self.lock:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.directory / ".escrita.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                if os.name == "nt":
                    import msvcrt
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                    for tentativa in range(40):
                        os.lseek(fd, 0, 0)
                        try:
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            if tentativa == 39:
                                raise
                            time.sleep(0.002)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                # Fechar o descritor também libera o lock entre processos.
                os.close(fd)

    def arquivos(self):
        return [self.path] + [self.directory / f"requisicoes.jsonl.{i}" for i in range(1, self.backups+1)]

    def _reter(self):
        if time.monotonic() - self._limpeza < 3600:
            return
        self._limpeza = time.monotonic()
        cutoff = time.time() - self.dias*86400
        for path in self.arquivos():
            if path.exists() and path.stat().st_mtime < cutoff:
                path.unlink()
            elif path.exists():
                rows = path.read_bytes().splitlines(keepends=True)
                limite = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
                kept = []
                for line in rows:
                    try:
                        item = json.loads(line)
                        if not isinstance(item, dict) or not item.get("id") or not isinstance(item.get("instante"), str):
                            raise ValueError("Linha incompleta")
                        if item["instante"] >= limite:
                            kept.append(line)
                    except (ValueError, TypeError):
                        kept.append(line)
                if len(kept) != len(rows):
                    fd, name = tempfile.mkstemp(prefix=".retencao-", dir=self.directory)
                    try:
                        with os.fdopen(fd, "wb") as handle:
                            handle.writelines(kept)
                        Path(name).replace(path)
                    finally:
                        Path(name).unlink(missing_ok=True)

    def gravar(self, evento):
        try:
            raw = json.dumps({"id": secrets.token_hex(16), "instante": _instante(),
                              "setor": self.setor, "versao": APP_VERSION, "pid": os.getpid(),
                              **evento}, ensure_ascii=False, allow_nan=False) + "\n"
            if len(raw.encode("utf-8")) > 16384:
                raise ValueError("Registro excedeu o limite técnico")
            with self._exclusivo():
                self._reter()
                if self.path.exists() and self.path.stat().st_size + len(raw.encode("utf-8")) > self.max_bytes:
                    paths = self.arquivos()
                    paths[-1].unlink(missing_ok=True)
                    for i in range(self.backups-1, -1, -1):
                        if paths[i].exists():
                            paths[i].replace(paths[i+1])
                with os.fdopen(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(raw)
            return True
        except Exception as exc:
            # Falha de observabilidade nunca altera o resultado da operação.
            self.falhas += 1
            self.ultima_falha = type(exc).__name__
            return False

    def consultar(self, filtros, pagina=1, por_pagina=50, limite=None):
        # Snapshot breve dos arquivos fechados antes de filtrar; teto de 30 MiB/setor.
        blocos = []
        try:
            with self._exclusivo():
                for path in self.arquivos():
                    if path.exists():
                        blocos.append(path.read_bytes())
        except OSError:
            return {"registros": [], "total": 0, "incompleto": True}
        total, result, vistos, invalidas = 0, [], set(), 0
        inicio = 0 if limite else (pagina-1)*por_pagina
        quantidade = limite+1 if limite else por_pagina
        cutoff = (datetime.now(timezone.utc)-timedelta(days=self.dias)).isoformat()
        for block in blocos:
            for line in reversed(block.splitlines()):
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict) or not item.get("id") or not item.get("instante"):
                        raise ValueError("Linha incompleta")
                except (ValueError, TypeError):
                    invalidas += 1
                    continue
                if item.get("id") in vistos or item.get("instante", "") < cutoff:
                    continue
                vistos.add(item.get("id"))
                if not _combina(item, filtros):
                    continue
                if inicio <= total < inicio+quantidade:
                    result.append(item)
                total += 1
        return {"registros": result, "total": total, "incompleto": bool(invalidas), "linhas_invalidas": invalidas}


def _combina(item, f):
    dia = item.get("instante", "")[:10]
    if f.get("d_ini") and dia < f["d_ini"] or f.get("d_fim") and dia > f["d_fim"]:
        return False
    for filtro, campo in (("acao", "tipo"), ("usuario", "ator"), ("rota", "rota"), ("correlacao", "correlacao")):
        if f.get(filtro) and f[filtro].casefold() not in str(item.get(campo, "")).casefold():
            return False
    if f.get("metodo") and f["metodo"] != item.get("metodo"):
        return False
    status = item.get("status")
    if f.get("status") and str(status or "") != f["status"]:
        return False
    resultado = f.get("resultado")
    if resultado == "erro" and (not status or status < 500):
        return False
    if resultado == "negado" and status not in {401, 403, 429}:
        return False
    return True


def trilha(config, setor=None):
    area = setor or _setor(config)
    if area not in {"endemias", "ambiental", "portal", "sistema"}:
        raise ValueError("Área de log inválida")
    root = str(Path(config["LOG_PATH"]).resolve().parent)
    key = (root, area)
    with _registry_lock:
        writer = _writers.get(key)
    if writer is None:
        writer = Trilha(root, area)
        with _registry_lock:
            _writers[key] = writer
    return writer


def contexto():
    if not has_request_context():
        return {}
    user = getattr(g, "_auth_usuario", None) or {}
    uid = user.get("id_usuario") or session.get("uid")
    try:
        ip = str(ipaddress.ip_address(auth.client_ip()))
    except ValueError:
        ip = "[IP inválido]"
    alvos = {}
    for key, value in (request.view_args or {}).items():
        if key in {"id", "uid"} or key.startswith("id_"):
            if isinstance(value, int) and not isinstance(value, bool):
                alvos[key] = value
            elif isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}|[0-9]{1,20}", value):
                alvos[key] = value
    return {"correlacao": getattr(g, "correlacao", None),
            "rota": request.url_rule.rule if request.url_rule else "[rota não reconhecida]",
            "endpoint": request.endpoint or "", "metodo": request.method if request.method in {"GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"} else "OUTRO",
            "ator_id": uid if isinstance(uid, int) else None,
            "ator_origem": "autenticado" if user else "sessao" if uid else "anonimo",
            "nivel": user.get("nivel") or session.get("nivel"),
            "ip": ip,
            "alvos": alvos,
            "ator": str(user.get("usuario") or session.get("nome") or "anônimo")[:100]}


def referencia_auditoria(acao, entidade, entidade_id, detalhes):
    if not has_request_context():
        return
    refs = getattr(g, "_rastro_auditoria", None)
    if refs is not None and len(refs) < 20:
        refs.append({"acao": identificador(acao), "entidade": identificador(entidade),
                     "entidade_id": identificador(entidade_id),
                     "campos": sorted(str(k) for k in (detalhes or {}) if k not in {"_rastro"})[:30]})


class _ErrosSeguros(logging.Handler):
    def emit(self, record):
        try:
            if has_app_context() and current_app.config.get("LOG_PATH"):
                trilha(current_app.config).gravar({"tipo": "diagnostico", "nivel_log": record.levelname,
                                                  **contexto(), **erro_seguro(record)})
            elif _fallback_config:
                trilha(_fallback_config, "sistema").gravar({"tipo": "diagnostico", "nivel_log": record.levelname,
                                                          **erro_seguro(record)})
        except Exception:
            pass


def registrar(app):
    global _handler, _fallback_config
    if app.extensions.get("rastreamento"):
        return
    writer = trilha(app.config)
    app.extensions["rastreamento"] = writer
    with _registry_lock:
        if _fallback_config is None:
            _fallback_config = {"LOG_PATH": app.config["LOG_PATH"]}
        if _handler is None:
            _handler = _ErrosSeguros(logging.WARNING)
            logging.getLogger().addHandler(_handler)
    if not getattr(writer, "_lifecycle_registrado", False):
        writer._lifecycle_registrado = True
        writer.gravar({"tipo": "aplicacao_iniciada", "pid": os.getpid()})
        atexit.register(lambda: writer.gravar({"tipo": "processo_encerrado", "pid": os.getpid()}) if writer.directory.exists() else None)
    polling = {}

    @app.before_request
    def inicio_rastreamento():
        g.correlacao = secrets.token_hex(16)
        g._rastro_inicio = time.monotonic()
        g._rastro_auditoria = []

    @app.after_request
    def fim_rastreamento(response):
        if not getattr(g, "correlacao", None):
            g.correlacao = secrets.token_hex(16)
        response.headers["X-Request-ID"] = g.correlacao
        inicio = getattr(g, "_rastro_inicio", time.monotonic())
        ctx = contexto()
        if request.endpoint == "static" and response.status_code < 400:
            return response


        rotina = request.endpoint == "auth.presenca" or (request.method in {"GET", "HEAD"} and (request.endpoint in _polling or "health" in (request.endpoint or "")))
        if rotina and response.status_code < 400:
            key = request.endpoint
            ultimo, repetidos = polling.get(key, (0, 0))
            if time.monotonic() - ultimo < 60:
                polling[key] = (ultimo, repetidos+1)
                return response
            polling[key] = (time.monotonic(), 0)
            ctx["polling_agrupado"] = repetidos
        refs = getattr(g, "_rastro_auditoria", [])
        evento = {"tipo": "download" if "attachment" in response.headers.get("Content-Disposition", "").lower() else "requisicao",
                  **ctx, "status": response.status_code, "duracao_ms": round((time.monotonic()-inicio)*1000, 2),
                  "bytes_resposta": response.content_length, "auditoria": refs}
        if response.is_streamed and not response.direct_passthrough and response.mimetype == "text/event-stream":
            writer.gravar({**evento, "tipo": "fluxo_iniciado"})
            original = response.response

            def acompanhar():
                encerrado = False
                try:
                    yield from original
                    encerrado = True
                finally:
                    writer.gravar({**evento, "tipo": "fluxo_encerrado", "completo": encerrado,
                                   "duracao_ms": round((time.monotonic()-inicio)*1000, 2), "auditoria": refs})
            response.response = acompanhar()
        else:
            writer.gravar(evento)
        return response


def provar_rotacao(config):
    """Prova local mínima: somente subpasta temporária na pasta privada de logs."""
    root = Path(config["LOG_PATH"]).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prova-logs-", dir=root) as temp:
        writer = Trilha(temp, "sistema", max_bytes=300, backups=2)
        for _ in range(8):
            if not writer.gravar({"tipo": "prova_rotacao", "status": 200}):
                return {"ok": False, "erro_tipo": writer.ultima_falha}
        arquivos = [p for p in writer.arquivos() if p.exists()]
        resultado = {"ok": len(arquivos) == 3 and all(p.stat().st_size <= 300 for p in arquivos),
                     "criacao_escrita_rotacao": len(arquivos) == 3, "dados_reais_lidos": False}
    resultado["temporarios_removidos"] = not Path(temp).exists()
    return resultado
