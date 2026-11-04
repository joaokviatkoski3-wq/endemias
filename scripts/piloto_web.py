"""Piloto somente loopback, banco ficticio e recursos separados da producao."""

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Piloto local de acesso web do Endemias")
    parser.add_argument("--validar", action="store_true", help="Prepara massa ficticia sem abrir portas")
    args = parser.parse_args(argv)
    if ROOT == Path(r"C:\endemias"):
        raise SystemExit("Este piloto so pode rodar em worktree separada da producao.")
    runtime = ROOT / ".venv" / "piloto-web"
    runtime.mkdir(parents=True, exist_ok=True)
    database = runtime / "piloto.db"
    official = Path(r"C:\endemias\endemias.db")
    if ROOT not in runtime.resolve().parents or (database.exists() and official.exists() and database.samefile(official)):
        raise SystemExit("Caminho do piloto nao esta isolado do ambiente oficial.")
    marker = runtime / "massa.json"
    if database.exists():
        if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")).get("sintetico") is not True:
            raise SystemExit("Banco existente sem marcador de massa sintetica; nenhuma execucao permitida.")
    else:
        from scripts.preparar_massa_web_teste import preparar
        from app_core import auth
        preparar(database)
        password = secrets.token_urlsafe(18)
        conn = sqlite3.connect(database)
        try:
            # Nao deixar senhas publicas da fixture habilitadas no piloto.
            conn.execute("UPDATE usuarios SET senha_hash=?", (auth.hash_senha(password),))
            conn.commit()
        finally:
            conn.close()
        (runtime / "acesso.local.txt").write_text("PILOTO - SOMENTE DADOS FICTICIOS\nUsuario: admin\nSenha: " + password + "\n", encoding="utf-8")
        marker.write_text(json.dumps({"sintetico": True}), encoding="utf-8")

    # Mapeamento publico do ETL; sem tokens. Necessario para validar uploads
    # no piloto, inclusive em instalacoes cujo banco ficticio ja existe.
    config_path = runtime / "config.json"
    if not config_path.exists():
        shutil.copyfile(ROOT / "config.json", config_path)

    settings = {
        "ENDEMIAS_DB_BACKEND": "sqlite", "ENDEMIAS_DB_PATH": str(database),
        "ENDEMIAS_AMBIENTE": "teste", "ENDEMIAS_PORT": "5002",
        "ENDEMIAS_INSTANCE_DIR": str(runtime), "ENDEMIAS_ANEXOS_DIR": str(runtime / "anexos"),
        "ENDEMIAS_UPLOAD_TEMP": str(runtime / "uploads"), "ENDEMIAS_LOG_PATH": str(runtime / "piloto.log"),
        "ENDEMIAS_SECRET_KEY_PATH": str(runtime / "secret.key"),
        "ENDEMIAS_CONFIG_PATH": str(runtime / "config.json"),
        "ENDEMIAS_KOBO_CONFIG_PATH": str(runtime / "kobo_config.json"),
        "ENDEMIAS_BACKUP_DIR": str(runtime / "backups/banco"),
        "ENDEMIAS_BACKUP_COMPLETO_DIR": str(runtime / "backups/completos"),
        "ENDEMIAS_ACESSO_EXTERNO": "1", "ENDEMIAS_ALLOWED_HOSTS": "piloto.vsatt.com.br",
        "ENDEMIAS_BIND": "127.0.0.1", "ENDEMIAS_ACESSO_LOCAL": "1",
        "ENDEMIAS_LOCAL_BIND": "127.0.0.1", "ENDEMIAS_LOCAL_PORT": "5002",
        "ENDEMIAS_TUNNEL_PORT": "5003", "ENDEMIAS_THREADS": "8",
        "ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK": "1",
    }
    os.environ.update(settings)
    from app import app
    from servir import local_application, local_options, server_options, create_dual_servers
    server_options(app.config)
    local_options(app.config)
    local = local_application(app, "127.0.0.1")
    if args.validar:
        print("Piloto preparado: SQLite ficticio, recursos isolados e portas 5002/5003 em loopback; nenhum servidor iniciado.")
        return 0
    external_server, local_server = create_dual_servers(app, local)
    print("PILOTO - SOMENTE DADOS FICTICIOS", flush=True)
    print("Acesso neste computador: http://127.0.0.1:5002", flush=True)
    print("Credenciais de ensaio: " + str(runtime / "acesso.local.txt"), flush=True)
    print("Entrada reservada para futuro Tunnel: 127.0.0.1:5003. Nenhum Tunnel criado.", flush=True)
    try:
        external_server.run()
    finally:
        external_server.close()
        local_server.close()
        external_server.task_dispatcher.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
