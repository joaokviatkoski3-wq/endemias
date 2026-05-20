"""
Endemias â€” Sistema de GestÃ£o Integrado  v3
Setor de Endemias / VigilÃ¢ncia Ambiental â€” Almirante TamandarÃ©-PR

Servidor Ãºnico: rode em um computador e os demais acessam via http://IP:5000
"""
import os, sqlite3, json
import logging
import logging.handlers
from datetime import date, datetime, timedelta

from flask import (Flask, render_template, request, redirect, url_for,
                   send_file, jsonify, abort, session)
from flask_wtf.csrf import CSRFProtect, CSRFError

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import import_history
from app_core import modules as modules_core
from app_core import uploads as uploads_core
from app_core import utils as utils_core
from app_core import version as version_core
from app_core import work_types
from blueprints.admin import bp as admin_bp
from blueprints.agenda import bp as agenda_bp
from blueprints.conta_ovos_sispncd import bp as conta_ovos_sispncd_bp
from blueprints.processar import bp as processar_bp

# â”€â”€ ValidaÃ§Ã£o de upload de arquivos (SEC-04) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# xlsx Ã© um ZIP internamente â€” assinatura PK\x03\x04 nos primeiros bytes
def _validar_arquivo_xlsx(file_storage):
    return uploads_core.validar_arquivo_xlsx(file_storage)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "endemias.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MODELO_PATH = os.path.join(BASE_DIR, "modelo_notificacao.txt")
SAIDA_DIR   = os.path.join(BASE_DIR, "notificacoes_geradas")
UPLOAD_TEMP = os.path.join(BASE_DIR, "uploads_temp")

os.makedirs(SAIDA_DIR, exist_ok=True)
os.makedirs(UPLOAD_TEMP, exist_ok=True)

app = Flask(__name__)
app.config["DB_PATH"] = DB_PATH
app.config["CONFIG_PATH"] = CONFIG_PATH
app.config["UPLOAD_TEMP"] = UPLOAD_TEMP

# â”€â”€ Logging estruturado em arquivo rotativo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_log_path = os.path.join(BASE_DIR, "endemias.log")
_log_handler = logging.handlers.RotatingFileHandler(
    _log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(funcName)s: %(message)s"
))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.WARNING)

# â”€â”€ Secret key: lida de arquivo local, gerada automaticamente se nÃ£o existir â”€â”€
_KEY_FILE = os.path.join(BASE_DIR, "secret.key")
if os.path.exists(_KEY_FILE):
    with open(_KEY_FILE, "rb") as _f:
        app.secret_key = _f.read()
else:
    import secrets as _secrets
    _k = _secrets.token_bytes(32)
    with open(_KEY_FILE, "wb") as _f:
        _f.write(_k)
    app.secret_key = _k
    print("[OK] secret.key gerado. Nunca compartilhe ou versione este arquivo.")

# â”€â”€ ConfiguraÃ§Ãµes de sessÃ£o segura â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"]    = True
app.config["SESSION_COOKIE_SAMESITE"]   = "Lax"

# Limite simples de tentativas de login por IP+usuario.
# Como o sistema roda em processo unico na rede local, memoria atende bem sem nova dependencia.
LOGIN_MAX_TENTATIVAS = auth_core.LOGIN_MAX_TENTATIVAS
LOGIN_JANELA_SEG     = auth_core.LOGIN_JANELA_SEG
_login_tentativas    = auth_core.login_tentativas

# â”€â”€ CSRF Protection (SEC-03) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Protege todos os formulÃ¡rios POST contra ataques de cross-site request forgery.
# Rotas de SSE (stream) sÃ£o isentas automaticamente (mÃ©todo GET).
# Rotas de API JSON que recebem o header X-CSRFToken tambÃ©m sÃ£o validadas.
app.config["WTF_CSRF_TIME_LIMIT"]   = 3600  # token vÃ¡lido por 1h
app.config["WTF_CSRF_CHECK_DEFAULT"] = True
csrf = CSRFProtect(app)
app.register_blueprint(admin_bp)

