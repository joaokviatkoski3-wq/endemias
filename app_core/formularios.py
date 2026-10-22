"""Hub de formulários internos (captura em campo + revisão/oficialização).

O primeiro formulário é a atualização de Registro Geográfico (RG). A tabela
``formularios`` é genérica: guarda o rascunho de qualquer formulário; a
aplicação do dado aprovado fica em cada módulo específico (ex.: o RG chama
``registro_geografico.salvar_quarteirao``).
"""

import json
from datetime import datetime

from app_core import db as db_core


TABLE = "formularios"

STATUS_RASCUNHO = "rascunho"
STATUS_ENVIADO = "enviado"
STATUS_EM_REVISAO = "em_revisao"
STATUS_APROVADO = "aprovado"
STATUS_OFICIALIZADO = "oficializado"
STATUS_DEVOLVIDO = "devolvido"

STATUS_VALIDOS = (
    STATUS_RASCUNHO,
    STATUS_ENVIADO,
    STATUS_EM_REVISAO,
    STATUS_APROVADO,
    STATUS_OFICIALIZADO,
    STATUS_DEVOLVIDO,
)

# Registro dos formulários disponíveis. Cada formulário futuro entra aqui.
FORMULARIOS = (
    {
        "tipo": "rg_atualizacao",
        "titulo": "Atualização de Registro Geográfico (RG)",
        "descricao": "Levantamento de campo dos imóveis de um quarteirão, do zero.",
        "href_campo": "/formularios/rg-campo",
        "href_revisao": "/formularios/rg-revisao",
        "icone": "registro_geografico.svg",
    },
)


def formulario_por_tipo(tipo):
    return next((f for f in FORMULARIOS if f["tipo"] == tipo), None)


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True


def _now():
    return datetime.now().isoformat(timespec="seconds")


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS formularios (
            id_formulario INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_formulario TEXT NOT NULL,
            usuario_id INTEGER,
            agente_nome TEXT,
            status TEXT NOT NULL DEFAULT 'rascunho',
            payload_json TEXT NOT NULL,
            uuid_cliente TEXT UNIQUE,
            revisado_por_usuario_id INTEGER,
            revisado_por_nome TEXT,
            oficializado_por_usuario_id INTEGER,
            oficializado_por_nome TEXT,
            motivo_devolucao TEXT,
            criado_em TEXT NOT NULL,
            enviado_em TEXT,
            revisado_em TEXT,
            oficializado_em TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_formularios_tipo_status
            ON formularios(tipo_formulario, status, id_formulario);
        """
    )


def salvar(target, tipo, payload, usuario, uuid_cliente=None, status=STATUS_ENVIADO):
    """Cria (ou atualiza por uuid_cliente) um formulário.

    Idempotência: se ``uuid_cliente`` já existir, atualiza payload/status e
    devolve o mesmo id — evita duplicidade ao reenviar do campo.
    """
    if formulario_por_tipo(tipo) is None:
        raise ValueError("Formulário desconhecido.")
    if status not in STATUS_VALIDOS:
        raise ValueError("Status inválido.")
    if not isinstance(payload, dict):
        raise ValueError("Payload inválido.")
    usuario = usuario or {}
    agora = _now()
    payload_json = json.dumps(payload, ensure_ascii=False)
    agente_nome = usuario.get("nome") or usuario.get("usuario") or None

    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        if uuid_cliente:
            existente = conn.execute(
                "SELECT id_formulario FROM formularios WHERE uuid_cliente=?", (uuid_cliente,)
            ).fetchone()
            if existente:
                conn.execute(
                    """UPDATE formularios
                          SET payload_json=?, status=?, agente_nome=COALESCE(?, agente_nome),
                              enviado_em=COALESCE(enviado_em, ?)
                        WHERE id_formulario=?""",
                    (payload_json, status, agente_nome, agora, existente["id_formulario"]),
                )
                conn.commit()
                return existente["id_formulario"]

        novo_id = db_core.insert_and_get_id(
            conn,
            """INSERT INTO formularios
                (tipo_formulario, usuario_id, agente_nome, status, payload_json,
                 uuid_cliente, criado_em, enviado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                tipo,
                usuario.get("id_usuario"),
                agente_nome,
                status,
                payload_json,
                uuid_cliente,
                agora,
                agora if status != STATUS_RASCUNHO else None,
            ),
            "id_formulario",
        )
        conn.commit()
        return novo_id
    finally:
        if close:
            conn.close()


