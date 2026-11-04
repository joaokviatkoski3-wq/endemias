"""Servidor Waitress. Nao instala servicos nem inicia tarefas automaticas."""

import argparse
import os
import ipaddress


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


def local_options(config, env=None):
    env = os.environ if env is None else env
    if str(env.get("ENDEMIAS_ACESSO_LOCAL", "")).lower() not in {"1", "true", "sim"}:
        return None
    if not config.get("ACESSO_EXTERNO"):
        raise ValueError("Entrada local adicional exige perfil externo.")
    bind = env.get("ENDEMIAS_LOCAL_BIND", "")
    try:
        address = ipaddress.ip_address(bind)
    except ValueError as exc:
        raise ValueError("Informe ENDEMIAS_LOCAL_BIND com o IP privado da interface local.") from exc
    if address.version != 4 or address.is_unspecified or address.is_multicast or not (address.is_private or address.is_loopback):
        raise ValueError("Entrada local exige endereco IPv4 privado explicito.")
    port = int(env.get("ENDEMIAS_LOCAL_PORT", "5000"))
    tunnel_port = int(env.get("ENDEMIAS_TUNNEL_PORT", "5001"))
    if not 1 <= port <= 65535 or not 1 <= tunnel_port <= 65535 or port == tunnel_port:
        raise ValueError("Portas local/Tunnel devem ser validas e diferentes.")
    return {"bind": str(address), "port": port, "tunnel_port": tunnel_port}


def local_application(external, bind):
    from app import create_app
    # Mesmos recursos e mesmo processo: locks de backup/importacao continuam comuns.
    config = dict(external.config)
    config.update(
        ACESSO_EXTERNO=False, SESSION_KEY_SCOPE="local",
        SESSION_COOKIE_SECURE=False, SESSION_COOKIE_NAME=("ambiental_local" if external.config.get("SETOR")=="ambiental" else "endemias_local"),
        TRUSTED_HOSTS=list(dict.fromkeys([bind, "127.0.0.1", "localhost"])), REQUIRE_SESSION_TOKEN=True, TERMOS_USO_ENABLED=True,
        TRUST_PROXY_HEADERS=False, MAX_CONTENT_LENGTH=220 * 1024 * 1024,
    )
    return create_app(config)


def create_dual_servers(external, local, env=None):
    """Duas escutas com o mesmo pool e mapa de conexoes do Waitress."""
    from waitress import create_server
    env = os.environ if env is None else env
    settings = local_options(external.config, env)
    if settings is None:
        raise ValueError("Entrada local adicional nao configurada.")
    options = server_options(external.config, env)
    options["port"] = settings["tunnel_port"]
    shared_map = {}
    from app_core import dominios
    external_server = create_server(dominios.application(external), map=shared_map, **options)
    try:
        options.pop("host")
        options.pop("port")
        addresses = [settings["bind"]]
        if settings["bind"] != "127.0.0.1":
            addresses.append("127.0.0.1")
        options.update(listen=" ".join(f"{address}:{settings['port']}" for address in addresses), max_request_body_size=local.config["MAX_CONTENT_LENGTH"])
        local_server = create_server(local, map=shared_map, _dispatcher=external_server.task_dispatcher, **options)
        if external.config.get('SETORES_ENABLED'):
            port=int(env.get('ENDEMIAS_AMBIENTAL_LOCAL_PORT','5004'))
            if not 1<=port<=65535 or port in {settings['port'],settings['tunnel_port']}:
                raise ValueError('Porta local Ambiental invalida ou em conflito.')
            ambiental=local_application(dominios.ambiental_application(external),settings['bind'])
            options['listen']=' '.join(f'{address}:{port}' for address in addresses)
            ambiental_server=create_server(ambiental,map=shared_map,_dispatcher=external_server.task_dispatcher,**options)
            local_server=ServidoresLocais(local_server,ambiental_server)
    except Exception:
        for channel in list(shared_map.values()):
            channel.close()
        external_server.task_dispatcher.shutdown()
        raise
    return external_server, local_server


class ServidoresLocais:
    def __init__(self,*servers):self.servers=servers
    def close(self):
        for server in self.servers:server.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Endemias com servidor Waitress")
    parser.add_argument("--validar", action="store_true", help="Valida configuracao sem abrir porta")
    args = parser.parse_args(argv)
    from app import app
    options = server_options(app.config)
    settings = local_options(app.config)
    if args.validar:
        print("Configuracao valida; nenhum servidor iniciado.")
        return 0
    if settings:
        local = local_application(app, settings["bind"])
        external_server, local_server = create_dual_servers(app, local)
        print(f"Entrada local: http://{settings['bind']}:{settings['port']} | Tunnel: 127.0.0.1:{settings['tunnel_port']}", flush=True)
        try:
            external_server.run()
        finally:
            external_server.close()
            local_server.close()
            external_server.task_dispatcher.shutdown()
        return 0
    from waitress import serve
    from app_core.version import APP_VERSION_LABEL
    print(f"{APP_VERSION_LABEL} | Waitress | {options['host']}:{options['port']} | {options['threads']} threads", flush=True)
    from app_core import dominios
    serve(dominios.application(app), **options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
