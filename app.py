"""
Endemias - Sistema de Gestao Integrado v3
Setor de Endemias / Vigilancia Ambiental - Almirante Tamandare-PR

Servidor unico: rode em um computador e os demais acessam via http://IP:5000
"""
import logging
import logging.handlers
import os
from datetime import timedelta

from flask import Flask, current_app, has_app_context, request, session
from flask_wtf.csrf import CSRFProtect

from app_core import app_setup
from app_core import agentes as agentes_core
from app_core import auth as auth_core
from app_core import db as db_core
from app_core import import_history
from app_core import uploads as uploads_core
from app_core import utils as utils_core
from app_core import work_types
from blueprints.admin import bp as admin_bp
from blueprints.agenda import bp as agenda_bp
from blueprints.amostras_animais import bp as amostras_animais_bp
from blueprints.auth import bp as auth_bp
from blueprints.bri import bp as bri_bp
from blueprints.consultas import bp as consultas_bp
from blueprints.conta_ovos_sispncd import bp as conta_ovos_sispncd_bp
from blueprints.controle_pessoal import bp as controle_pessoal_bp
from blueprints.esporotricose import bp as esporotricose_bp
from blueprints.exportacoes import bp as exportacoes_bp
from blueprints.home import bp as home_bp
from blueprints.mapa import bp as mapa_bp
from blueprints.notificacoes import bp as notificacoes_bp
from blueprints.processar import bp as processar_bp
from blueprints.pontos_estrategicos import bp as pontos_estrategicos_bp
from blueprints.recolhimentos import bp as recolhimentos_bp
from blueprints.relatorio_agente import bp as relatorio_agente_bp


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_bool(env, name, default=False):
    value = env.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on", "sim")


def resolve_paths(env=None, base_dir=BASE_DIR):
    env = env or os.environ
    instance_dir = os.path.abspath(env.get("ENDEMIAS_INSTANCE_DIR", base_dir))
    return {
        "INSTANCE_DIR": instance_dir,
        "DB_PATH": os.path.abspath(env.get("ENDEMIAS_DB_PATH", os.path.join(instance_dir, "endemias.db"))),
        "CONFIG_PATH": os.path.abspath(env.get("ENDEMIAS_CONFIG_PATH", os.path.join(base_dir, "config.json"))),
        "UPLOAD_TEMP": os.path.abspath(env.get("ENDEMIAS_UPLOAD_TEMP", os.path.join(instance_dir, "uploads_temp"))),
        "LOG_PATH": os.path.abspath(env.get("ENDEMIAS_LOG_PATH", os.path.join(instance_dir, "endemias.log"))),
        "SECRET_KEY_PATH": os.path.abspath(env.get("ENDEMIAS_SECRET_KEY_PATH", os.path.join(instance_dir, "secret.key"))),
    }


PATHS = resolve_paths()
INSTANCE_DIR = PATHS["INSTANCE_DIR"]
DB_PATH = PATHS["DB_PATH"]
CONFIG_PATH = PATHS["CONFIG_PATH"]
UPLOAD_TEMP = PATHS["UPLOAD_TEMP"]
LOG_PATH = PATHS["LOG_PATH"]
SECRET_KEY_PATH = PATHS["SECRET_KEY_PATH"]
SESSION_COOKIE_SECURE_DEFAULT = _env_bool(os.environ, "ENDEMIAS_SESSION_COOKIE_SECURE", False)
TRUST_PROXY_HEADERS_DEFAULT = _env_bool(os.environ, "ENDEMIAS_TRUST_PROXY_HEADERS", False)
CSP_REPORT_ONLY_DEFAULT = _env_bool(os.environ, "ENDEMIAS_CSP_REPORT_ONLY", True)
CSP_ALLOW_INLINE_DEFAULT = _env_bool(os.environ, "ENDEMIAS_CSP_ALLOW_INLINE", True)

csrf = CSRFProtect()


# Validacao de upload de arquivos (mantem wrapper compativel com testes/codigo antigo).
def _validar_arquivo_xlsx(file_storage):
    return uploads_core.validar_arquivo_xlsx(file_storage)


def _configure_logging(log_path):
    root_logger = logging.getLogger()
    ja_configurado = any(
        isinstance(handler, logging.handlers.RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == os.path.abspath(log_path)
        for handler in root_logger.handlers
    )
    if not ja_configurado:
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(funcName)s: %(message)s"))
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)


def _configure_secret_key(flask_app, key_file):
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            flask_app.secret_key = f.read()
        return

    import secrets as _secrets

    key = _secrets.token_bytes(32)
    with open(key_file, "wb") as f:
        f.write(key)
    flask_app.secret_key = key
    print("[OK] secret.key gerado. Nunca compartilhe ou versione este arquivo.")


def _register_blueprints(flask_app):
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(agenda_bp)
    flask_app.register_blueprint(amostras_animais_bp)
    flask_app.register_blueprint(bri_bp)
    flask_app.register_blueprint(conta_ovos_sispncd_bp)
    flask_app.register_blueprint(controle_pessoal_bp)
    flask_app.register_blueprint(consultas_bp)
    flask_app.register_blueprint(esporotricose_bp)
    flask_app.register_blueprint(exportacoes_bp)
    flask_app.register_blueprint(home_bp)
    flask_app.register_blueprint(mapa_bp)
    flask_app.register_blueprint(notificacoes_bp)
    flask_app.register_blueprint(processar_bp)
    flask_app.register_blueprint(pontos_estrategicos_bp)
    flask_app.register_blueprint(recolhimentos_bp)
    flask_app.register_blueprint(relatorio_agente_bp)