def listar(target, tipo=None, status=None, usuario=None, limite=200):
    """Lista formulários. Usuário não-admin vê apenas os próprios."""
    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        where, params = "WHERE 1=1", []
        if tipo:
            where += " AND tipo_formulario=?"
            params.append(tipo)
        if status:
            where += " AND status=?"
            params.append(status)
        if usuario and usuario.get("nivel") != "admin":
            where += " AND usuario_id=?"
            params.append(usuario.get("id_usuario"))
        rows = [
            db_core.serialize_row(r)
            for r in conn.execute(
                f"SELECT * FROM formularios {where} ORDER BY id_formulario DESC LIMIT ?",
                params + [int(limite)],
            )
        ]
        for row in rows:
            row["payload"] = json.loads(row["payload_json"] or "{}")
        return rows
    finally:
        if close:
            conn.close()


def obter(target, id_formulario):
    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM formularios WHERE id_formulario=?", (id_formulario,)
        ).fetchone()
        if not row:
            return None
        item = db_core.serialize_row(row)
        item["payload"] = json.loads(item["payload_json"] or "{}")
        return item
    finally:
        if close:
            conn.close()


def revisar(target, id_formulario, payload, decisao, usuario, motivo=None):
    """Admin corrige o payload e decide aprovar/devolver."""
    if decisao not in (STATUS_APROVADO, STATUS_DEVOLVIDO):
        raise ValueError("Decisão inválida.")
    if not isinstance(payload, dict):
        raise ValueError("Payload inválido.")
    usuario = usuario or {}
    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT status FROM formularios WHERE id_formulario=?", (id_formulario,)
        ).fetchone()
        if not row:
            raise ValueError("Formulário não encontrado.")
        if row["status"] == STATUS_OFICIALIZADO:
            raise ValueError("Formulário já oficializado.")
        conn.execute(
            """UPDATE formularios
                  SET payload_json=?, status=?, revisado_por_usuario_id=?,
                      revisado_por_nome=?, revisado_em=?, motivo_devolucao=?
                WHERE id_formulario=?""",
            (
                json.dumps(payload, ensure_ascii=False),
                decisao,
                usuario.get("id_usuario"),
                usuario.get("nome") or usuario.get("usuario") or None,
                _now(),
                motivo or None,
                id_formulario,
            ),
        )
        conn.commit()
        return True
    finally:
        if close:
            conn.close()


def excluir(target, id_formulario):
    """Exclui um formulário ainda não oficializado."""
    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT status FROM formularios WHERE id_formulario=?", (id_formulario,)
        ).fetchone()
        if not row:
            raise ValueError("Formulário não encontrado.")
        if row["status"] == STATUS_OFICIALIZADO:
            raise ValueError("Formulário oficializado não pode ser apagado.")
        conn.execute("DELETE FROM formularios WHERE id_formulario=?", (id_formulario,))
        conn.commit()
        return True
    finally:
        if close:
            conn.close()


def marcar_oficializado(target, id_formulario, usuario):
    """Marca o formulário como oficializado (chamado pelo módulo específico)."""
    usuario = usuario or {}
    conn, close = _open_connection(target)
    try:
        ensure_schema(conn)
        conn.execute(
            """UPDATE formularios
                  SET status=?, oficializado_por_usuario_id=?, oficializado_por_nome=?,
                      oficializado_em=?
                WHERE id_formulario=?""",
            (
                STATUS_OFICIALIZADO,
                usuario.get("id_usuario"),
                usuario.get("nome") or usuario.get("usuario") or None,
                _now(),
                id_formulario,
            ),
        )
        conn.commit()
        return True
    finally:
        if close:
            conn.close()
