import logging
from datetime import date, datetime, timedelta
from functools import wraps
import re
import unicodedata

from flask import Blueprint, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import focos_positivos as focos_core
from app_core import laboratorio_lancamentos as lab_core
from app_core import ovitrampas_laboratorio as ovi_lab_core


bp = Blueprint("laboratorio_lancamentos", __name__)
login_required = auth_core.login_required

CAMPOS_CONTAGEM = (
    "aegypt_larvas", "aegypt_pupas", "aegypt_exuvias", "aegypt_adulto",
    "albopictus_larvas", "albopictus_pupas", "albopictus_exuvias", "albopictus_adulto",
    "outra_larvas", "outra_pupas", "outra_exuvias", "outra_adulto",
)


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


def _agentes_coleta_sql(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        aggregate = "string_agg(nomes.nome, ', ' ORDER BY nomes.nome)"
    else:
        aggregate = "GROUP_CONCAT(nomes.nome, ', ')"
    return f"""SELECT {aggregate} FROM (
                   SELECT DISTINCT a.nome
                     FROM visita_agentes va
                     JOIN agentes a ON a.id_agente=va.id_agente
                    WHERE va.id_visita=v.id_visita
                ) nomes"""


def _dias_pendente_sql(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return "CURRENT_DATE - v.data"
    return "CAST(julianday('now', 'localtime') - julianday(v.data) AS INTEGER)"


def _numeric_text_order(conn, expression):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return (
            f"CAST(NULLIF(substring(CAST({expression} AS TEXT) "
            "FROM '^[0-9]+'), '') AS BIGINT)"
        )
    return f"CAST({expression} AS INTEGER)"


def _contagens(dados):
    return {
        nome: _int_nao_negativo(dados.get(nome), nome)
        for nome in CAMPOS_CONTAGEM
    }


def _agente_da_conta(conn):
    usuario = bh.usuario_atual()
    if not usuario:
        return None

    id_agente = usuario.get("id_agente")
    if id_agente:
        return conn.execute(
            "SELECT id_agente, nome FROM agentes WHERE id_agente=? AND ativo=1",
            (id_agente,),
        ).fetchone()

    nomes_conta = {
        _chave_identidade(usuario.get("nome")),
        _chave_identidade(usuario.get("usuario")),
    }
    nomes_conta.discard("")
    for agente in conn.execute(
        "SELECT id_agente, nome, nome_completo FROM agentes WHERE ativo=1 ORDER BY nome"
    ).fetchall():
        nomes_agente = {
            _chave_identidade(agente["nome"]),
            _chave_identidade(agente["nome_completo"]),
        }
        if nomes_conta & nomes_agente:
            return agente
    return None


def _chave_identidade(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", texto.casefold())


def _resultado_editavel(row, hoje=None):
    if (row["origem"] or "kobo") != "sistema":
        return False
    referencia = str(row["criado_em"] or row["data_leitura"] or "")[:10]
    try:
        dias = (hoje or date.today()) - date.fromisoformat(referencia)
    except ValueError:
        return False
    return timedelta(0) <= dias <= timedelta(days=3)


def _agente_para_edicao(conn, dados, usuario):
    if (usuario or {}).get("nivel") != "admin":
        raise PermissionError(
            "Somente administradores podem alterar o laboratorista da leitura."
        )
    try:
        id_agente = int(dados.get("id_laboratorista"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Selecione um laboratorista ativo.") from exc
    agente = conn.execute(
        "SELECT id_agente, nome FROM agentes WHERE id_agente=? AND ativo=1",
        (id_agente,),
    ).fetchone()
    if not agente:
        raise ValueError("Selecione um laboratorista ativo.")
    return agente


@bp.route("/laboratorio/lancamentos")
@login_required
@laboratorio_required
def page():
    usuario = bh.usuario_atual() or {}
    conn = bh.get_db()
    try:
        agentes = [db_core.serialize_row(row) for row in conn.execute(
            "SELECT id_agente, nome FROM agentes WHERE ativo=1 ORDER BY nome"
        ).fetchall()]
        laboratoristas = [db_core.serialize_row(row) for row in conn.execute(
            """SELECT id_usuario, nome
                 FROM usuarios
                WHERE ativo=1
                  AND (nivel='admin' OR COALESCE(acesso_laboratorio,0)=1)
             ORDER BY nome"""
        ).fetchall()]
    finally:
        conn.close()
    return render_template(
        "laboratorio_lancamentos.html",
        is_admin=usuario.get("nivel") == "admin",
        agentes=agentes,
        laboratoristas=laboratoristas,
    )


@bp.route("/api/laboratorio/lancamentos/pendentes")
@login_required
@laboratorio_required
def pendentes():
    conn = bh.get_db()
    try:
        agentes_sql = _agentes_coleta_sql(conn)
        dias_sql = _dias_pendente_sql(conn)
        tubo_order = _numeric_text_order(conn, "c.num_tubo")
        rows = conn.execute(f"""
            SELECT c.id_coleta, c.num_tubo, c.codigo_deposito, c.tipo_deposito,
                   c.deposito_eliminado, v.id_visita, v.data, v.tipo,
                   COALESCE(l.nome, v.localidade) AS localidade, v.quarteirao,
                   v.logradouro, v.numero, v.visita, v.observacoes,
                   {dias_sql} AS dias_pendente,
                   ({agentes_sql}) AS agentes
              FROM coletas c
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
              LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
             LEFT JOIN {lab_core.STATUS_TABLE} st ON st.id_coleta=c.id_coleta
             WHERE rl.id_coleta IS NULL AND st.id_coleta IS NULL
             ORDER BY v.data, {tubo_order}, c.num_tubo
        """).fetchall()
    finally:
        conn.close()
    return jsonify({
        "pendentes": [db_core.serialize_row(row) for row in rows],
        "total": len(rows),
    })


@bp.route("/api/laboratorio/lancamentos/historico")
@login_required
@laboratorio_required
def historico():
    limite = min(max(int(request.args.get("limite", 100)), 1), 500)
    conn = bh.get_db()
    try:
        agentes_sql = _agentes_coleta_sql(conn)
        resultados = conn.execute(f"""
            SELECT 'resultado' AS registro_tipo, rl.id_resultado, rl.id_coleta,
                   rl.num_tubo, rl.data_coleta, rl.data_leitura, rl.laboratorista,
                   rl.id_laboratorista,
                   COALESCE(rl.origem, 'kobo') AS origem, rl.criado_em, rl.atualizado_em,
                   rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas,
                   rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                   v.tipo, COALESCE(l.nome, v.localidade) AS localidade,
                   v.logradouro, v.numero, v.quarteirao,
                   ({agentes_sql}) AS agentes
              FROM resultados_laboratorio rl
              JOIN coletas c ON c.id_coleta=rl.id_coleta
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
             ORDER BY rl.data_leitura DESC, rl.id_resultado DESC
             LIMIT ?
        """, (limite,)).fetchall()
    finally:
        conn.close()
    itens = []
    for row in resultados:
        item = db_core.serialize_row(row)
        item["editavel"] = _resultado_editavel(row)
        item["positivo_aegypti"] = any(
            int(item.get(nome) or 0) > 0 for nome in CAMPOS_CONTAGEM[:4]
        )
        itens.append(item)
    return jsonify({"registros": itens, "total": len(itens)})


@bp.route("/api/laboratorio/ovitrampas/lotes")
@login_required
@laboratorio_required
def ovitrampas_lotes():
    historico = request.args.get("historico") == "1"
    return jsonify(ovi_lab_core.listar_para_laboratorista(
        bh.db_target(), historico=historico,
    ))


@bp.route("/api/laboratorio/ovitrampas/lotes/<int:id_lote>")
@login_required
@laboratorio_required
def ovitrampas_lote(id_lote):
    try:
        return jsonify(ovi_lab_core.obter_lote(bh.db_target(), id_lote))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 404


@bp.route("/api/laboratorio/ovitrampas/lotes/<int:id_lote>/rascunho", methods=["PUT"])
@login_required
@laboratorio_required
def ovitrampas_lote_rascunho(id_lote):
    dados = request.get_json(silent=True) or {}
    usuario = dict(bh.usuario_atual() or {})
    try:
        lote = ovi_lab_core.salvar_rascunho(
            bh.db_target(), id_lote, dados.get("leituras"), usuario,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "lote": lote})


@bp.route("/api/laboratorio/ovitrampas/lotes/<int:id_lote>/concluir", methods=["POST"])
@login_required
@laboratorio_required
def ovitrampas_lote_concluir(id_lote):
    dados = request.get_json(silent=True) or {}
    usuario = dict(bh.usuario_atual() or {})
    try:
        lote = ovi_lab_core.concluir_lote(
            bh.db_target(), id_lote, dados.get("leituras"), usuario,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "ovitrampas_leitura_lote_concluido",
        entidade="ovitrampas_laboratorio_lotes",
        entidade_id=id_lote,
        detalhes={
            "diario": lote["diario_nome"],
            "data_movimento": lote["data_movimento"],
            "movimento": lote["movimento"],
            "armadilhas": lote["armadilhas"],
            "ovos": lote["ovos"],
            "laboratorista": lote["laboratorista_nome"],
        },
    )
    return jsonify({"ok": True, "lote": lote})


@bp.route("/api/laboratorio/ovitrampas/lotes/<int:id_lote>/laboratorista", methods=["PUT"])
@login_required
@laboratorio_required
def ovitrampas_lote_laboratorista(id_lote):
    usuario = bh.usuario_atual() or {}
    if usuario.get("nivel") != "admin":
        return jsonify({
            "erro": "Somente administradores podem alterar o laboratorista da leitura."
        }), 403
    dados = request.get_json(silent=True) or {}
    try:
        resultado = ovi_lab_core.atualizar_laboratorista(
            bh.db_target(), id_lote, dados.get("id_laboratorista"),
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "ovitrampas_leitura_laboratorista_editado",
        entidade="ovitrampas_laboratorio_lotes",
        entidade_id=id_lote,
        detalhes={
            "laboratorista_anterior": resultado["anterior"],
            "laboratorista_novo": resultado["lote"]["laboratorista_nome"],
        },
    )
    return jsonify({"ok": True, "lote": resultado["lote"]})


@bp.route("/api/laboratorio/lancamentos/<id_coleta>/resultado", methods=["POST"])
@login_required
@laboratorio_required
def salvar_resultado(id_coleta):
    dados = request.get_json(silent=True) or {}
    try:
        campos = _contagens(dados)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    conn = bh.get_db()
    try:
        agente = _agente_da_conta(conn)
        coleta = conn.execute("""
            SELECT c.id_coleta, c.num_tubo, v.data, v.id_visita
              FROM coletas c JOIN visitas v ON v.id_visita=c.id_visita
             WHERE c.id_coleta=?
        """, (id_coleta,)).fetchone()
        if not agente:
            return jsonify({
                "erro": "O nome desta conta não corresponde a um agente ativo. Contate o administrador."
            }), 400
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
        data_leitura = date.today().isoformat()
        colunas = ", ".join(campos)
        placeholders = ", ".join("?" for _ in campos)
        id_resultado = db_core.insert_and_get_id(
            conn,
            f"""
                INSERT INTO resultados_laboratorio (
                    id_coleta, num_tubo, data_coleta, laboratorista, id_laboratorista,
                    data_leitura, {colunas}, origem, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, {placeholders}, 'sistema', ?, ?)
            """,
            (
                id_coleta, coleta["num_tubo"], coleta["data"], agente["nome"],
                agente["id_agente"], data_leitura, *campos.values(), agora, agora,
            ),
            "id_resultado",
        )
        foco = focos_core.sincronizar_foco_visita(
            conn, coleta["id_visita"], agora,
        )
        conn.commit()
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
            "id_foco": foco["id_foco"],
            "gera_notificacao": foco["gera_notificacao"],
        },
    )
    return jsonify({"ok": True, "id_resultado": id_resultado})


@bp.route("/api/laboratorio/lancamentos/resultados/<int:id_resultado>/editar", methods=["POST"])
@login_required
@laboratorio_required
def editar_resultado(id_resultado):
    dados = request.get_json(silent=True) or {}
    try:
        campos = _contagens(dados)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    conn = bh.get_db()
    try:
        usuario = bh.usuario_atual() or {}
        resultado = conn.execute(
            """SELECT rl.id_resultado, rl.id_coleta, rl.num_tubo,
                      rl.data_leitura, rl.origem, rl.criado_em, c.id_visita,
                      rl.laboratorista, rl.id_laboratorista
                 FROM resultados_laboratorio rl
                 JOIN coletas c ON c.id_coleta=rl.id_coleta
                WHERE rl.id_resultado=?""",
            (id_resultado,),
        ).fetchone()
        if not resultado:
            return jsonify({"erro": "Resultado não encontrado."}), 404
        if not _resultado_editavel(resultado):
            return jsonify({
                "erro": "Somente lançamentos feitos no sistema há até 3 dias podem ser editados."
            }), 403
        if "id_laboratorista" in dados:
            try:
                agente = _agente_para_edicao(conn, dados, usuario)
            except PermissionError as exc:
                return jsonify({"erro": str(exc)}), 403
            except ValueError as exc:
                return jsonify({"erro": str(exc)}), 400
        else:
            agente = {
                "id_agente": resultado["id_laboratorista"],
                "nome": resultado["laboratorista"],
            }

        agora = datetime.now().isoformat()
        sets = ", ".join(f"{nome}=?" for nome in campos)
        conn.execute(
            f"""UPDATE resultados_laboratorio
                   SET {sets}, laboratorista=?, id_laboratorista=?, atualizado_em=?
                 WHERE id_resultado=?""",
            (*campos.values(), agente["nome"], agente["id_agente"], agora, id_resultado),
        )
        foco = focos_core.sincronizar_foco_visita(
            conn, resultado["id_visita"], agora,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Erro ao editar resultado laboratorial")
        return jsonify({"erro": "Não foi possível editar o resultado."}), 500
    finally:
        conn.close()

    audit.registrar_evento(
        bh.get_db,
        "resultado_laboratorio_editado",
        entidade="resultados_laboratorio",
        entidade_id=id_resultado,
        detalhes={
            "id_coleta": resultado["id_coleta"],
            "num_tubo": resultado["num_tubo"],
            "laboratorista_anterior": resultado["laboratorista"],
            "laboratorista": agente["nome"],
            "total": sum(campos.values()),
            "id_foco": foco["id_foco"],
            "gera_notificacao": foco["gera_notificacao"],
        },
    )
    return jsonify({"ok": True, "id_resultado": id_resultado})
