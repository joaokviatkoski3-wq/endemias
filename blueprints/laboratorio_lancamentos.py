import logging
from datetime import date, datetime
from functools import wraps

from flask import Blueprint, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import laboratorio_lancamentos as lab_core


bp = Blueprint("laboratorio_lancamentos", __name__)
login_required = auth_core.login_required


def laboratorio_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        usuario = bh.usuario_atual()
        if lab_core.pode_lancar(usuario):
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"erro": "Sem permissão para acessar os lançamentos do laboratório."}), 403
        return render_template("403.html"), 403
    return wrapper


def _int_nao_negativo(value, field):
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido em {field}.") from exc
    if number < 0 or number > 100000:
        raise ValueError(f"Valor inválido em {field}.")
    return number


def _agentes_coleta_sql():
    return """SELECT GROUP_CONCAT(nome, ', ') FROM (
                SELECT DISTINCT a.nome
                  FROM visita_agentes va
                  JOIN agentes a ON a.id_agente=va.id_agente
                 WHERE va.id_visita=v.id_visita
                 ORDER BY a.nome
              )"""


@bp.route("/laboratorio/lancamentos")
@login_required
@laboratorio_required
def page():
    conn = bh.get_db()
    try:
        agentes = conn.execute(
            "SELECT id_agente, nome FROM agentes WHERE ativo=1 ORDER BY nome"
        ).fetchall()
    finally:
        conn.close()
    return render_template(
        "laboratorio_lancamentos.html",
        agentes=[dict(row) for row in agentes],
        hoje=date.today().isoformat(),
    )


@bp.route("/api/laboratorio/lancamentos/pendentes")
@login_required
@laboratorio_required
def pendentes():
    conn = bh.get_db()
    try:
        rows = conn.execute(f"""
            SELECT c.id_coleta, c.num_tubo, c.codigo_deposito, c.tipo_deposito,
                   c.deposito_eliminado, v.id_visita, v.data, v.tipo,
                   COALESCE(l.nome, v.localidade) AS localidade, v.quarteirao,
                   v.logradouro, v.numero, v.visita, v.observacoes,
                   CAST(julianday('now', 'localtime') - julianday(v.data) AS INTEGER) AS dias_pendente,
                   ({_agentes_coleta_sql()}) AS agentes
              FROM coletas c
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
              LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
              LEFT JOIN {lab_core.STATUS_TABLE} st ON st.id_coleta=c.id_coleta
             WHERE rl.id_coleta IS NULL AND st.id_coleta IS NULL
             ORDER BY date(v.data), CAST(c.num_tubo AS INTEGER), c.num_tubo
        """).fetchall()
    finally:
        conn.close()
    return jsonify({"pendentes": [dict(row) for row in rows], "total": len(rows)})


@bp.route("/api/laboratorio/lancamentos/historico")
@login_required
@laboratorio_required
def historico():
    limite = min(max(int(request.args.get("limite", 100)), 1), 500)
    conn = bh.get_db()
    try:
        resultados = conn.execute(f"""
            SELECT 'resultado' AS registro_tipo, rl.id_resultado, rl.id_coleta,
                   rl.num_tubo, rl.data_coleta, rl.data_leitura, rl.laboratorista,
                   COALESCE(rl.origem, 'kobo') AS origem,
                   rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas,
                   rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                   v.tipo, COALESCE(l.nome, v.localidade) AS localidade,
                   v.logradouro, v.numero, v.quarteirao,
                   ({_agentes_coleta_sql()}) AS agentes,
                   NULL AS motivo, NULL AS encerrado_em
              FROM resultados_laboratorio rl
              JOIN coletas c ON c.id_coleta=rl.id_coleta
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
             ORDER BY date(rl.data_leitura) DESC, rl.id_resultado DESC
             LIMIT ?
        """, (limite,)).fetchall()
        encerrados = conn.execute(f"""
            SELECT 'sem_resultado' AS registro_tipo, NULL AS id_resultado, st.id_coleta,
                   c.num_tubo, v.data AS data_coleta, NULL AS data_leitura,
                   NULL AS laboratorista, 'sistema' AS origem,
                   v.tipo, COALESCE(l.nome, v.localidade) AS localidade,
                   v.logradouro, v.numero, v.quarteirao,
                   ({_agentes_coleta_sql()}) AS agentes,
                   st.motivo, st.encerrado_em
              FROM {lab_core.STATUS_TABLE} st
              JOIN coletas c ON c.id_coleta=st.id_coleta
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
             ORDER BY datetime(st.encerrado_em) DESC
             LIMIT ?
        """, (limite,)).fetchall()
    finally:
        conn.close()
    itens = [dict(row) for row in resultados] + [dict(row) for row in encerrados]
    itens.sort(
        key=lambda item: item.get("data_leitura") or item.get("encerrado_em") or "",
        reverse=True,
    )
    return jsonify({"registros": itens[:limite], "total": len(itens[:limite])})


