import logging
import time

from flask import current_app, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import modules as modules_core
from app_core import utils as utils_core
from app_core import version as version_core
from app_core import work_types


_glob_cache = {}
_CACHE_TTL = 60


def _cached_q(key, sql, params=()):
    now = time.monotonic()
    db_path = current_app.config["DB_PATH"]
    cache_key = (db_path, key)
    if cache_key not in _glob_cache or now - _glob_cache[cache_key][0] > _CACHE_TTL:
        _glob_cache[cache_key] = (now, db_core.query(db_path, sql, params))
    return _glob_cache[cache_key][1]


def invalidar_cache_globals():
    _glob_cache.clear()


def register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logging.warning("CSRFError: %s | IP: %s | URL: %s", e.description, request.remote_addr, request.url)
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"erro": "Token de seguranca expirado. Recarregue a pagina e tente novamente."}), 400
        return render_template("erro_csrf.html"), 400

    @app.errorhandler(404)
    def err404(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def err500(e):
        return render_template("500.html"), 500

    @app.errorhandler(403)
    def err403(e):
        return render_template("403.html"), 403


def register_template_filters(app):
    @app.template_filter("data_br")
    def filtro_data_br(valor):
        meses = [
            "janeiro",
            "fevereiro",
            "marco",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        try:
            from datetime import datetime as _dt

            d = _dt.strptime(str(valor)[:10], "%Y-%m-%d")
            return f"{d.day} de {meses[d.month - 1]} de {d.year}"
        except (ValueError, TypeError, AttributeError):
            return str(valor) if valor else "______"


def register_security_headers(app):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if current_app.config.get("CSP_REPORT_ONLY", True):
            response.headers.setdefault("Content-Security-Policy-Report-Only", csp)
        else:
            response.headers.setdefault("Content-Security-Policy", csp)
        return response


def register_context_processors(app):
    @app.context_processor
    def inject_globals():
        db_path = current_app.config["DB_PATH"]
        localidades = _cached_q("localidades", "SELECT nome FROM localidades ORDER BY nome")
        agentes = _cached_q("agentes", "SELECT nome FROM agentes ORDER BY nome")
        tipos_v = _cached_q("tipos_visita", "SELECT DISTINCT tipo FROM visitas WHERE tipo IS NOT NULL ORDER BY tipo")
        pendentes = db_core.scalar(
            db_path,
            "SELECT COUNT(*) FROM focos_positivos WHERE status_notificacao='pendente' AND gera_notificacao=1",
        )
        usuario = auth_core.usuario_atual(lambda sql, params=(): db_core.query_one(db_path, sql, params))
        return dict(
            localidades_glob=[r["nome"] for r in localidades],
            agentes_glob=[r["nome"] for r in agentes],
            tipos_glob=[r["tipo"] for r in tipos_v],
            nav_pendentes=pendentes,
            hoje=utils_core.hoje(),
            STATUS_OPCOES=work_types.STATUS_OPTIONS,
            STATUS_CORES=work_types.STATUS_COLORS,
            TIPO_CORES=work_types.WORK_TYPE_COLORS,
            TIPO_LABELS=work_types.WORK_TYPE_LABELS,
            TIPOS_TRABALHO=work_types.WORK_TYPES,
            AGENDA_TIPO_CORES=work_types.AGENDA_TYPE_COLORS,
            AGENDA_TIPO_LABELS=work_types.AGENDA_TYPE_LABELS,
            AGENDA_TIPOS=work_types.AGENDA_TYPES,
            AGENDA_FORM_LABELS=work_types.AGENDA_FORM_LABELS,
            usuario_atual=usuario,
            topbar_modules=modules_core.visible_modules(usuario, area="topbar"),
            sidebar_groups=modules_core.grouped_modules(modules_core.visible_modules(usuario, area="sidebar")),
            home_modules=modules_core.visible_modules(usuario, area="home"),
            APP_VERSION=version_core.APP_VERSION,
            APP_VERSION_DATE=version_core.APP_VERSION_DATE,
            APP_VERSION_LABEL=version_core.APP_VERSION_LABEL,
        )
