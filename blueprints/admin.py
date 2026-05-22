import secrets
import string
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh


bp = Blueprint("admin", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.route("/admin/usuarios")
@login_required
@nivel_min("admin")
def admin_usuarios():
    usuarios = bh.q("SELECT * FROM usuarios ORDER BY nivel, nome")
    return render_template("admin_usuarios.html", usuarios=usuarios)


@bp.route("/admin/usuarios/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_criar_usuario():
    usuario = request.form.get("usuario", "").strip().lower()
    nome = request.form.get("nome", "").strip()
    nivel = request.form.get("nivel", "visualizador")
    senha = request.form.get("senha", "").strip()
    erro = None
    if not usuario or not nome or not senha:
        erro = "Preencha todos os campos."
    elif len(senha) < 6:
        erro = "A senha deve ter ao menos 6 caracteres."
    elif nivel not in ("admin", "operador", "visualizador"):
        erro = "Nivel invalido."
    else:
        try:
            conn = bh.get_db()
            cur = conn.execute("""INSERT INTO usuarios (usuario,nome,senha_hash,nivel,ativo,criado_em)
                                  VALUES (?,?,?,?,1,?)""",
                               (usuario, nome, auth_core.hash_senha(senha), nivel, datetime.now().isoformat()))
            conn.commit()
            novo_id = cur.lastrowid
            conn.close()
            audit.registrar_evento(
                bh.get_db,
                "usuario_criado",
                entidade="usuarios",
                entidade_id=novo_id,
                detalhes={"usuario": usuario, "nome": nome, "nivel": nivel},
            )
        except Exception as e:
            erro = f"Erro: {e}"
    if erro:
        usuarios = bh.q("SELECT * FROM usuarios ORDER BY nivel, nome")
        return render_template("admin_usuarios.html", usuarios=usuarios, erro=erro)
    return redirect(url_for("admin.admin_usuarios"))


@bp.route("/admin/usuarios/<int:uid>/editar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_editar_usuario(uid):
    campo = request.form.get("campo")
    valor = request.form.get("valor", "").strip()
    conn = bh.get_db()
    anterior = conn.execute("SELECT usuario,nome,nivel,ativo FROM usuarios WHERE id_usuario=?", (uid,)).fetchone()
    if campo == "nivel" and valor in ("admin", "operador", "visualizador"):
        conn.execute("UPDATE usuarios SET nivel=? WHERE id_usuario=?", (valor, uid))
    elif campo == "ativo" and valor in ("0", "1"):
        if uid == session.get("uid"):
            conn.close()
            return jsonify({"erro": "Voce nao pode desativar sua propria conta."}), 400
        conn.execute("UPDATE usuarios SET ativo=? WHERE id_usuario=?", (int(valor), uid))
    elif campo == "senha" and len(valor) >= 6:
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?", (auth_core.hash_senha(valor), uid))
    else:
        conn.close()
        return jsonify({"erro": "Parametro invalido."}), 400
    conn.commit()
    conn.close()
    detalhes = {"campo": campo}
    if anterior:
        detalhes.update({
            "usuario": anterior["usuario"],
            "valor_antigo": anterior[campo] if campo in anterior.keys() else None,
        })
    detalhes["valor_novo"] = "***" if campo == "senha" else valor
    audit.registrar_evento(
        bh.get_db,
        "usuario_editado",
        entidade="usuarios",
        entidade_id=uid,
        detalhes=detalhes,
    )
    return jsonify({"ok": True})


@bp.route("/admin/usuarios/<int:uid>/resetar-senha", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_resetar_senha(uid):
    nova = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
    conn = bh.get_db()
    alvo = conn.execute("SELECT usuario,nome FROM usuarios WHERE id_usuario=?", (uid,)).fetchone()
    conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?", (auth_core.hash_senha(nova), uid))
    conn.commit()
    conn.close()
    audit.registrar_evento(
        bh.get_db,
        "usuario_senha_resetada",
        entidade="usuarios",
        entidade_id=uid,
        detalhes={"usuario": alvo["usuario"] if alvo else None, "nome": alvo["nome"] if alvo else None},
    )
    return jsonify({"ok": True, "senha": nova})