@bp.route("/api/laboratorio/lancamentos/<id_coleta>/resultado", methods=["POST"])
@login_required
@laboratorio_required
def salvar_resultado(id_coleta):
    dados = request.get_json(silent=True) or {}
    try:
        id_laboratorista = int(dados.get("id_laboratorista"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Selecione o laboratorista."}), 400
    try:
        data_leitura = date.fromisoformat(str(dados.get("data_leitura") or "")).isoformat()
    except ValueError:
        return jsonify({"erro": "Informe uma data de leitura válida."}), 400
    try:
        campos = {
            nome: _int_nao_negativo(dados.get(nome), nome)
            for nome in (
                "aegypt_larvas", "aegypt_pupas", "aegypt_exuvias", "aegypt_adulto",
                "albopictus_larvas", "albopictus_pupas", "albopictus_exuvias", "albopictus_adulto",
                "outra_larvas", "outra_pupas", "outra_exuvias", "outra_adulto",
            )
        }
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    conn = bh.get_db()
    try:
        agente = conn.execute(
            "SELECT id_agente, nome FROM agentes WHERE id_agente=? AND ativo=1",
            (id_laboratorista,),
        ).fetchone()
        coleta = conn.execute("""
            SELECT c.id_coleta, c.num_tubo, v.data
              FROM coletas c JOIN visitas v ON v.id_visita=c.id_visita
             WHERE c.id_coleta=?
        """, (id_coleta,)).fetchone()
        if not agente:
            return jsonify({"erro": "Selecione um laboratorista ativo."}), 400
        if not coleta:
            return jsonify({"erro": "Tubo não encontrado."}), 404
        if conn.execute(
            "SELECT 1 FROM resultados_laboratorio WHERE id_coleta=?", (id_coleta,)
        ).fetchone():
            return jsonify({"erro": "Este tubo já possui resultado."}), 409
        if conn.execute(
            f"SELECT 1 FROM {lab_core.STATUS_TABLE} WHERE id_coleta=?", (id_coleta,)
        ).fetchone():
            return jsonify({"erro": "Este tubo foi encerrado sem resultado."}), 409

        agora = datetime.now().isoformat()
        colunas = ", ".join(campos)
        placeholders = ", ".join("?" for _ in campos)
        cur = conn.execute(f"""
            INSERT INTO resultados_laboratorio (
                id_coleta, num_tubo, data_coleta, laboratorista, id_laboratorista,
                data_leitura, {colunas}, origem, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, {placeholders}, 'sistema', ?, ?)
        """, (
            id_coleta, coleta["num_tubo"], coleta["data"], agente["nome"],
            agente["id_agente"], data_leitura, *campos.values(), agora, agora,
        ))
        conn.commit()
        id_resultado = cur.lastrowid
    except Exception:
        conn.rollback()
        logging.exception("Erro ao salvar resultado laboratorial")
        return jsonify({"erro": "Não foi possível salvar o resultado."}), 500
    finally:
        conn.close()

    audit.registrar_evento(
        bh.get_db,
        "resultado_laboratorio_criado",
        entidade="resultados_laboratorio",
        entidade_id=id_resultado,
        detalhes={
            "id_coleta": id_coleta,
            "num_tubo": coleta["num_tubo"],
            "laboratorista": agente["nome"],
            "data_leitura": data_leitura,
            "origem": "sistema",
            "total": sum(campos.values()),
        },
    )
    return jsonify({"ok": True, "id_resultado": id_resultado})
