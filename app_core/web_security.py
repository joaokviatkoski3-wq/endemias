"""Perfil opt-in de acesso externo e fronteira de confianca do Tunnel local."""

import ipaddress
import hashlib
import hmac
import os

from flask import current_app, jsonify, redirect, request, session, url_for
from werkzeug.wrappers import Response

from app_core import auth
from app_core import db
from app_core import termos_uso


PUBLIC_ENDPOINTS = {"static", "auth.login", "auth.logout", "auth.esqueci_senha", "auth.recuperar_senha",
                    "formularios.sw_js", "formularios.manifest"}
TERMS_ENDPOINTS = {"auth.termos", "auth.aceitar_termos", "auth.minha_senha", "auth.presenca"}


def scope_session_key(app):
    scope = app.config.get("SESSION_KEY_SCOPE")
    if scope:
        if scope not in {"externo", "local"}:
            raise ValueError("Escopo de sessao invalido.")
        app.secret_key = hmac.new(app.secret_key, ("endemias-web:" + scope).encode(), hashlib.sha256).digest()


def external_defaults(env=None):
    env = os.environ if env is None else env
    enabled = str(env.get("ENDEMIAS_ACESSO_EXTERNO", "")).lower() in {"1", "true", "sim"}
    return {
        "ACESSO_EXTERNO": enabled,
        "TRUSTED_HOSTS": [h.strip() for h in env.get("ENDEMIAS_ALLOWED_HOSTS", "").split(",") if h.strip()] or None,
        "REQUIRE_SESSION_TOKEN": enabled,
        "TERMOS_USO_ENABLED": enabled or str(env.get("ENDEMIAS_TERMOS_USO", "")).lower() in {"1", "true", "sim"},
    }


class TunnelLocal:
    """Aceita metadados Cloudflare apenas do conector em loopback.

    O listener precisa ficar em 127.0.0.1. Nao usar ProxyFix nem confiar na
    primeira entrada de X-Forwarded-For, que pode ser fornecida pelo cliente.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") in {"/login", "/termos/aceitar", "/recuperar-senha"}:
            try:
                size = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                size = 16385
            if size > 16384:
                return Response("Formulario muito grande.", status=413)(environ, start_response)
        try:
            peer = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
            client = ipaddress.ip_address(environ.get("HTTP_CF_CONNECTING_IP", ""))
        except ValueError:
            return Response("Conexao externa invalida.", status=400)(environ, start_response)
        if not peer.is_loopback:
            return Response("Conector nao autorizado.", status=403)(environ, start_response)
        if environ.get("HTTP_X_FORWARDED_PROTO", "").lower() != "https":
            return Response("HTTPS obrigatorio.", status=400)(environ, start_response)
        environ["REMOTE_ADDR"] = str(client)
        environ["wsgi.url_scheme"] = "https"
        # Host original passa pela validacao TRUSTED_HOSTS do Flask.
        for key in list(environ):
            if key.startswith("HTTP_X_FORWARDED_") or key == "HTTP_FORWARDED":
                environ.pop(key, None)
        return self.app(environ, start_response)


def configure(app):
    if app.config.get("ACESSO_EXTERNO"):
        hosts = app.config.get("TRUSTED_HOSTS")
        if not hosts or any(h.startswith(".") or "*" in h or "/" in h for h in hosts):
            raise ValueError("Acesso externo exige ENDEMIAS_ALLOWED_HOSTS com nomes exatos.")
        app.config.update(
            DEBUG=False,
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_NAME="__Host-endemias",
            SESSION_COOKIE_PATH="/",
            SESSION_COOKIE_DOMAIN=None,
            SESSION_KEY_SCOPE="externo",
            REQUIRE_SESSION_TOKEN=True,
            TERMOS_USO_ENABLED=True,
            TRUST_PROXY_HEADERS=False,
            MAX_CONTENT_LENGTH=min(app.config["MAX_CONTENT_LENGTH"], 95 * 1024 * 1024),
            MAX_FORM_MEMORY_SIZE=512 * 1024,
            MAX_FORM_PARTS=200,
            CSP_REPORT_ONLY=False,
        )
        app.wsgi_app = TunnelLocal(app.wsgi_app)

    @app.before_request
    def require_authentication():
        if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        usuario = auth.usuario_atual(lambda sql, params=(): db.query_one(db.configured_target(current_app.config), sql, params))
        if usuario:
            if (app.config.get("TERMOS_USO_ENABLED") and request.endpoint not in TERMS_ENDPOINTS
                    and session.get("termo_aceito") != termos_uso.VERSAO + ":" + termos_uso.HASH):
                if termos_uso.aceitou(db.configured_target(app.config), usuario["id_usuario"]):
                    session["termo_aceito"] = termos_uso.VERSAO + ":" + termos_uso.HASH
                elif request.path.startswith("/api/"):
                    return jsonify({"erro": "Leia e confirme o termo de responsabilidade.", "termos_url": url_for("auth.termos")}), 403
                else:
                    return redirect(url_for("auth.termos"))
            return None
        if app.config.get("ACESSO_EXTERNO") and request.path.startswith("/api/"):
            return jsonify({"erro": "Entre no sistema para continuar."}), 401
        return redirect(url_for("auth.login", next=request.path))

    @app.after_request
    def private_response(response):
        if request.endpoint not in {"static", "formularios.sw_js", "formularios.manifest"}:
            if session.get("uid"):
                response.headers["X-Endemias-User"] = str(session["uid"])
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.vary.add("Cookie")
        if app.config.get("ACESSO_EXTERNO"):
            # Sem includeSubDomains: outros servicos do dominio sao independentes.
            response.headers["Strict-Transport-Security"] = "max-age=86400"
        return response
