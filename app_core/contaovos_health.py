"""Estado operacional sanitizado da integracao Conta Ovos."""

import json
import os
from datetime import datetime
from pathlib import Path

from app_core import contaovos_credencial


DEFAULT_STATUS_PATH = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
) / "Endemias" / "contaovos_status.json"
_ALLOWED_FIELDS = {
    "ok",
    "checked_at",
    "page_items",
    "scopes",
    "credential_format",
    "error",
}


def status_path(env=None):
    env = os.environ if env is None else env
    configured = str(env.get("ENDEMIAS_CONTAOVOS_STATUS_FILE") or "").strip()
    return Path(configured) if configured else DEFAULT_STATUS_PATH


def read_status(env=None):
    credential = contaovos_credencial.public_status(env)
    result = {
        "configured": credential["configured"],
        "credential_path": credential["path"],
        "verified": False,
        "ok": False,
        "checked_at": None,
        "page_items": None,
        "scopes": [],
        "credential_format": None,
        "error": None,
    }
    path = status_path(env)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return result
    if not isinstance(raw, dict):
        return result
    safe = {key: raw.get(key) for key in _ALLOWED_FIELDS if key in raw}
    result.update(safe)
    result["verified"] = bool(result.get("checked_at"))
    result["ok"] = bool(result.get("ok"))
    return result


def write_status(data, env=None):
    path = status_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {key: data.get(key) for key in _ALLOWED_FIELDS if key in data}
    safe["checked_at"] = safe.get("checked_at") or datetime.now().isoformat(
        timespec="seconds"
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return safe
