"""Servidor Waitress. Nao instala servicos nem inicia tarefas automaticas."""

import argparse
import os


def server_options(config, env=None):
    env = os.environ if env is None else env
    threads = int(env.get("ENDEMIAS_THREADS", "16"))
    if not 4 <= threads <= 64:
        raise ValueError("ENDEMIAS_THREADS deve estar entre 4 e 64.")
    external = config.get("ACESSO_EXTERNO", False)
    host = env.get("ENDEMIAS_BIND", "127.0.0.1")
    if external and host != "127.0.0.1":
        raise ValueError("Acesso externo exige escuta em 127.0.0.1.")
    return dict(
        host=host, port=config["SERVER_PORT"], threads=threads,
        connection_limit=256, channel_timeout=120,
        max_request_body_size=config["MAX_CONTENT_LENGTH"],
        max_request_header_size=16384, clear_untrusted_proxy_headers=False,
        expose_tracebacks=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Endemias com servidor Waitress")
    parser.add_argument("--validar", action="store_true", help="Valida configuracao sem abrir porta")
    args = parser.parse_args(argv)
    from app import app
    options = server_options(app.config)
    if args.validar:
        print("Configuracao valida; nenhum servidor iniciado.")
        return 0
    from waitress import serve
    from app_core.version import APP_VERSION_LABEL
    print(f"{APP_VERSION_LABEL} | Waitress | {options['host']}:{options['port']} | {options['threads']} threads", flush=True)
    serve(app, **options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