STATUS_OPCOES = work_types.STATUS_OPTIONS
STATUS_CORES = work_types.STATUS_COLORS
TIPO_CORES = work_types.WORK_TYPE_COLORS
TIPO_LABELS = work_types.WORK_TYPE_LABELS
TIPOS_TRABALHO = work_types.WORK_TYPES
AGENDA_TIPO_COR = work_types.AGENDA_TYPE_COLORS
AGENDA_TIPO_LABEL = work_types.AGENDA_TYPE_LABELS
AGENDA_TIPOS = work_types.AGENDA_TYPES
AGENDA_FORM_LABEL = work_types.AGENDA_FORM_LABELS


# Banco e wrappers de compatibilidade.
def _db_path():
    if has_app_context():
        return current_app.config.get("DB_PATH", DB_PATH)
    return DB_PATH


def get_db():
    return db_core.connect(_db_path())


def q(sql, params=()):
    return db_core.query(_db_path(), sql, params)


def q1(sql, params=()):
    return db_core.query_one(_db_path(), sql, params)


def qval(sql, params=()):
    return db_core.scalar(_db_path(), sql, params)


def invalidar_cache_globals():
    app_setup.invalidar_cache_globals()


def garantir_tabela_importacoes(conn=None):
    return import_history.garantir_tabela_importacoes(get_db, conn)


def registrar_importacao(job_id, arquivos, status="upload", usuario=None):
    usuario = usuario or session.get("nome", "")
    return import_history.registrar_importacao(get_db, job_id, arquivos, status, usuario)


def atualizar_importacao(job_id, status, dry_run_ok=None, commit_ok=None, sumario=None, erro=None):
    return import_history.atualizar_importacao(
        get_db,
        job_id,
        status,
        dry_run_ok=dry_run_ok,
        commit_ok=commit_ok,
        sumario=sumario,
        erro=erro,
    )


def listar_importacoes_recentes(limite=10):
    return import_history.listar_importacoes_recentes(get_db, limite)


LOGIN_MAX_TENTATIVAS = auth_core.LOGIN_MAX_TENTATIVAS
LOGIN_JANELA_SEG = auth_core.LOGIN_JANELA_SEG
_login_tentativas = auth_core.login_tentativas


def _hash_legado(senha):
    return auth_core.hash_legado(senha)


def _hash(senha):
    return auth_core.hash_senha(senha)


def _verificar_senha(senha_digitada, hash_armazenado):
    return auth_core.verificar_senha(senha_digitada, hash_armazenado)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def login_required(f):
    return auth_core.login_required(f)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


def _url_segura(target):
    return auth_core.url_segura(target)


def _chave_login(usuario):
    return auth_core.chave_login(usuario)


def _login_bloqueado(chave, agora=None):
    return auth_core.login_bloqueado(chave, agora)


def _registrar_login_falha(chave, agora=None):
    return auth_core.registrar_login_falha(chave, agora)


def _limpar_login_falhas(chave):
    return auth_core.limpar_login_falhas(chave)


def hoje():
    return utils_core.hoje()


def data_n_dias(n=30):
    return utils_core.data_n_dias(n)


def data_ano():
    return utils_core.data_ano()


def safe_int(v, default=0):
    return utils_core.safe_int(v, default)


def request_int_arg(nome, default, minimo=None, maximo=None):
    return utils_core.bounded_int(request.args.get(nome), default, minimo, maximo)


def build_where(params_dict, alias_v="v", alias_l="l", alias_a="a"):
    return utils_core.build_visit_where(params_dict, alias_v, alias_l)


def create_app(config_overrides=None):
    os.makedirs(UPLOAD_TEMP, exist_ok=True)
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    flask_app = Flask(__name__, instance_path=INSTANCE_DIR)
    flask_app.config.update(
        DB_PATH=DB_PATH,
        CONFIG_PATH=CONFIG_PATH,
        UPLOAD_TEMP=UPLOAD_TEMP,
        INSTANCE_DIR=INSTANCE_DIR,
        LOG_PATH=LOG_PATH,
        SECRET_KEY_PATH=SECRET_KEY_PATH,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE_DEFAULT,
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
        WTF_CSRF_TIME_LIMIT=3600,
        WTF_CSRF_CHECK_DEFAULT=True,
        TRUST_PROXY_HEADERS=TRUST_PROXY_HEADERS_DEFAULT,
        CSP_REPORT_ONLY=CSP_REPORT_ONLY_DEFAULT,
        CSP_ALLOW_INLINE=CSP_ALLOW_INLINE_DEFAULT,
    )
    if config_overrides:
        flask_app.config.update(config_overrides)

    _configure_logging(flask_app.config["LOG_PATH"])
    _configure_secret_key(flask_app, flask_app.config["SECRET_KEY_PATH"])
    agentes_core.ensure_schema(flask_app.config["DB_PATH"])
    csrf.init_app(flask_app)

    flask_app.extensions["invalidar_cache_globals"] = invalidar_cache_globals
    _register_blueprints(flask_app)
    app_setup.register_error_handlers(flask_app)
    app_setup.register_template_filters(flask_app)
    app_setup.register_security_headers(flask_app)
    app_setup.register_context_processors(flask_app)
    return flask_app


app = create_app()


if __name__ == "__main__":
    import socket

    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except OSError:
        ip = "127.0.0.1"

    print("=" * 54)
    print("  ENDEMIAS - Sistema de Gestao Integrado v3")
    print("  Setor de Endemias - Almirante Tamandare-PR")
    print("=" * 54)
    print(f"\n  Banco de dados: {DB_PATH}")
    print("\n  Acesse no navegador:")
    print("    Este computador : http://localhost:5000")
    print(f"    Rede local      : http://{ip}:5000")
    print("\n  Para encerrar: Ctrl+C ou feche esta janela")
    print("=" * 54 + "\n")

    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