# Isentar rotas que nÃ£o precisam de CSRF (SSE â€” usam GET, sem estado)
# Nota: rotas GET nÃ£o sÃ£o afetadas pelo CSRF de qualquer forma.
# As Ãºnicas isenÃ§Ãµes necessÃ¡rias sÃ£o endpoints chamados por sistemas externos.
# Por ora, nenhuma isenÃ§Ã£o â€” todos os POST sÃ£o protegidos.

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Retorna erro amigÃ¡vel quando o token CSRF falha ou expira."""
    logging.warning(f"CSRFError: {e.description} | IP: {request.remote_addr} | URL: {request.url}")
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"erro": "Token de seguranÃ§a expirado. Recarregue a pÃ¡gina e tente novamente."}), 400
    return render_template("erro_csrf.html"), 400


@app.template_filter("data_br")
def filtro_data_br(valor):
    meses = ["janeiro","fevereiro","marÃ§o","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(str(valor)[:10], "%Y-%m-%d")
        return f"{d.day} de {meses[d.month-1]} de {d.year}"
    except (ValueError, TypeError, AttributeError):
        return str(valor) if valor else "______"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CONSTANTES UI
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

STATUS_OPCOES = work_types.STATUS_OPTIONS
STATUS_CORES = work_types.STATUS_COLORS
TIPO_CORES = work_types.WORK_TYPE_COLORS
TIPO_LABELS = work_types.WORK_TYPE_LABELS
TIPOS_TRABALHO = work_types.WORK_TYPES
AGENDA_TIPO_COR = work_types.AGENDA_TYPE_COLORS
AGENDA_TIPO_LABEL = work_types.AGENDA_TYPE_LABELS
AGENDA_TIPOS = work_types.AGENDA_TYPES
AGENDA_FORM_LABEL = work_types.AGENDA_FORM_LABELS
DURATION_WORK_TYPE_CODE = work_types.primary_duration_work_type_code()

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  BANCO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def get_db():
    return db_core.connect(DB_PATH)

def q(sql, params=()):
    return db_core.query(DB_PATH, sql, params)

def q1(sql, params=()):
    return db_core.query_one(DB_PATH, sql, params)

def qval(sql, params=()):
    return db_core.scalar(DB_PATH, sql, params)

# FIX ARQ-01: Cache simples com TTL para evitar queries repetidas em todo request
# Localidades e agentes mudam raramente â€” cache de 60s Ã© seguro
import time as _time
_glob_cache: dict = {}
_CACHE_TTL = 60  # segundos

def _cached_q(key, sql, params=()):
    now = _time.monotonic()
    if key not in _glob_cache or now - _glob_cache[key][0] > _CACHE_TTL:
        _glob_cache[key] = (now, q(sql, params))
    return _glob_cache[key][1]

def invalidar_cache_globals():
    """Chamar apÃ³s ETL ou apÃ³s criar/editar agentes e localidades."""
    _glob_cache.clear()

app.extensions["invalidar_cache_globals"] = invalidar_cache_globals
app.register_blueprint(agenda_bp)
app.register_blueprint(conta_ovos_sispncd_bp)
app.register_blueprint(processar_bp)

def garantir_tabela_importacoes(conn=None):
    return import_history.garantir_tabela_importacoes(get_db, conn)

def registrar_importacao(job_id, arquivos, status="upload", usuario=None):
    usuario = usuario or session.get("nome", "")
    return import_history.registrar_importacao(get_db, job_id, arquivos, status, usuario)

def atualizar_importacao(job_id, status, dry_run_ok=None, commit_ok=None, sumario=None, erro=None):
    return import_history.atualizar_importacao(
        get_db, job_id, status, dry_run_ok=dry_run_ok,
        commit_ok=commit_ok, sumario=sumario, erro=erro,
    )

def listar_importacoes_recentes(limite=10):
    return import_history.listar_importacoes_recentes(get_db, limite)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  AUTH
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# â”€â”€ FunÃ§Ãµes de hash de senha â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# COMPATIBILIDADE: hashes antigos (SHA-256 puro) ainda funcionam para login,
# mas ao salvar nova senha sempre usa pbkdf2:sha256 com salt.

def _hash_legado(senha):
    """SHA-256 sem salt â€” usado APENAS para verificar hashes antigos."""
    return auth_core.hash_legado(senha)

def _hash(senha):
    """Gera hash seguro com pbkdf2:sha256 e salt aleatÃ³rio (werkzeug)."""
    return auth_core.hash_senha(senha)

def _verificar_senha(senha_digitada, hash_armazenado):
    """
    Verifica senha contra hash armazenado.
    Aceita tanto hashes werkzeug (pbkdf2:sha256:...) quanto hashes legados (SHA-256 puro).
    Ao autenticar com hash legado, atualiza automaticamente para hash seguro.
    Retorna (ok: bool, novo_hash: str|None) â€” novo_hash != None significa que deve ser salvo.
    """
    return auth_core.verificar_senha(senha_digitada, hash_armazenado)
        # Hash moderno werkzeug
        # Hash legado SHA-256 â€” verificar e fazer upgrade

def usuario_atual():
    return auth_core.usuario_atual(q1)

def login_required(f):
    return auth_core.login_required(f)

def nivel_min(nivel):
    """Decorator: exige nÃ­vel mÃ­nimo (admin > operador > visualizador)."""
    return auth_core.nivel_min(nivel, usuario_atual)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def hoje():             return utils_core.hoje()
def data_n_dias(n=30):  return utils_core.data_n_dias(n)
def data_ano():         return utils_core.data_ano()

def safe_int(v, default=0):
    return utils_core.safe_int(v, default)

def request_int_arg(nome, default, minimo=None, maximo=None):
    return utils_core.bounded_int(request.args.get(nome), default, minimo, maximo)

def build_where(params_dict, alias_v="v", alias_l="l", alias_a="a"):
    where, params = "WHERE 1=1", []
    d_ini = params_dict.get("d_ini") or data_n_dias(365)
    d_fim = params_dict.get("d_fim") or hoje()
    where += f" AND {alias_v}.data BETWEEN ? AND ?"; params += [d_ini, d_fim]

    def getlist(k):
        if hasattr(params_dict, "getlist"): return params_dict.getlist(k)
        v = params_dict.get(k, [])
        return v if isinstance(v, list) else [v]

    tipos = getlist("tipo"); locs = getlist("localidade"); ags = getlist("agente")

    if tipos:
        where += f" AND {alias_v}.tipo IN ({','.join('?'*len(tipos))})"; params += tipos
    if locs:
        where += f" AND {alias_l}.nome IN ({','.join('?'*len(locs))})"; params += locs
    if ags:
        cond = " OR ".join([
            f"EXISTS(SELECT 1 FROM visita_agentes va2 JOIN agentes a2 ON a2.id_agente=va2.id_agente "
            f"WHERE va2.id_visita={alias_v}.id_visita AND a2.nome=?)"
            for _ in ags
        ])
        where += f" AND ({cond})"; params += ags

    return where, params

def ler_modelo():
    return utils_core.ler_modelo(MODELO_PATH)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CONTEXTO GLOBAL
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.context_processor
def inject_globals():
    # FIX ARQ-01: localidades, agentes e tipos_v sÃ£o cacheados por 60s
    # pendentes sempre Ã© consultado em real-time (muda com frequÃªncia)
    localidades = _cached_q("localidades", "SELECT nome FROM localidades ORDER BY nome")
    agentes     = _cached_q("agentes",     "SELECT nome FROM agentes ORDER BY nome")
    tipos_v     = _cached_q("tipos_visita","SELECT DISTINCT tipo FROM visitas WHERE tipo IS NOT NULL ORDER BY tipo")
    pendentes   = qval("SELECT COUNT(*) FROM focos_positivos WHERE status_notificacao='pendente' AND gera_notificacao=1")
    u           = usuario_atual()
    return dict(
        localidades_glob=[r["nome"] for r in localidades],
        agentes_glob    =[r["nome"] for r in agentes],
        tipos_glob      =[r["tipo"] for r in tipos_v],
        nav_pendentes   =pendentes,
        hoje            =hoje(),
        STATUS_OPCOES   =STATUS_OPCOES,
        STATUS_CORES    =STATUS_CORES,
        TIPO_CORES      =TIPO_CORES,
        TIPO_LABELS     =TIPO_LABELS,
        TIPOS_TRABALHO  =TIPOS_TRABALHO,
        AGENDA_TIPO_CORES=AGENDA_TIPO_COR,
        AGENDA_TIPO_LABELS=AGENDA_TIPO_LABEL,
        AGENDA_TIPOS    =AGENDA_TIPOS,
        AGENDA_FORM_LABELS=AGENDA_FORM_LABEL,
        usuario_atual   =u,
        topbar_modules  = modules_core.visible_modules(u, area="topbar"),
        sidebar_groups  = modules_core.grouped_modules(modules_core.visible_modules(u, area="sidebar")),
        home_modules    = modules_core.visible_modules(u, area="home"),
        APP_VERSION      = version_core.APP_VERSION,
        APP_VERSION_DATE = version_core.APP_VERSION_DATE,
        APP_VERSION_LABEL= version_core.APP_VERSION_LABEL,
    )

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ROTAS â€” AUTH
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _url_segura(target):
    """Retorna True se a URL alvo Ã© do prÃ³prio servidor (previne open redirect)."""
    return auth_core.url_segura(target)

def _chave_login(usuario):
    return auth_core.chave_login(usuario)

def _login_bloqueado(chave, agora=None):
    return auth_core.login_bloqueado(chave, agora)

def _registrar_login_falha(chave, agora=None):
    return auth_core.registrar_login_falha(chave, agora)

def _limpar_login_falhas(chave):
    return auth_core.limpar_login_falhas(chave)


@app.route("/login", methods=["GET", "POST"])
@csrf.exempt   # login nÃ£o tem sessÃ£o prÃ©via para validar token â€” protegido pelo rate limit da senha
def login():
    if session.get("uid"):
        return redirect(url_for("home"))
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha   = request.form.get("senha", "")
        chave   = _chave_login(usuario)
        if _login_bloqueado(chave):
            logging.warning(f"Login bloqueado por excesso de tentativas | usuario={usuario} | IP={request.remote_addr}")
            return render_template("login.html", erro="Muitas tentativas incorretas. Aguarde alguns minutos e tente novamente."), 429
        u = q1("SELECT * FROM usuarios WHERE usuario=? AND ativo=1", (usuario,))
        if u:
            ok, novo_hash = _verificar_senha(senha, u["senha_hash"])
            if ok:
                _limpar_login_falhas(chave)
                session.permanent = True          # respeita PERMANENT_SESSION_LIFETIME
                session["uid"]    = u["id_usuario"]
                session["nivel"]  = u["nivel"]
                session["nome"]   = u["nome"]
                # Upgrade silencioso de hash legado para pbkdf2
                if novo_hash:
                    try:
                        conn = get_db()
                        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                                     (novo_hash, u["id_usuario"]))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                # Redirecionar com seguranÃ§a (sem open redirect)
                dest = request.args.get("next", "")
                if not dest or not _url_segura(dest):
                    dest = url_for("home")
                return redirect(dest)
        erro = "UsuÃ¡rio ou senha incorretos."
        _registrar_login_falha(chave)
    return render_template("login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/minha-senha", methods=["GET", "POST"])
@login_required
def minha_senha():
    erro = ok = None
    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova  = request.form.get("nova", "")
        conf  = request.form.get("confirmar", "")
        u = q1("SELECT * FROM usuarios WHERE id_usuario=?", (session["uid"],))
        senha_ok, _ = _verificar_senha(atual, u["senha_hash"])
        if not senha_ok:
            erro = "Senha atual incorreta."
        elif len(nova) < 6:
            erro = "A nova senha deve ter ao menos 6 caracteres."
        elif nova != conf:
            erro = "As senhas nÃ£o coincidem."
        else:
            conn = get_db()
            conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                         (_hash(nova), session["uid"]))
            conn.commit(); conn.close()
            ok = "Senha alterada com sucesso."
    return render_template("minha_senha.html", erro=erro, ok=ok)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ROTAS â€” PÃGINAS PRINCIPAIS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/")
@login_required
def home():
    conn = get_db()
    try:
        ano_ini  = data_ano()
        kpis = {
            "visitas_hoje":     conn.execute("SELECT COUNT(*) FROM visitas WHERE data=?", (hoje(),)).fetchone()[0],
            "visitas_ano":      conn.execute("SELECT COUNT(*) FROM visitas WHERE data>=?", (ano_ini,)).fetchone()[0],
            "focos_pendentes":  conn.execute("SELECT COUNT(*) FROM focos_positivos WHERE status_notificacao='pendente' AND gera_notificacao=1").fetchone()[0],
            "agentes_ativos":   conn.execute("SELECT COUNT(DISTINCT id_agente) FROM visita_agentes va JOIN visitas v ON v.id_visita=va.id_visita WHERE v.data>=?", (data_n_dias(30),)).fetchone()[0],
            "coletas_total":    conn.execute("SELECT COUNT(*) FROM coletas").fetchone()[0],
            "positivos_aeg":    conn.execute("SELECT COUNT(*) FROM resultados_laboratorio WHERE aegypt_larvas>0 OR aegypt_pupas>0 OR aegypt_exuvias>0 OR aegypt_adulto>0").fetchone()[0],
        }
        atividade   = conn.execute("SELECT data, COUNT(*) as total FROM visitas WHERE data>=? GROUP BY data ORDER BY data DESC LIMIT 14", (data_n_dias(14),)).fetchall()
        dist_tipo   = conn.execute("SELECT tipo, COUNT(*) as total FROM visitas WHERE data>=? GROUP BY tipo ORDER BY total DESC", (ano_ini,)).fetchall()
        focos_rec   = conn.execute("""
            SELECT f.*, l.nome as localidade_nome FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
            WHERE f.gera_notificacao=1 ORDER BY f.processado_em DESC LIMIT 5
        """).fetchall()
    finally:
        conn.close()
    return render_template("home.html",
        kpis=kpis,
        atividade=[dict(r) for r in atividade],
        dist_tipo=[dict(r) for r in dist_tipo],
        focos_recentes=[dict(r) for r in focos_rec],
    )

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html",
        d_ini=request.args.get("d_ini", data_n_dias(90)),
        d_fim=request.args.get("d_fim", hoje()),
        tipos_sel=request.args.getlist("tipo"),
        locs_sel=request.args.getlist("localidade"),
        ags_sel=request.args.getlist("agente"),
    )

@app.route("/laboratorio")
@login_required
def laboratorio():
    return render_template("laboratorio.html",
        d_ini=request.args.get("d_ini", data_n_dias(90)),
        d_fim=request.args.get("d_fim", hoje()),
    )

@app.route("/visitas")
@login_required
def visitas():
    return render_template("visitas.html",
        d_ini=request.args.get("d_ini", data_n_dias(7)),
        d_fim=request.args.get("d_fim", hoje()),
        tipos_sel=request.args.getlist("tipo"),
        locs_sel=request.args.getlist("localidade"),
        ags_sel=request.args.getlist("agente"),
    )

@app.route("/relatorio-agente")
@login_required
def relatorio_agente():
    return render_template("relatorio_agente.html",
        agente_sel=request.args.get("agente", ""),
        d_ini=request.args.get("d_ini", data_n_dias(30)),
        d_fim=request.args.get("d_fim", hoje()),
    )

@app.route("/esporotricose")
@login_required
def esporotricose():
    return render_template("esporotricose.html")

# â”€â”€ COD-03: lÃ³gica de dados do relatÃ³rio de agente extraÃ­da aqui â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Usada tanto pela rota PDF quanto pela API, sem duplicaÃ§Ã£o.
def _obter_dados_relatorio_agente(nome, d_ini, d_fim):
    """
    Consulta todas as mÃ©tricas de um agente num perÃ­odo.
    Retorna dict pronto para render_template ou jsonify.
    """
    conn = get_db()
    p = [nome, d_ini, d_fim]
    base_w = (
        "FROM visitas v "
        "JOIN visita_agentes va ON va.id_visita=v.id_visita "
        "JOIN agentes a ON a.id_agente=va.id_agente "
        "LEFT JOIN localidades l ON l.id_localidade=v.id_localidade "
        "WHERE a.nome=? AND v.data BETWEEN ? AND ?"
    )

    try:
        totais = conn.execute(f"""SELECT
            COUNT(DISTINCT v.id_visita) as total, COUNT(DISTINCT v.data) as dias,
            COUNT(DISTINCT v.quarteirao) as quarteiroes,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
            {base_w}""", p).fetchone()

        por_tipo = conn.execute(f"""SELECT v.tipo,
            COUNT(DISTINCT v.id_visita) as total,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
            {base_w} GROUP BY v.tipo ORDER BY total DESC""", p).fetchall()

        por_loc = conn.execute(
            f"SELECT l.nome as localidade, COUNT(DISTINCT v.id_visita) as total "
            f"{base_w} GROUP BY l.nome ORDER BY total DESC", p
        ).fetchall()

        por_dia = conn.execute(
            f"SELECT v.data, COUNT(DISTINCT v.id_visita) as total "
            f"{base_w} GROUP BY v.data ORDER BY v.data", p
        ).fetchall()

        evolucao = conn.execute(
            f"SELECT strftime('%Y-%m-%d',v.data,'weekday 0','-6 days') as semana, "
            f"COUNT(DISTINCT v.id_visita) as total {base_w} GROUP BY semana ORDER BY semana", p
        ).fetchall()

        dep = conn.execute("""
            SELECT SUM(d.inspecionado) as insp, SUM(d.eliminado) as elim, SUM(d.tratado) as trat
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            LEFT JOIN depositos_inspecionados d ON d.id_visita=v.id_visita
            WHERE a.nome=? AND v.data BETWEEN ? AND ?""", p).fetchone()

        col = conn.execute("""
            SELECT COUNT(DISTINCT c.id_coleta) as total,
                COUNT(DISTINCT CASE WHEN rl.aegypt_larvas>0 OR rl.aegypt_pupas>0
                    OR rl.aegypt_exuvias>0 OR rl.aegypt_adulto>0 THEN c.id_coleta END) as pos_aeg,
                COUNT(DISTINCT CASE WHEN rl.albopictus_larvas>0 OR rl.albopictus_pupas>0
                    THEN c.id_coleta END) as pos_alb
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            LEFT JOIN coletas c ON c.id_visita=v.id_visita
            LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
            WHERE a.nome=? AND v.data BETWEEN ? AND ?""", p).fetchone()

        tbo_raw = conn.execute("""
            SELECT
                CASE WHEN LOWER(sub.visita) IN ('normal','recuperado') THEN 'acessados'
                     ELSE 'nao_acessados' END as grupo,
                COUNT(*) as n, ROUND(AVG(dur),1) as media,
                ROUND(MIN(dur),1) as minimo, ROUND(MAX(dur),1) as maximo
            FROM (SELECT v.visita,
                  (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                  FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
                  JOIN agentes a ON a.id_agente=va.id_agente
                  WHERE a.nome=? AND v.data BETWEEN ? AND ? AND v.tipo=?
                  AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL) sub
            WHERE dur BETWEEN 1 AND 240 GROUP BY grupo""", p + [DURATION_WORK_TYPE_CODE]).fetchall()

        por_periodo_raw = conn.execute(f"""SELECT
            CASE WHEN v.hora_inicio < '12:00' THEN 'manha' ELSE 'tarde' END as periodo,
            COUNT(DISTINCT v.id_visita) as total,
            COUNT(DISTINCT v.data) as dias_periodo
            {base_w} AND v.hora_inicio IS NOT NULL GROUP BY periodo""", p).fetchall()

        media_geral_raw = conn.execute("""
            SELECT
                COUNT(DISTINCT v.id_visita) as total,
                COUNT(DISTINCT v.data) as dias,
                COUNT(DISTINCT v.quarteirao) as quarteiroes,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados,
                COUNT(DISTINCT a.id_agente) as num_agentes
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            WHERE v.data BETWEEN ? AND ?""", [d_ini, d_fim]).fetchone()
    finally:
        conn.close()

    # â”€â”€ Calcular mÃ©tricas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    totais_d = dict(totais) if totais else {}
    dep_d    = dict(dep)    if dep    else {}
    col_d    = dict(col)    if col    else {}
    tv   = safe_int(totais_d.get("total", 0))
    dias = safe_int(totais_d.get("dias",  0))
    tc   = safe_int(col_d.get("total", 0))
    ta   = safe_int(col_d.get("pos_aeg", 0))

    por_periodo = {}
    for r in por_periodo_raw:
        rd = dict(r)
        dias_p = safe_int(rd.get("dias_periodo")) or 1
        por_periodo[rd["periodo"]] = {
            "total": safe_int(rd.get("total", 0)),
            "media": round(safe_int(rd.get("total", 0)) / dias_p, 1),
        }

    comparacao = {}
    if media_geral_raw:
        mg   = dict(media_geral_raw)
        n_ag = safe_int(mg.get("num_agentes")) or 1
        tv_g = safe_int(mg.get("total", 0))
        dias_g = safe_int(mg.get("dias", 0)) or 1
        comparacao = {
            "media_total":       round(tv_g / n_ag, 1),
            "media_dia":         round((tv_g / n_ag) / dias_g, 1),
            "media_normais":     round(safe_int(mg.get("normais", 0)) / n_ag, 1),
            "media_fechados":    round(safe_int(mg.get("fechados", 0)) / n_ag, 1),
            "media_recuperados": round(safe_int(mg.get("recuperados", 0)) / n_ag, 1),
            "media_recusados":   round(safe_int(mg.get("recusados", 0)) / n_ag, 1),
            "num_agentes":       n_ag,
        }

    return {
        "agente": nome, "d_ini": d_ini, "d_fim": d_fim,
        "totais": totais_d,
        "por_tipo":  [dict(r) for r in por_tipo],
        "por_loc":   [dict(r) for r in por_loc],
        "por_dia":   [dict(r) for r in por_dia],
        "evolucao":  [dict(r) for r in evolucao],
        "dep":       dep_d,
        "col":       col_d,
        "tbo_por_grupo": {r["grupo"]: dict(r) for r in tbo_raw},
        "taxa_normal": round(safe_int(totais_d.get("normais", 0)) / tv * 100, 1) if tv else 0,
        "media_dia":   round(tv / dias, 1) if dias else 0,
        "por_periodo": por_periodo,
        "comparacao":  comparacao,
        # campos extras para compatibilidade com API JSON
        "totais_api": {
            "total": tv, "dias": dias,
            "media_dia": round(tv / dias, 1) if dias else 0,
            "quarteiroes": safe_int(totais_d.get("quarteiroes", 0)),
            "normais": safe_int(totais_d.get("normais", 0)),
            "fechados": safe_int(totais_d.get("fechados", 0)),
            "recuperados": safe_int(totais_d.get("recuperados", 0)),
            "recusados": safe_int(totais_d.get("recusados", 0)),
            "inspecionados": safe_int(dep_d.get("insp", 0)),
            "eliminados": safe_int(dep_d.get("elim", 0)),
            "tratados": safe_int(dep_d.get("trat", 0)),
        },
        "coletas_api": {
            "total": tc, "pos_aeg": ta,
            "pos_alb": safe_int(col_d.get("pos_alb", 0)),
            "indice": round(ta / tc * 100, 1) if tc else 0,
        },
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

@app.route("/relatorio-agente/pdf")
@login_required
def relatorio_agente_pdf():
    """
    COD-03: Rota PDF usa _obter_dados_relatorio_agente() compartilhada com a API.
    Antes tinha ~130 linhas de queries duplicadas aqui â€” agora sÃ£o 8 linhas.
    """
    nome  = request.args.get("agente", "")
    d_ini = request.args.get("d_ini", data_n_dias(30))
    d_fim = request.args.get("d_fim", hoje())
    if not nome:
        return "Agente nÃ£o informado.", 400
    try:
        dados = _obter_dados_relatorio_agente(nome, d_ini, d_fim)
    except Exception as e:
        logging.exception("Erro em relatorio_agente_pdf")
        return f"Erro ao gerar relatÃ³rio: {e}", 500
    return render_template("relatorio_agente_pdf.html", **dados)

# â”€â”€ NOTIFICAÃ‡Ã•ES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route("/notificacoes")
@login_required
def notificacoes():
    fs = request.args.getlist("status")
    ft = request.args.getlist("tipo")
    fl = request.args.getlist("localidade")
    fa = request.args.getlist("agente")
    d_ini   = request.args.get("d_ini", "")
    d_fim   = request.args.get("d_fim", "")
    busca   = request.args.get("busca", "").strip()
    pagina  = request_int_arg("pagina", 1, minimo=1)
    pp_str  = request.args.get("por_pagina", "50")
    pp      = None if pp_str == "tudo" else safe_int(pp_str, 50)
    if pp is not None:
        pp = min(max(pp, 1), 500)
        pp_str = str(pp)

    where, params = "WHERE 1=1", []
    if d_ini:   where += " AND f.data>=?"; params.append(d_ini)
    if d_fim:   where += " AND f.data<=?"; params.append(d_fim)
    if fs:      where += f" AND COALESCE(f.status_notificacao,'pendente') IN ({','.join('?'*len(fs))})"; params+=fs
    if ft:      where += f" AND f.tipo_trabalho IN ({','.join('?'*len(ft))})"; params+=ft
    if fl:      where += f" AND l.nome IN ({','.join('?'*len(fl))})"; params+=fl
    if fa:
        cond = " OR ".join(["f.agentes LIKE ?" for _ in fa])
        where += f" AND ({cond})"; params += [f"%{a}%" for a in fa]
    if busca:
        where += " AND (f.logradouro LIKE ? OR f.num_tubo LIKE ? OR f.nome_morador LIKE ? OR CAST(f.quarteirao AS TEXT) LIKE ? OR f.codigo LIKE ?)"
        b = f"%{busca}%"; params += [b, b, b, b, b]
    where += " AND f.gera_notificacao=1"

    base = f"SELECT f.*, l.nome AS localidade_nome FROM focos_positivos f LEFT JOIN localidades l ON l.id_localidade=f.id_localidade {where}"
    conn = get_db()
    total = conn.execute(f"SELECT COUNT(*) FROM focos_positivos f LEFT JOIN localidades l ON l.id_localidade=f.id_localidade {where}", params).fetchone()[0]

    if pp:
        total_pag = max(1, (total + pp - 1) // pp)
        pagina    = min(pagina, total_pag)
        focos     = conn.execute(base + " ORDER BY f.data DESC LIMIT ? OFFSET ?", params + [pp, (pagina-1)*pp]).fetchall()
    else:
        total_pag, pagina = 1, 1
        focos = conn.execute(base + " ORDER BY f.data DESC", params).fetchall()

    contadores = {}
    for row in conn.execute("SELECT COALESCE(status_notificacao,'pendente') as st, COUNT(*) as cnt FROM focos_positivos WHERE gera_notificacao=1 GROUP BY st").fetchall():
        contadores[row[0]] = row[1]

    tipos_n   = [r[0] for r in conn.execute("SELECT DISTINCT tipo_trabalho FROM focos_positivos WHERE tipo_trabalho IS NOT NULL ORDER BY tipo_trabalho").fetchall()]
    locs_n    = [r[0] for r in conn.execute("SELECT DISTINCT nome FROM localidades ORDER BY nome").fetchall()]
    agentes_l = [r[0] for r in conn.execute("SELECT nome FROM agentes ORDER BY nome").fetchall()]
    conn.close()

    return render_template("notificacoes.html",
        focos=[dict(f) for f in focos], contadores=contadores,
        tipos=tipos_n, localidades_n=locs_n, agentes_lista=agentes_l,
        filtro_status=fs, filtro_tipo=ft, filtro_loc=fl, filtro_agente=fa,
        filtro_d_ini=d_ini, filtro_d_fim=d_fim, busca=busca,
        pagina=pagina, total_paginas=total_pag, total=total, por_pagina=pp_str,
    )

@app.route("/notificacoes/foco/<id_foco>")
@login_required
def foco_detalhe(id_foco):
    foco = q1("SELECT f.*, l.nome AS localidade_nome FROM focos_positivos f LEFT JOIN localidades l ON l.id_localidade=f.id_localidade WHERE f.id_foco=?", (id_foco,))
    if not foco: abort(404)
    historico = []
    if foco.get("logradouro"):
        historico = q("""
            SELECT v.data, v.tipo, v.visita, GROUP_CONCAT(DISTINCT a.nome) as agentes
            FROM visitas v
            LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
            LEFT JOIN agentes a ON a.id_agente=va.id_agente
            WHERE v.logradouro=? AND v.numero=?
            GROUP BY v.id_visita ORDER BY v.data DESC LIMIT 10
        """, (foco["logradouro"], foco.get("numero", "")))
    historico_foco = q("""
        SELECT campo, valor_ant, valor_novo, usuario, alterado_em
        FROM focos_historico WHERE id_foco=? ORDER BY alterado_em DESC LIMIT 50
    """, (id_foco,))
    return render_template("foco_detalhe.html", foco=foco, historico=historico,
                           historico_foco=historico_foco)

@app.route("/notificacoes/foco/<id_foco>/atualizar", methods=["POST"])
@login_required
@nivel_min("operador")
def foco_atualizar(id_foco):
    campos = ["status_notificacao","tentativa_1","tentativa_2","tentativa_3",
              "data_entrega","observacoes","nome_morador","logradouro","numero","complemento","depositos","agentes"]
    vals   = {c: request.form.get(c) or None for c in campos}
    conn   = get_db()
    try:
        # Ler valores anteriores para auditoria
        anterior = conn.execute(
            f"SELECT {','.join(campos)} FROM focos_positivos WHERE id_foco=?", (id_foco,)
        ).fetchone()

        conn.execute("""
            UPDATE focos_positivos SET
                status_notificacao=?,tentativa_1=?,tentativa_2=?,tentativa_3=?,
                data_entrega=?,observacoes=?,nome_morador=?,
                logradouro=?,numero=?,complemento=?,depositos=?,agentes=?
            WHERE id_foco=?
        """, list(vals.values()) + [id_foco])

        # Registrar apenas campos que mudaram
        if anterior:
            usuario = session.get("nome", "desconhecido")
            agora   = datetime.now().isoformat()
            for i, campo in enumerate(campos):
                ant = anterior[i]
                nov = vals[campo]
                if str(ant or "") != str(nov or ""):
                    conn.execute("""
                        INSERT INTO focos_historico (id_foco, campo, valor_ant, valor_novo, usuario, alterado_em)
                        VALUES (?,?,?,?,?,?)
                    """, (id_foco, campo, ant, nov, usuario, agora))

        conn.commit()
    finally:
        conn.close()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True})
    return redirect(url_for("foco_detalhe", id_foco=id_foco))

@app.route("/notificacoes/foco/<id_foco>/status", methods=["POST"])
@login_required
@nivel_min("operador")
def foco_status_rapido(id_foco):
    novo = request.json.get("status") if request.is_json else request.form.get("status")
    if novo not in STATUS_OPCOES + [None]:
        return jsonify({"erro": "Status invÃ¡lido"}), 400
    conn = get_db()
    try:
        ant_row = conn.execute("SELECT status_notificacao FROM focos_positivos WHERE id_foco=?", (id_foco,)).fetchone()
        ant = ant_row[0] if ant_row else None
        conn.execute("UPDATE focos_positivos SET status_notificacao=? WHERE id_foco=?", (novo, id_foco))
        if str(ant or "") != str(novo or ""):
            conn.execute("""INSERT INTO focos_historico (id_foco,campo,valor_ant,valor_novo,usuario,alterado_em)
                            VALUES (?,?,?,?,?,?)""",
                         (id_foco, "status_notificacao", ant, novo,
                          session.get("nome","desconhecido"), datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "status": novo})

@app.route("/notificacoes/imprimir", methods=["POST"])
@login_required
@nivel_min("operador")
def imprimir():
    ids = request.form.getlist("ids")
    if not ids: return redirect(url_for("notificacoes"))
    conn = get_db()
    focos = []
    for id_foco in ids:
        row = conn.execute("""
            SELECT f.*, l.nome AS localidade_nome FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
            WHERE f.id_foco=? AND f.gera_notificacao=1
        """, (id_foco,)).fetchone()
        if row: focos.append(dict(row))
    if not focos:
        conn.close(); return "Nenhum foco vÃ¡lido.", 400
    try:
        caminho = gerar_docx(focos)
    except Exception as e:
        conn.close(); return f"Erro ao gerar DOCX: {e}", 500
    for f in focos:
        conn.execute("UPDATE focos_positivos SET status_notificacao='impressa' WHERE id_foco=? AND COALESCE(status_notificacao,'pendente')='pendente'", (f["id_foco"],))
    conn.commit(); conn.close()
    return send_file(caminho, as_attachment=True,
                     download_name=f"notificacoes_{datetime.now().strftime('%Y%m%d_%H%M')}.docx")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ROTAS â€” PROCESSAR (ETL via upload)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

#  API JSON
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/dashboard")
@login_required
def api_dashboard():
    try:
        where, params = build_where(request.args)
        base = f"""FROM visitas v
                   LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                   LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                   LEFT JOIN agentes a ON a.id_agente=va.id_agente
                   {where}"""
        conn = get_db()

        kpi = conn.execute(f"""
            SELECT COUNT(DISTINCT v.id_visita) as total,
                   COUNT(DISTINCT v.data) as dias,
                   COUNT(DISTINCT v.quarteirao) as quarteiroes,
                   COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
                   COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
                   COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
                   COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
            {base}""", params).fetchone()

        por_tipo    = conn.execute(f"SELECT v.tipo, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY v.tipo", params).fetchall()
        por_loc     = conn.execute(f"SELECT l.nome as loc, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY l.nome ORDER BY total DESC LIMIT 15", params).fetchall()
        por_status  = conn.execute(f"SELECT COALESCE(LOWER(v.visita),'sem info') as visita, COUNT(*) as total {base} GROUP BY LOWER(v.visita)", params).fetchall()
        evolucao    = conn.execute(f"SELECT strftime('%Y-%W',v.data) as sem, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY sem ORDER BY sem", params).fetchall()
        por_agente  = conn.execute(f"SELECT a.nome, COUNT(DISTINCT v.id_visita) as total {base} AND a.nome IS NOT NULL GROUP BY a.nome ORDER BY total DESC", params).fetchall()
        por_imovel  = conn.execute(f"SELECT v.tipo_imovel, COUNT(*) as total {base} AND v.tipo_imovel IS NOT NULL GROUP BY v.tipo_imovel ORDER BY total DESC", params).fetchall()
        dep         = conn.execute(f"SELECT SUM(d.inspecionado) as insp, SUM(d.eliminado) as elim, SUM(d.tratado) as trat FROM depositos_inspecionados d JOIN visitas v ON v.id_visita=d.id_visita LEFT JOIN localidades l ON l.id_localidade=v.id_localidade LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita LEFT JOIN agentes a ON a.id_agente=va.id_agente {where}", params).fetchone()
        dep_tipo    = conn.execute(f"SELECT d.tipo_deposito, SUM(d.inspecionado) as insp FROM depositos_inspecionados d JOIN visitas v ON v.id_visita=d.id_visita LEFT JOIN localidades l ON l.id_localidade=v.id_localidade LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita LEFT JOIN agentes a ON a.id_agente=va.id_agente {where} GROUP BY d.tipo_deposito ORDER BY insp DESC", params).fetchall()
        tbo_dur = conn.execute(f"""
            SELECT COUNT(*) as n,
                   ROUND(AVG(dur),1) as media,
                   ROUND(MIN(dur),1) as minimo,
                   ROUND(MAX(dur),1) as maximo
            FROM (
                SELECT (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                FROM visitas v
                LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                LEFT JOIN agentes a ON a.id_agente=va.id_agente
                {where} AND v.tipo=? AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
            ) sub WHERE dur BETWEEN 1 AND 240
        """, params + [DURATION_WORK_TYPE_CODE]).fetchone()

        tbo_dur_tipo = conn.execute(f"""
            SELECT
                CASE WHEN LOWER(sub.visita) IN ('normal','recuperado') THEN 'acessados'
                     ELSE 'nao_acessados' END as grupo,
                COUNT(*) as n,
                ROUND(AVG(dur),1) as media,
                ROUND(MIN(dur),1) as minimo,
                ROUND(MAX(dur),1) as maximo
            FROM (
                SELECT v.visita,
                    (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                FROM visitas v
                LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                LEFT JOIN agentes a ON a.id_agente=va.id_agente
                {where} AND v.tipo=? AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
            ) sub WHERE dur BETWEEN 1 AND 240
            GROUP BY grupo
        """, params + [DURATION_WORK_TYPE_CODE]).fetchall()

        conn.close()

        return jsonify({
            "kpi": dict(kpi) if kpi else {},
            "depositos": {"inspecionados": safe_int(dep["insp"]) if dep else 0,
                          "eliminados": safe_int(dep["elim"]) if dep else 0,
                          "tratados": safe_int(dep["trat"]) if dep else 0},
            "dep_por_tipo": [dict(r) for r in dep_tipo],
            "tbo_duracao": {
                "n": dict(tbo_dur)["n"] if tbo_dur else 0,
                "media": dict(tbo_dur)["media"] if tbo_dur else None,
                "minimo": dict(tbo_dur)["minimo"] if tbo_dur else None,
                "maximo": dict(tbo_dur)["maximo"] if tbo_dur else None,
                "por_grupo": {dict(r)["grupo"]: {"n":dict(r)["n"],"media":dict(r)["media"],"minimo":dict(r)["minimo"],"maximo":dict(r)["maximo"]} for r in tbo_dur_tipo},
            },
            "por_tipo": [dict(r) for r in por_tipo],
            "por_loc": [dict(r) for r in por_loc],
            "por_status": [dict(r) for r in por_status],
            "evolucao": [dict(r) for r in evolucao],
            "por_agente": [dict(r) for r in por_agente],
            "por_imovel": [dict(r) for r in por_imovel],
        })
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@app.route("/api/laboratorio")
@login_required
def api_laboratorio():
    try:
        d_ini   = request.args.get("d_ini", data_n_dias(365))
        d_fim   = request.args.get("d_fim", hoje())
        tipos   = request.args.getlist("tipo")
        locs    = request.args.getlist("localidade")
        ags     = request.args.getlist("agente")
        tubo    = request.args.get("tubo", "").strip()
        especie = request.args.get("especie", "")
        apenas_pos = request.args.get("apenas_pos", "")
        pagina  = request_int_arg("pagina", 1, minimo=1)
        pp      = request_int_arg("por_pagina", 50, minimo=1, maximo=500)

        where  = "WHERE v.data BETWEEN ? AND ?"
        params = [d_ini, d_fim]
        if tipos: where += f" AND v.tipo IN ({','.join('?'*len(tipos))})"; params += tipos
        if locs:  where += f" AND l.nome IN ({','.join('?'*len(locs))})"; params += locs
        if ags:
            cond = " OR ".join(["a.nome=?" for _ in ags])
            where += f" AND ({cond})"; params += ags
        if tubo: where += " AND c.num_tubo LIKE ?"; params.append(f"%{tubo}%")

        aeg = "(rl.aegypt_larvas>0 OR rl.aegypt_pupas>0 OR rl.aegypt_exuvias>0 OR rl.aegypt_adulto>0)"
        alb = "(rl.albopictus_larvas>0 OR rl.albopictus_pupas>0 OR rl.albopictus_exuvias>0 OR rl.albopictus_adulto>0)"
        out = "(rl.outra_larvas>0 OR rl.outra_pupas>0 OR rl.outra_exuvias>0 OR rl.outra_adulto>0)"

        if apenas_pos == "1" or especie == "aegypti": where += f" AND {aeg}"
        elif especie == "albopictus": where += f" AND {alb}"
        elif especie == "outra":      where += f" AND {out}"

        base = f"""FROM resultados_laboratorio rl
                   JOIN coletas c ON c.id_coleta=rl.id_coleta
                   JOIN visitas v ON v.id_visita=c.id_visita
                   LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                   LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                   LEFT JOIN agentes a ON a.id_agente=va.id_agente
                   {where}"""

        conn  = get_db()
        total = conn.execute(f"SELECT COUNT(DISTINCT rl.id_resultado) {base}", params).fetchone()[0]
        total_pag = max(1, (total + pp - 1) // pp)
        pagina    = min(pagina, total_pag)
        offset    = (pagina - 1) * pp

        rows = conn.execute(f"""
            SELECT DISTINCT rl.id_resultado, v.data, v.tipo, l.nome as localidade,
                   v.quarteirao, v.logradouro, v.numero, c.num_tubo, c.tipo_deposito,
                   rl.data_leitura, rl.laboratorista,
                   rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas, rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes,
                   ({aeg}) as pos_aeg, ({alb}) as pos_alb, ({out}) as pos_out
            {base} GROUP BY rl.id_resultado ORDER BY v.data DESC, rl.id_resultado DESC
            LIMIT ? OFFSET ?
        """, params + [pp, offset]).fetchall()

        totais = conn.execute(f"""SELECT
            SUM(sub.ta) as total_aeg, SUM(sub.tb) as total_alb, SUM(sub.tc) as total_out,
            COUNT(*) as total_col, SUM(sub.pa) as pos_aeg, SUM(sub.pb) as pos_alb
            FROM (
              SELECT DISTINCT rl.id_resultado,
                rl.aegypt_larvas+rl.aegypt_pupas+rl.aegypt_exuvias+rl.aegypt_adulto as ta,
                rl.albopictus_larvas+rl.albopictus_pupas+rl.albopictus_exuvias+rl.albopictus_adulto as tb,
                rl.outra_larvas+rl.outra_pupas+rl.outra_exuvias+rl.outra_adulto as tc,
                CASE WHEN {aeg} THEN 1 ELSE 0 END as pa,
                CASE WHEN {alb} THEN 1 ELSE 0 END as pb
              {base}
            ) sub""", params).fetchone()

        evolucao = conn.execute(f"""
            SELECT strftime('%Y-%m', v.data) as mes,
                   COUNT(DISTINCT rl.id_resultado) as total,
                   COUNT(DISTINCT CASE WHEN {aeg} THEN rl.id_resultado END) as positivos
            {base} GROUP BY mes ORDER BY mes
        """, params).fetchall()

        por_loc = conn.execute(f"""
            SELECT l.nome as loc, COUNT(DISTINCT rl.id_resultado) as total,
                   COUNT(DISTINCT CASE WHEN {aeg} THEN rl.id_resultado END) as positivos
            {base} GROUP BY l.nome ORDER BY total DESC
        """, params).fetchall()

        conn.close()
        tc = safe_int(totais["total_col"])
        ta = safe_int(totais["pos_aeg"])
        return jsonify({
            "total": total, "total_paginas": total_pag, "pagina": pagina,
            "totais": {
                "total_coletas": tc, "aegypti": safe_int(totais["total_aeg"]),
                "albopictus": safe_int(totais["total_alb"]), "outra": safe_int(totais["total_out"]),
                "positivos_aeg": ta, "positivos_alb": safe_int(totais["pos_alb"]),
                "indice_pos": round(ta/tc*100, 1) if tc else 0,
            },
            "evolucao": [dict(r) for r in evolucao],
            "por_loc":  [dict(r) for r in por_loc],
            "registros":[dict(r) for r in rows],
        })
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@app.route("/api/visitas")
@login_required
def api_visitas():
    try:
        where, params = build_where(request.args)
        busca = request.args.get("busca", "").strip()
        if busca:
            where += " AND (v.logradouro LIKE ? OR CAST(v.quarteirao AS TEXT) LIKE ?)"
            b = f"%{busca}%"; params += [b, b]

        pagina = request_int_arg("pagina", 1, minimo=1)
        pp     = request_int_arg("por_pagina", 100, minimo=1, maximo=500)
        base   = f"""FROM visitas v
                     LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                     LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                     LEFT JOIN agentes a ON a.id_agente=va.id_agente
                     {where}"""

        conn  = get_db()
        total = conn.execute(f"SELECT COUNT(DISTINCT v.id_visita) {base}", params).fetchone()[0]
        total_pag = max(1, (total + pp - 1) // pp)
        pagina    = min(pagina, total_pag)
        rows = conn.execute(f"""
            SELECT DISTINCT v.id_visita, v.data, v.tipo, l.nome as localidade,
                   v.quarteirao, v.logradouro, v.numero, v.visita,
                   v.tipo_imovel, v.ciclo, v.sequencia, v.morador,
                   v.hora_inicio, v.hora_fim, v.observacoes,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes,
                   CASE WHEN EXISTS(
                       SELECT 1 FROM focos_positivos f
                       WHERE f.id_visita=v.id_visita AND f.gera_notificacao=1
                   ) THEN 1 ELSE 0 END as positiva
            {base} GROUP BY v.id_visita ORDER BY v.data DESC, v.hora_inicio
            LIMIT ? OFFSET ?
        """, params + [pp, (pagina-1)*pp]).fetchall()
        conn.close()
        return jsonify({"total": total, "total_paginas": total_pag, "pagina": pagina,
                        "registros": [dict(r) for r in rows]})
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@app.route("/api/relatorio-agente")
@login_required
def api_relatorio_agente():
    """
    COD-03: API usa _obter_dados_relatorio_agente() compartilhada com a rota PDF.
    Antes tinha ~110 linhas de queries duplicadas â€” agora sÃ£o 12 linhas.
    """
    try:
        nome  = request.args.get("agente", "")
        d_ini = request.args.get("d_ini", data_n_dias(30))
        d_fim = request.args.get("d_fim", hoje())
        if not nome:
            return jsonify({"erro": "Agente nÃ£o informado"}), 400
        dados = _obter_dados_relatorio_agente(nome, d_ini, d_fim)
        # Retornar estrutura compatÃ­vel com o frontend existente
        return jsonify({
            "agente":   dados["agente"],
            "d_ini":    dados["d_ini"],
            "d_fim":    dados["d_fim"],
            "totais":   dados["totais_api"],
            "coletas":  dados["coletas_api"],
            "tbo_duracao": {
                "por_grupo": dados["tbo_por_grupo"],
            },
            "por_tipo": dados["por_tipo"],
            "por_loc":  dados["por_loc"],
            "por_dia":  dados["por_dia"],
            "evolucao": dados["evolucao"],
        })
    except Exception as e:
        logging.exception("Erro em api_relatorio_agente")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  GERAÃ‡ÃƒO DE DOCX
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def formatar_data_br(data_iso):
    meses = ["janeiro","fevereiro","marÃ§o","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    try:
        d = datetime.strptime(str(data_iso)[:10], "%Y-%m-%d")
        return f"{d.day} de {meses[d.month-1]} de {d.year}"
    except (ValueError, TypeError, AttributeError):
        return "______"

def remover_bordas(tabela):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for row in tabela.rows:
        for cell in row.cells:
            tcPr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for side in ["top","bottom","left","right","insideH","insideV"]:
                b = OxmlElement(f"w:{side}"); b.set(qn("w:val"), "none"); borders.append(b)
            tcPr.append(borders)

def gerar_via(doc, foco, modelo):
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    def par(texto="", bold=False, italic=False, size=11,
            align=WD_ALIGN_PARAGRAPH.LEFT, sb=0, sa=6):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(sb)
        p.paragraph_format.space_after  = Pt(sa)
        if texto:
            r = p.add_run(texto); r.bold = bold; r.italic = italic; r.font.size = Pt(size)
        return p

    def par_mixed(partes, align=WD_ALIGN_PARAGRAPH.LEFT, sb=0, sa=6):
        p = doc.add_paragraph(); p.alignment = align
        p.paragraph_format.space_before = Pt(sb); p.paragraph_format.space_after = Pt(sa)
        for texto, bold, italic, size in partes:
            r = p.add_run(texto); r.bold = bold; r.italic = italic; r.font.size = Pt(size)
        return p

    cab = doc.add_table(rows=1, cols=3); cab.style = "Table Grid"; remover_bordas(cab)

    # Coluna esquerda â€” Logo da prefeitura
    cl = cab.rows[0].cells[0]; cl.width = Cm(3.5)
    pl = cl.paragraphs[0]; pl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_pref = os.path.join(BASE_DIR, "static", "img", "logo_prefeitura.png")
    try: pl.add_run().add_picture(logo_pref, width=Cm(3))
    except Exception: pl.add_run("[LOGO PREFEITURA]")

    # Coluna central â€” TÃ­tulos
    ct = cab.rows[0].cells[1]
    for i, linha in enumerate(modelo.get("CABECALHO","").split("\n")):
        p = ct.paragraphs[0] if i == 0 else ct.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(linha); r.bold = (i==0); r.font.size = Pt(10 if i==0 else 9)

    # Coluna direita â€” Logo do Setor de Endemias
    cr = cab.rows[0].cells[2]; cr.width = Cm(3.5)
    pr = cr.paragraphs[0]; pr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_end = os.path.join(BASE_DIR, "static", "img", "logo_endemias.png")
    try: pr.add_run().add_picture(logo_end, width=Cm(3))
    except Exception: pr.add_run("[LOGO ENDEMIAS]")

    # Centralizar a tabela na pÃ¡gina
    from docx.oxml.ns import qn as _qn
    from docx.oxml import OxmlElement as _OxmlElement
    tblPr = cab._tbl.tblPr
    jc = _OxmlElement("w:jc"); jc.set(_qn("w:val"), "center")
    tblPr.append(jc)

    doc.add_paragraph()
    par(f"Almirante TamandarÃ© (PR), ______/______ de {date.today().year}.",
        align=WD_ALIGN_PARAGRAPH.RIGHT, size=10, sa=8)
    par(modelo.get("TITULO","COMUNICADO / NOTIFICAÃ‡ÃƒO"), bold=True, size=13,
        align=WD_ALIGN_PARAGRAPH.CENTER, sa=4)
    par(modelo.get("SAUDACAO","Prezado(a) Senhor(a) PROPRIETÃRIO/RESPONSÃVEL"), bold=True, size=11, sa=8)

    end_fmt  = f"{foco.get('logradouro') or ''}, {foco.get('numero') or 's/n'}".strip(", ")
    loc_fmt  = foco.get("localidade_nome") or foco.get("localidade") or ""
    qrt_fmt  = f"QuarteirÃ£o {foco.get('quarteirao')}" if foco.get("quarteirao") else ""
    loc_linha = " â€” ".join(filter(None, [loc_fmt, qrt_fmt]))

    corpo = modelo.get("CORPO","").replace("{endereco}", end_fmt)\
                                  .replace("{localidade}", loc_linha)\
                                  .replace("{data_visita}", formatar_data_br(foco.get("data")))
    partes = []
    marcador = "Aedes aegypti"
    while marcador in corpo:
        idx = corpo.index(marcador)
        if corpo[:idx]: partes.append((corpo[:idx], False, False, 11))
        partes.append((marcador, False, True, 11)); corpo = corpo[idx+len(marcador):]
    if corpo: partes.append((corpo, False, False, 11))
    par_mixed(partes, sa=8)

    par(modelo.get("AVISO",""), bold=True, size=11, sa=8)
    par(modelo.get("CONTATO",""), size=10, sa=10)
    campos = [
        ("LOCALIDADE",    loc_linha or "___________________________"),
        ("ENDEREÃ‡O",      end_fmt   or "___________________________"),
        ("MORADOR",       foco.get("nome_morador") or "___________________________"),
        ("DEPÃ“SITO(S)",   foco.get("depositos")    or "___________________________"),
        ("AGENTE(S)",     foco.get("agentes")      or "___________________________"),
    ]
    if foco.get("observacoes"):
        campos.append(("OBSERVAÃ‡Ã•ES", foco["observacoes"]))
    for label, valor in campos:
        par_mixed([(f"â€¢ {label}: ", True, True, 11), (valor, False, True, 11)], sa=3)

    doc.add_paragraph()
    ass = doc.add_table(rows=2, cols=2); ass.style = "Table Grid"; remover_bordas(ass)
    for i, txt in enumerate(["_"*35, "_"*35]):
        c = ass.rows[0].cells[i]; c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.paragraphs[0].add_run(txt)
    for i, txt in enumerate(["VigilÃ¢ncia Ambiental / Setor de Endemias","ProprietÃ¡rio / ResponsÃ¡vel"]):
        c = ass.rows[1].cells[i]; c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.paragraphs[0].add_run(txt).bold = True

    doc.add_paragraph()
    par(modelo.get("RODAPE",""), size=8, align=WD_ALIGN_PARAGRAPH.CENTER, sa=0)
    if foco.get("codigo"):
        par(f"NÂº da notificaÃ§Ã£o: {foco['codigo']}", size=7,
            align=WD_ALIGN_PARAGRAPH.CENTER, sa=0)

def gerar_docx(focos):
    from docx import Document; from docx.shared import Cm
    modelo = ler_modelo(); doc = Document()
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Cm(1.5)
        section.left_margin = section.right_margin  = Cm(2)
    for i, foco in enumerate(focos):
        gerar_via(doc, foco, modelo)
        if i < len(focos)-1: doc.add_page_break()
    caminho = os.path.join(SAIDA_DIR, f"notificacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
    doc.save(caminho); return caminho

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  MAPA
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/mapa")
@login_required
def mapa():
    return render_template("mapa.html")


@app.route("/api/mapa")
@login_required
def api_mapa():
    """
    Retorna estatÃ­sticas por quarteirÃ£o para colorir o mapa.
    Filtros: localidade[] (nomes), tipo[], d_ini, d_fim
    """
    try:
        locs  = request.args.getlist("localidade")   # nomes de localidade
        tipos = request.args.getlist("tipo")
        d_ini = request.args.get("d_ini", "")
        d_fim = request.args.get("d_fim", "")

        # â”€â”€ Visitas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        where_v  = "WHERE v.quarteirao IS NOT NULL AND v.id_localidade IS NOT NULL"
        params_v = []

        if locs:
            where_v += f" AND l.nome IN ({','.join('?'*len(locs))})"; params_v += locs
        if tipos:
            where_v += f" AND v.tipo IN ({','.join('?'*len(tipos))})"; params_v += tipos
        if d_ini:
            where_v += " AND v.data>=?"; params_v.append(d_ini)
        if d_fim:
            where_v += " AND v.data<=?"; params_v.append(d_fim)

        conn = get_db()

        rows_v = conn.execute(f"""
            SELECT
                v.id_localidade,
                v.quarteirao,
                v.tipo,
                COUNT(DISTINCT v.id_visita)                                             AS total_tipo,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) AS normais,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) AS fechados,
                COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) AS recuperados,
                MAX(v.data)                                                             AS ultimo_trabalho
            FROM visitas v
            LEFT JOIN localidades l ON l.id_localidade = v.id_localidade
            {where_v}
            GROUP BY v.id_localidade, v.quarteirao, v.tipo
        """, params_v).fetchall()

        # â”€â”€ Focos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        where_f  = "WHERE f.quarteirao IS NOT NULL AND f.id_localidade IS NOT NULL AND f.gera_notificacao=1"
        params_f = []
        if locs:
            where_f += f" AND l2.nome IN ({','.join('?'*len(locs))})"; params_f += locs
        if d_ini:
            where_f += " AND f.data>=?"; params_f.append(d_ini)
        if d_fim:
            where_f += " AND f.data<=?"; params_f.append(d_fim)
        if tipos:
            where_f += f" AND f.tipo_trabalho IN ({','.join('?'*len(tipos))})"; params_f += tipos

        rows_f = conn.execute(f"""
            SELECT f.id_localidade, f.quarteirao,
                   COUNT(*) AS total_focos,
                   COUNT(CASE WHEN f.status_notificacao='pendente' THEN 1 END) AS focos_pendentes
            FROM focos_positivos f
            LEFT JOIN localidades l2 ON l2.id_localidade = f.id_localidade
            {where_f}
            GROUP BY f.id_localidade, f.quarteirao
        """, params_f).fetchall()

        conn.close()

        # â”€â”€ Montar dicionÃ¡rio keyed por "id_localidade:quarteirao" â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        dados = {}
        def mapa_entry_vazio():
            entry = {
                "total": 0,
                "tipos": {},
                "normais": 0,
                "fechados": 0,
                "recuperados": 0,
                "ultimo_trabalho": None,
                "focos": 0,
                "focos_pendentes": 0,
            }
            for codigo in TIPO_CORES:
                entry[codigo.lower()] = 0
            return entry

        for r in rows_v:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            tipo = r["tipo"] or ""
            total_tipo = r["total_tipo"] or 0
            dados[chave]["total"] += total_tipo
            dados[chave]["tipos"][tipo] = total_tipo
            dados[chave][tipo.lower()] = total_tipo
            dados[chave]["normais"] += r["normais"] or 0
            dados[chave]["fechados"] += r["fechados"] or 0
            dados[chave]["recuperados"] += r["recuperados"] or 0
            ultimo = r["ultimo_trabalho"]
            if ultimo and (not dados[chave]["ultimo_trabalho"] or ultimo > dados[chave]["ultimo_trabalho"]):
                dados[chave]["ultimo_trabalho"] = ultimo
        for r in rows_f:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            dados[chave]["focos"]           = r["total_focos"]
            dados[chave]["focos_pendentes"] = r["focos_pendentes"]

        return jsonify(dados)

    except Exception as e:
        logging.exception("Erro em api_mapa")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ADMIN â€” GESTÃƒO DE USUÃRIOS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/visitas/exportar")
@login_required
def exportar_visitas():
    try:
        where, params = build_where(request.args)
        busca = request.args.get("busca","").strip()
        if busca:
            where += " AND (v.logradouro LIKE ? OR CAST(v.quarteirao AS TEXT) LIKE ?)"
            b = f"%{busca}%"; params += [b, b]
        rows = q(f"""
            SELECT DISTINCT v.data, v.tipo, l.nome as localidade, v.quarteirao,
                   v.logradouro, v.numero, v.visita, v.morador, v.tipo_imovel,
                   v.ciclo, v.sequencia, v.hora_inicio, v.hora_fim, v.observacoes,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes
            FROM visitas v
            LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
            LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
            LEFT JOIN agentes a ON a.id_agente=va.id_agente
            {where} GROUP BY v.id_visita ORDER BY v.data DESC, v.hora_inicio
        """, params)
        cabecalho = ["Data","Tipo","Localidade","QuarteirÃ£o","Logradouro","NÃºmero",
                     "Visita","Morador","Tipo ImÃ³vel","Ciclo","SequÃªncia",
                     "Hora InÃ­cio","Hora Fim","ObservaÃ§Ãµes","Agentes"]
        return _gerar_xlsx(cabecalho, rows, "visitas")
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500

@app.route("/api/notificacoes/exportar")
@login_required
def exportar_notificacoes():
    try:
        fs = request.args.getlist("status")
        ft = request.args.getlist("tipo")
        fl = request.args.getlist("localidade")
        d_ini = request.args.get("d_ini","")
        d_fim = request.args.get("d_fim","")
        busca = request.args.get("busca","").strip()
        where, params = "WHERE f.gera_notificacao=1", []
        if d_ini:   where += " AND f.data>=?"; params.append(d_ini)
        if d_fim:   where += " AND f.data<=?"; params.append(d_fim)
        if fs:      where += f" AND COALESCE(f.status_notificacao,'pendente') IN ({','.join('?'*len(fs))})"; params+=fs
        if ft:      where += f" AND f.tipo_trabalho IN ({','.join('?'*len(ft))})"; params+=ft
        if fl:      where += f" AND l.nome IN ({','.join('?'*len(fl))})"; params+=fl
        if busca:
            where += " AND (f.logradouro LIKE ? OR f.num_tubo LIKE ? OR f.nome_morador LIKE ? OR f.codigo LIKE ?)"
            b = f"%{busca}%"; params += [b,b,b,b]
        rows = q(f"""
            SELECT f.codigo, f.data, f.tipo_trabalho, l.nome as localidade,
                   f.quarteirao, f.logradouro, f.numero, f.nome_morador,
                   f.num_tubo, f.depositos, f.agentes,
                   COALESCE(f.status_notificacao,'pendente') as status,
                   f.tentativa_1, f.tentativa_2, f.tentativa_3,
                   f.data_entrega, f.observacoes
            FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
            {where} ORDER BY f.data DESC
        """, params)
        cabecalho = ["CÃ³digo","Data","Tipo","Localidade","QuarteirÃ£o","Logradouro",
                     "NÃºmero","Morador","Tubo(s)","DepÃ³sito(s)","Agentes","Status",
                     "Tentativa 1","Tentativa 2","Tentativa 3","Data Entrega","ObservaÃ§Ãµes"]
        return _gerar_xlsx(cabecalho, rows, "notificacoes")
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500

@app.route("/api/laboratorio/exportar")
@login_required
def exportar_laboratorio():
    try:
        d_ini  = request.args.get("d_ini", data_n_dias(365))
        d_fim  = request.args.get("d_fim", hoje())
        tipos  = request.args.getlist("tipo")
        locs   = request.args.getlist("localidade")
        tubo   = request.args.get("tubo","").strip()
        where  = "WHERE v.data BETWEEN ? AND ?"
        params = [d_ini, d_fim]
        if tipos: where += f" AND v.tipo IN ({','.join('?'*len(tipos))})"; params+=tipos
        if locs:  where += f" AND l.nome IN ({','.join('?'*len(locs))})"; params+=locs
        if tubo:  where += " AND c.num_tubo LIKE ?"; params.append(f"%{tubo}%")
        rows = q(f"""
            SELECT DISTINCT v.data, v.tipo, l.nome as localidade, v.quarteirao,
                   v.logradouro, v.numero, c.num_tubo, c.tipo_deposito,
                   rl.data_leitura, rl.laboratorista,
                   rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas, rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes
            FROM resultados_laboratorio rl
            JOIN coletas c ON c.id_coleta=rl.id_coleta
            JOIN visitas v ON v.id_visita=c.id_visita
            LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
            LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
            LEFT JOIN agentes a ON a.id_agente=va.id_agente
            {where} GROUP BY rl.id_resultado ORDER BY v.data DESC
        """, params)
        cabecalho = ["Data","Tipo","Localidade","QuarteirÃ£o","Logradouro","NÃºmero",
                     "Tubo","DepÃ³sito","Data Leitura","Laboratorista",
                     "Ae. Larvas","Ae. Pupas","Ae. ExÃºvias","Ae. Adulto",
                     "Alb. Larvas","Alb. Pupas","Alb. ExÃºvias","Alb. Adulto",
                     "Outra Larvas","Outra Pupas","Outra ExÃºvias","Outra Adulto","Agentes"]
        return _gerar_xlsx(cabecalho, rows, "laboratorio")
    except Exception as e:
        logging.exception("Erro em rota Flask")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500

def _gerar_xlsx(cabecalho, rows, nome):
    import openpyxl, io
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nome[:31]
    fill = PatternFill("solid", fgColor="1A4FBA")
    for ci, col in enumerate(cabecalho, 1):
        c = ws.cell(1, ci, col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center")
    for ri, row in enumerate(rows, 2):
        vals = list(row.values()) if isinstance(row, dict) else list(row)
        for ci, v in enumerate(vals, 1):
            ws.cell(ri, ci, v)
    for col in ws.columns:
        w = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(w + 2, 40)
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(buf, as_attachment=True,
                     download_name=f"{nome}_{ts}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/saida/download/<tipo>")
@login_required
def saida_download(tipo):
    tipo = (tipo or "").upper()
    if tipo not in work_types.WORK_TYPE_CODES:
        abort(404)
    caminho = os.path.join(BASE_DIR, "saida", f"{tipo}_consolidado.xlsx")
    if not os.path.exists(caminho):
        return f"Arquivo {tipo}_consolidado.xlsx ainda nÃ£o gerado. Execute um processamento primeiro.", 404
    return send_file(caminho, as_attachment=True,
                     download_name=f"{tipo}_consolidado_{datetime.now().strftime('%Y%m%d')}.xlsx")

def _focos_para_impressao(ids):
    """Retorna lista de dicts de focos para impressÃ£o, na ordem dos IDs."""
    conn = get_db()
    focos = []
    for id_foco in ids:
        row = conn.execute("""
            SELECT f.*, l.nome AS localidade_nome
            FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade = f.id_localidade
            WHERE f.id_foco = ? AND f.gera_notificacao = 1
        """, (id_foco,)).fetchone()
        if row:
            focos.append(dict(row))
    conn.close()
    return focos

@app.route("/notificacoes/foco/<id_foco>/imprimir-html")
@login_required
@nivel_min("operador")
def imprimir_html_single(id_foco):
    focos = _focos_para_impressao([id_foco])
    if not focos:
        abort(404)
    # Marcar como impressa se ainda pendente
    conn = get_db()
    conn.execute("""UPDATE focos_positivos SET status_notificacao='impressa'
                    WHERE id_foco=? AND COALESCE(status_notificacao,'pendente')='pendente'""", (id_foco,))
    conn.commit(); conn.close()
    return render_template("notificacao_print.html", focos=focos, auto_print=True, modelo=type("M", (), ler_modelo())())

@app.route("/notificacoes/imprimir-html", methods=["POST"])
@login_required
@nivel_min("operador")
def imprimir_html_lote():
    ids = request.form.getlist("ids")
    if not ids:
        return redirect(url_for("notificacoes"))
    focos = _focos_para_impressao(ids)
    if not focos:
        return "Nenhum foco vÃ¡lido.", 400
    conn = get_db()
    for f in focos:
        conn.execute("""UPDATE focos_positivos SET status_notificacao='impressa'
                        WHERE id_foco=? AND COALESCE(status_notificacao,'pendente')='pendente'""",
                     (f["id_foco"],))
    conn.commit(); conn.close()
    return render_template("notificacao_print.html", focos=focos, auto_print=True, modelo=type("M", (), ler_modelo())())

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ERROR HANDLERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.errorhandler(404)
def err404(e): return render_template("404.html"), 404

@app.errorhandler(500)
def err500(e): return render_template("500.html"), 500

@app.errorhandler(403)
def err403(e): return render_template("403.html"), 403

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  MAIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    try:    ip = socket.gethostbyname(hostname)
    except OSError: ip = "127.0.0.1"

    print("=" * 54)
    print("  ENDEMIAS â€” Sistema de GestÃ£o Integrado  v3")
    print("  Setor de Endemias Â· Almirante TamandarÃ©-PR")
    print("=" * 54)
    print(f"\n  Banco de dados: {DB_PATH}")
    print(f"\n  Acesse no navegador:")
    print(f"    Este computador : http://localhost:5000")
    print(f"    Rede local      : http://{ip}:5000")
    print(f"\n  Para encerrar: Ctrl+C ou feche esta janela")
    print("=" * 54 + "\n")

    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
