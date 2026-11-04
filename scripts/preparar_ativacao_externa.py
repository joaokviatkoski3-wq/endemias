"""Consulta de prontidao e configuracao proposta; sem aplicar migracoes."""

import argparse
import copy
import ctypes
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEB_HOME = Path(r"C:\ProgramData\EndemiasWeb")


def proposed_config(original, hostname, local_ip):
    if not re.fullmatch(r"[a-z0-9-]+\.vsatt\.com\.br", hostname):
        raise ValueError("Hostname deve ser um subdominio simples de vsatt.com.br.")
    address = ipaddress.IPv4Address(local_ip)
    if not any(address in ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError("Entrada local exige IP privado explicito.")
    config = copy.deepcopy(original)
    config.update(server="waitress", version="1.76.0", probe_only=False)
    config["env"].update({
        "ENDEMIAS_ACESSO_EXTERNO": "1", "ENDEMIAS_ALLOWED_HOSTS": hostname,
        "ENDEMIAS_BIND": "127.0.0.1", "ENDEMIAS_THREADS": "16",
        "ENDEMIAS_ACESSO_LOCAL": "1", "ENDEMIAS_LOCAL_BIND": str(address),
        "ENDEMIAS_LOCAL_PORT": "5000", "ENDEMIAS_TUNNEL_PORT": "5001",
    })
    return config


def inspect_database(config):
    import psycopg2
    from psycopg2 import sql
    from app_core import postgresql_migrations
    os.environ.update(config["env"])
    env = config["env"]
    connection = psycopg2.connect(host=env["ENDEMIAS_PG_HOST"], port=env["ENDEMIAS_PG_PORT"],
        user=env["ENDEMIAS_PG_USER"], dbname=env["ENDEMIAS_PG_DATABASE"], connect_timeout=10,
        application_name="endemias_preflight_readonly")
    try:
        connection.set_session(readonly=True)
        migrations = postgresql_migrations.status(connection, ROOT / "migrations/postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == "endemias"
            cursor.execute("SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user")
            assert not any(cursor.fetchone())
            cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE nivel='admin') FROM usuarios WHERE ativo=1")
            users, admins = cursor.fetchone()
            cursor.execute("SHOW listen_addresses")
            listen = cursor.fetchone()[0]
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            tables = [row[0] for row in cursor.fetchall()]
            counts = {}
            for name in tables:
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(name)))
                counts[name] = cursor.fetchone()[0]
        return {"migrations": migrations, "active_users": users, "active_admins": admins,
                "listen_addresses": listen, "counts": counts,
                "sql_administrative_privileges": False}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--local-ip", required=True)
    args = parser.parse_args()
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Consulta usa credencial protegida; requer administrador.")
    original = json.loads((WEB_HOME / "config.json").read_text(encoding="utf-8"))
    proposed = proposed_config(original, args.host, args.local_ip)
    result = inspect_database(proposed)
    pending = [row["version"] for row in result["migrations"] if row["state"] == "pending"]
    mismatch = [row["version"] for row in result["migrations"] if row["state"] == "checksum_mismatch"]
    with open(r"C:\endemias\endemias.db", "rb") as frozen:
        frozen_hash = hashlib.file_digest(frozen, "sha256").hexdigest()
    result.update(hostname=args.host, pending=pending, mismatch=mismatch,
                  schema_ready=pending == ["0030"] and not mismatch and result["active_admins"] > 0,
                  frozen_sqlite_sha256=frozen_hash,
                  changes_applied=False)
    (ROOT / ".venv/ativacao-externa-preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Consulta de prontidao concluida sem escrita no banco ou configuracao oficial.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback
        (ROOT / ".venv/ativacao-externa-preflight.json").write_text(json.dumps({"error_type": type(error).__name__,
            "trace": [{"line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        raise SystemExit(1)
