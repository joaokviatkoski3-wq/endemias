"""Ciencia de responsabilidade do usuario; nao e consentimento do paciente."""

import hashlib
from datetime import datetime, timezone

from app_core import auth, db


VERSAO = "2026-11-03.1"
TITULO = "Termo de ciência e responsabilidade pelo uso dos dados"
COMPROMISSOS = (
    "Acessarei e utilizarei os dados somente para as atividades de trabalho para as quais estou autorizado, respeitando minhas permissões e as orientações do setor.",
    "Manterei sigilo sobre dados pessoais e informações de saúde. Não divulgarei nem compartilharei esses dados com pessoas não autorizadas, inclusive por mensagens, redes sociais, fotografias ou capturas de tela.",
    "Usarei relatórios, planilhas e outros arquivos exportados somente para a finalidade de trabalho autorizada, guardando-os em locais protegidos e seguindo as orientações do setor para compartilhamento, retenção e descarte.",
    "Não compartilharei minha senha nem utilizarei a conta de outra pessoa. Protegerei o aparelho de acesso e encerrarei a sessão quando necessário, especialmente em equipamentos compartilhados.",
    "Protegerei os dados e rascunhos baixados para trabalho offline e seguirei as orientações do setor antes de trocar ou descartar o aparelho.",
    "Comunicarei prontamente ao responsável pelo sistema ou à chefia qualquer perda de aparelho, acesso indevido, envio incorreto ou suspeita de exposição de dados, sem tentar ocultar o ocorrido.",
)
AVISO = (
    "Declaro que li e compreendi estes compromissos de uso autorizado e sigilo. "
    "Estou ciente de que acessos e operações podem ser registrados para segurança e auditoria, "
    "e de que o descumprimento poderá ser apurado conforme as normas aplicáveis. "
    "Este aceite não autoriza usos indevidos, não substitui as obrigações da instituição "
    "e não é consentimento dos titulares para o tratamento de seus dados."
)
TEXTO = TITULO + "\n\n" + "\n\n".join(COMPROMISSOS) + "\n\n" + AVISO
HASH = hashlib.sha256((VERSAO + "\n" + TEXTO).encode("utf-8")).hexdigest()


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS usuarios_termos (
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id_usuario),
        termo_hash TEXT NOT NULL,
        versao TEXT NOT NULL,
        texto_termo TEXT NOT NULL,
        aceito_em TEXT NOT NULL,
        ip TEXT NOT NULL,
        PRIMARY KEY (usuario_id, termo_hash)
    )""")
    conn.commit()


def aceitou(target, uid):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        return bool(conn.execute(
            "SELECT 1 FROM usuarios_termos WHERE usuario_id=? AND termo_hash=? AND versao=?",
            (uid, HASH, VERSAO),
        ).fetchone())
    finally:
        conn.close()


def registrar(target, uid):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        conn.execute("""INSERT INTO usuarios_termos
            (usuario_id, termo_hash, versao, texto_termo, aceito_em, ip)
            VALUES (?,?,?,?,?,?) ON CONFLICT (usuario_id, termo_hash) DO NOTHING""",
            (uid, HASH, VERSAO, TEXTO, datetime.now(timezone.utc).isoformat(), auth.client_ip()),
        )
        conn.commit()
    finally:
        conn.close()
