"""Piloto de Web Push sem corpo. O navegador exibe uma mensagem fixa."""

import base64
from contextlib import closing
from datetime import datetime, timedelta
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import re
from threading import Event, Thread
import time

import certifi
import urllib3

from app_core import avisos_campo, db, sessoes, visitas_integradas


CHAVE_ENV = "ENDEMIAS_CAMPO_PUSH_CHAVE"
ORIGEM_FCM = "https://fcm.googleapis.com"
ENDPOINT = re.compile(r"https://fcm\.googleapis\.com/fcm/send/[A-Za-z0-9_.:-]{20,2048}")
LOG = logging.getLogger(__name__)


def conta_piloto():
    return os.environ.get("ENDEMIAS_FORMULARIOS_OFFLINE_USUARIO", "").strip().casefold()


def identificavel(usuario):
    piloto = conta_piloto()
    return (bool(piloto and usuario.get("id_agente") and not usuario.get("somente_laboratorio")
                 and usuario.get("nivel") in {"usuario", "operador", "admin", "superadmin"})
            and str(usuario.get("usuario", "")).casefold() == piloto)


def _base64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@lru_cache(maxsize=1)
def chave(path):
    from Cryptodome.PublicKey import ECC

    key = ECC.import_key(Path(path).read_text(encoding="ascii"))
    if key.curve != "NIST P-256" or not key.has_private():
        raise ValueError("Chave de notificações inválida.")
    return key


def criar_chave(path):
    from Cryptodome.PublicKey import ECC

    path.write_text(ECC.generate(curve="P-256").export_key(format="PEM"), encoding="ascii")


def chave_publica(key):
    return _base64(key.public_key().export_key(format="SEC1"))


def validar_endpoint(valor):
    if not isinstance(valor, str) or not ENDPOINT.fullmatch(valor):
        raise ValueError("Neste piloto, use o aplicativo instalado pelo Chrome no Android.")
    return valor


def _cabecalhos(key, assunto, now):
    from Cryptodome.Hash import SHA256
    from Cryptodome.Signature import DSS

    header = _base64(b'{"typ":"JWT","alg":"ES256"}')
    claims = {"aud": ORIGEM_FCM, "exp": now + 3600, "sub": assunto}
    payload = _base64(json.dumps(claims, separators=(",", ":")).encode("ascii"))
    partes = f"{header}.{payload}"
    sig = DSS.new(key, "deterministic-rfc6979", encoding="binary").sign(SHA256.new(partes.encode("ascii")))
    return {"Authorization": f"vapid t={partes}.{_base64(sig)},k={chave_publica(key)}",
            "TTL": "3600", "Topic": "vsatt-campo", "Content-Length": "0"}


@lru_cache(maxsize=1)
def _http():
    return urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
                               timeout=urllib3.Timeout(connect=3.0, read=3.0), retries=False)


def enviar(endpoint, key, assunto):
    endpoint = validar_endpoint(endpoint)
    response = _http().request("POST", endpoint, headers=_cabecalhos(key, assunto, int(time.time())),
                               body=b"", redirect=False, preload_content=False)
    try:
        return response.status
    finally:
        response.close()
        response.release_conn()


def _aparelho(conn, usuario, lock=False):
    suffix = " FOR UPDATE" if lock and conn.backend == "postgresql" else ""
    return conn.execute("SELECT * FROM campo_push_aparelhos WHERE id_usuario=?" + suffix,
                        (usuario,)).fetchone()


def status(target, usuario):
    with closing(db.connect(target)) as conn:
        row = _aparelho(conn, usuario)
        return sessoes.digest(row["endpoint"]) if row else None


def inscrever(target, usuario, sid, endpoint):
    endpoint = validar_endpoint(endpoint)
    with closing(db.connect(target)) as conn, conn:
        conn.execute("""INSERT INTO campo_push_aparelhos
            (id_usuario,id_agente,sessao_hash,senha_vinculo,endpoint,inscrito_em)
            VALUES (?,?,?,?,?,?) ON CONFLICT (id_usuario) DO UPDATE SET
                id_agente=excluded.id_agente, sessao_hash=excluded.sessao_hash, senha_vinculo=excluded.senha_vinculo,
                endpoint=excluded.endpoint, teste_em=0, inscrito_em=excluded.inscrito_em""",
            (usuario["id_usuario"], usuario["id_agente"], sessoes.digest(sid),
             sessoes.digest(usuario["senha_hash"]), endpoint, datetime.now().isoformat(timespec="microseconds")))


