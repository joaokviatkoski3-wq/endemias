"""Leitura segura da credencial privada da API Conta Ovos."""

import os
from pathlib import Path


DEFAULT_CREDENTIAL_PATH = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
) / "Endemias" / "contaovos.key"


class ContaOvosCredentialError(RuntimeError):
    pass


def credential_path(env=None):
    env = os.environ if env is None else env
    configured = str(env.get("ENDEMIAS_CONTAOVOS_KEY_FILE") or "").strip()
    return Path(configured) if configured else DEFAULT_CREDENTIAL_PATH


def configured(env=None):
    return credential_path(env).is_file()


def read_key(env=None):
    path = credential_path(env)
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise ContaOvosCredentialError(
            "A credencial privada do Conta Ovos ainda nao foi configurada."
        ) from None
    except OSError:
        raise ContaOvosCredentialError(
            "Nao foi possivel ler a credencial privada do Conta Ovos."
        ) from None
    if not value or "\n" in value or "\r" in value:
        raise ContaOvosCredentialError(
            "A credencial privada do Conta Ovos e invalida."
        )
    return value


def public_status(env=None):
    path = credential_path(env)
    return {
        "configured": path.is_file(),
        "path": str(path),
    }
