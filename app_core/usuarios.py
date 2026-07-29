"""Regras de cadastro e manutencao das contas de acesso."""

import os
from datetime import datetime

from app_core import auth
from app_core import db as db_core


VALID_LEVELS = ("admin", "operador", "visualizador")
EDITABLE_FIELDS = {
    "nivel",
    "ativo",
    "acesso_laboratorio",
    "somente_laboratorio",
    "senha",
}


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    if isinstance(target, (str, bytes, os.PathLike, db_core.DatabaseTarget)):
        return db_core.connect(target), True
    raise TypeError("Destino ou conexao de banco invalido.")


def _insert_id(conn, statement, parameters):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        row = conn.execute(
            statement.rstrip().rstrip(";") + " RETURNING id_usuario",
            parameters,
        ).fetchone()
        return row[0]
    return conn.execute(statement, parameters).lastrowid


def listar(target):
    conn, close = _open_connection(target)
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM usuarios ORDER BY nivel, nome"
            ).fetchall()
        ]
    finally:
        if close:
            conn.close()


def criar(target, dados, agora=None):
    usuario = str(dados.get("usuario") or "").strip().lower()
    nome = str(dados.get("nome") or "").strip()
    nivel = str(dados.get("nivel") or "visualizador").strip()
    senha = str(dados.get("senha") or "").strip()
    acesso_laboratorio = (
        1 if str(dados.get("acesso_laboratorio") or "0") == "1" else 0
    )
    somente_laboratorio = (
        1 if str(dados.get("somente_laboratorio") or "0") == "1" else 0
    )
    if somente_laboratorio:
        acesso_laboratorio = 1
    if not usuario or not nome or not senha:
        raise ValueError("Preencha todos os campos.")
    if not auth.senha_valida(senha):
        raise ValueError(auth.mensagem_senha_invalida())
    if nivel not in VALID_LEVELS:
        raise ValueError("Nivel invalido.")

    conn, close = _open_connection(target)
    try:
        novo_id = _insert_id(
            conn,
            """
            INSERT INTO usuarios
                (usuario, nome, senha_hash, nivel, ativo, criado_em,
                 acesso_laboratorio, somente_laboratorio)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                usuario,
                nome,
                auth.hash_senha(senha),
                nivel,
                agora or datetime.now().isoformat(),
                acesso_laboratorio,
                somente_laboratorio,
            ),
        )
        conn.commit()
        return novo_id
    finally:
        if close:
            conn.close()


def editar(target, uid, campo, valor, usuario_atual_id=None):
    campo = str(campo or "")
    valor = str(valor or "").strip()
    if campo not in EDITABLE_FIELDS:
        raise ValueError("Parametro invalido.")

    conn, close = _open_connection(target)
    try:
        row = conn.execute(
            """
            SELECT usuario, nome, nivel, ativo, acesso_laboratorio,
                   somente_laboratorio
              FROM usuarios
             WHERE id_usuario=?
            """,
            (uid,),
        ).fetchone()
        if not row:
            raise ValueError("Usuario nao encontrado.")
        anterior = dict(row)

        if campo == "nivel" and valor in VALID_LEVELS:
            novo = valor
            conn.execute(
                "UPDATE usuarios SET nivel=? WHERE id_usuario=?",
                (novo, uid),
            )
        elif campo == "ativo" and valor in ("0", "1"):
            if uid == usuario_atual_id:
                raise ValueError("Voce nao pode desativar sua propria conta.")
            novo = int(valor)
            conn.execute(
                "UPDATE usuarios SET ativo=? WHERE id_usuario=?",
                (novo, uid),
            )
        elif campo == "acesso_laboratorio" and valor in ("0", "1"):
            novo = int(valor)
            if novo == 0:
                conn.execute(
                    """
                    UPDATE usuarios
                       SET acesso_laboratorio=0, somente_laboratorio=0
                     WHERE id_usuario=?
                    """,
                    (uid,),
                )
            else:
                conn.execute(
                    """
                    UPDATE usuarios
                       SET acesso_laboratorio=1
                     WHERE id_usuario=?
                    """,
                    (uid,),
                )
        elif campo == "somente_laboratorio" and valor in ("0", "1"):
            novo = int(valor)
            conn.execute(
                """
                UPDATE usuarios
                   SET somente_laboratorio=?, acesso_laboratorio=1
                 WHERE id_usuario=?
                """,
                (novo, uid),
            )
        elif campo == "senha" and auth.senha_valida(valor):
            novo = "***"
            conn.execute(
                "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                (auth.hash_senha(valor), uid),
            )
        else:
            raise ValueError("Parametro invalido.")

        conn.commit()
        return anterior, novo
    finally:
        if close:
            conn.close()


def resetar_senha(target, uid, nova_senha):
    if not auth.senha_valida(nova_senha):
        raise ValueError(auth.mensagem_senha_invalida())
    conn, close = _open_connection(target)
    try:
        row = conn.execute(
            "SELECT usuario, nome FROM usuarios WHERE id_usuario=?",
            (uid,),
        ).fetchone()
        if not row:
            raise ValueError("Usuario nao encontrado.")
        conn.execute(
            "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
            (auth.hash_senha(nova_senha), uid),
        )
        conn.commit()
        return dict(row)
    finally:
        if close:
            conn.close()