def cancelar(target, usuario, endpoint):
    with closing(db.connect(target)) as conn, conn:
        conn.execute("DELETE FROM campo_push_aparelhos WHERE id_usuario=? AND endpoint=?",
                     (usuario, validar_endpoint(endpoint)))


def revogar_sessao(conn, sid_hash, usuario):
    if os.environ.get(CHAVE_ENV):
        conn.execute("DELETE FROM campo_push_aparelhos WHERE id_usuario=? AND sessao_hash=?",
                     (usuario, sid_hash))


def testar(target, usuario, endpoint):
    endpoint = validar_endpoint(endpoint)
    now = int(time.time())
    with closing(visitas_integradas.connect(target)) as conn, conn:
        row = _aparelho(conn, usuario, lock=True)
        if not row or row["endpoint"] != endpoint:
            raise ValueError("Ative os avisos neste aparelho antes de testar.")
        if now - row["ultimo_teste"] < 60:
            raise ValueError("Aguarde um minuto antes de pedir outro teste.")
        conn.execute("UPDATE campo_push_aparelhos SET ultimo_teste=?,teste_em=? WHERE id_usuario=?",
                     (now, now+15, usuario))


def verificar_resultados(target, key, assunto, agora=None):
    """Agrupa resultados novos do piloto em um único aviso por verificação."""
    agora = agora or datetime.now()
    with closing(visitas_integradas.connect(target)) as conn, conn:
        if conn.backend == "postgresql" and not conn.execute(
                "SELECT pg_try_advisory_xact_lock(?)", (430992101,)).fetchone()[0]:
            return
        user = conn.execute("""SELECT u.id_usuario, u.id_agente, u.senha_hash, u.somente_laboratorio, u.nivel, u.usuario
            FROM usuarios u JOIN agentes a ON a.id_agente=u.id_agente
              JOIN campo_push_aparelhos p ON p.id_usuario=u.id_usuario
            WHERE LOWER(u.usuario)=? AND u.setor='endemias' AND u.ativo=1 AND a.ativo=1""",
            (conta_piloto(),)).fetchone()
        if not user or not identificavel(dict(user)):
            return
        usuario, agente = user["id_usuario"], user["id_agente"]
        aparelho = _aparelho(conn, usuario, lock=True)
        if not aparelho:
            return
        if aparelho["id_agente"] != agente or aparelho["senha_vinculo"] != sessoes.digest(user["senha_hash"]):
            conn.execute("DELETE FROM campo_push_aparelhos WHERE id_usuario=?", (usuario,))
            return
        # Evita disparo de um acervo acumulado durante o desligamento do servidor.
        desde = max(aparelho["inscrito_em"], (agora-timedelta(days=1)).isoformat(timespec="microseconds"))
        agora_seg = int(agora.timestamp())
        agendado = aparelho["teste_em"]
        if agendado and agora_seg < agendado:
            return
        if agendado and agora_seg > agendado+300:
            conn.execute("UPDATE campo_push_aparelhos SET teste_em=0 WHERE id_usuario=?", (usuario,))
            agendado = 0
        pendentes = [] if agendado else avisos_campo.pendentes_push(conn, usuario, agente, desde)
        if not pendentes and not agendado:
            return
        code = enviar(aparelho["endpoint"], key, assunto)
        if code in {404, 410}:
            conn.execute("DELETE FROM campo_push_aparelhos WHERE id_usuario=?", (usuario,))
        elif 200 <= code < 300:
            if agendado:
                conn.execute("UPDATE campo_push_aparelhos SET teste_em=0 WHERE id_usuario=?", (usuario,))
                return
            conn.executemany("""INSERT INTO campo_push_entregas (id_usuario,id_agente,id_resultado,versao)
                VALUES (?,?,?,?) ON CONFLICT (id_usuario,id_agente,id_resultado) DO UPDATE SET versao=excluded.versao""",
                [(usuario, agente, ident, ver) for ident, ver in pendentes])
        else:
            LOG.warning("Web Push aguardando nova tentativa (HTTP %d)", code)


def iniciar(config):
    path = os.environ.get(CHAVE_ENV)
    if not path or not config.get("ACESSO_EXTERNO") or not conta_piloto():
        return None
    try:
        key = chave(path)
        assunto = "https://" + config["TRUSTED_HOSTS"][0]
        target = db.configured_target(config)
    except Exception:
        LOG.error("Web Push indisponível. Confira as configurações do piloto.")
        return None
    parar = Event()

    def loop():
        while not parar.wait(25):
            try:
                verificar_resultados(target, key, assunto)
            except Exception as exc:
                LOG.warning("Web Push aguardando nova tentativa (%s)", type(exc).__name__)

    Thread(target=loop, name="vsatt-web-push", daemon=True).start()
    return parar
