"""Lógica específica do formulário de atualização de Registro Geográfico."""

from app_core import db as db_core
from app_core import escopo_agente
from app_core import formularios as formularios_core
from app_core import registro_geografico as rg_core


TIPO = "rg_atualizacao"


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True


def snapshot(target, selecoes):
    """Referências para o campo: quarteirões + logradouros existentes + tipos.

    ``selecoes`` é uma lista de dicts ``{id_localidade, quarteirao}``.
    """
    conn, close = _open_connection(target)
    try:
        rg_core.ensure_schema(conn)
        resultado = []
        for sel in selecoes:
            id_localidade = _int(sel.get("id_localidade"))
            quarteirao = rg_core._quarteirao(sel.get("quarteirao"))
            if not id_localidade or not quarteirao:
                continue
            loc = conn.execute(
                "SELECT id_localidade, nome FROM localidades WHERE id_localidade=?",
                (id_localidade,),
            ).fetchone()
            if not loc:
                continue
            logradouros = [
                r[0]
                for r in conn.execute(
                    """SELECT DISTINCT logradouro
                         FROM registro_geografico_imoveis
                        WHERE id_localidade=? AND quarteirao=?
                          AND TRIM(COALESCE(logradouro,''))<>''
                        ORDER BY logradouro""",
                    (id_localidade, quarteirao),
                )
            ]
            resultado.append({
                "id_localidade": id_localidade,
                "localidade": loc["nome"],
                "quarteirao": quarteirao,
                "quarteirao_exibicao": rg_core._quarteirao_display(quarteirao),
                "logradouros": logradouros,
            })
        tipos = [{"codigo": codigo, "nome": nome} for codigo, nome in rg_core.TIPOS.items()]
        return {"selecoes": resultado, "tipos": tipos}
    finally:
        if close:
            conn.close()


def oficializar(target, id_formulario, usuario):
    """Aplica o payload aprovado no RG (substitui o quarteirão) e oficializa."""
    conn = db_core.connect(target)
    try:
        # Preparação fora da transação: executescript do SQLite pode confirmar.
        rg_core.ensure_schema(conn)
        formularios_core.ensure_schema(conn)
        conn.commit()
        if getattr(conn, "backend", "sqlite") == "postgresql":
            conn.execute("SELECT id_formulario FROM formularios WHERE id_formulario=? FOR UPDATE", (id_formulario,))
        else:
            conn.execute("BEGIN IMMEDIATE")
        form = formularios_core.obter(conn, id_formulario)
        if not form:
            raise ValueError("Formulário não encontrado.")
        if form["tipo_formulario"] != TIPO:
            raise ValueError("Formulário não é de atualização de RG.")
        if form["status"] != formularios_core.STATUS_APROVADO:
            raise ValueError("Somente formulários aprovados podem ser oficializados.")
        usuario = usuario or {}
        rg_core.salvar_quarteirao(
            target, form["payload"] or {}, conexao=conn,
            usuario_id=usuario.get("id_usuario"),
            usuario_nome=usuario.get("nome") or usuario.get("usuario"),
        )
        formularios_core.marcar_oficializado(conn, id_formulario, usuario, commit=False)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def contexto(target, usuario):
    """Agente vinculado ao usuário logado + lista de agentes ativos."""
    conn, close = _open_connection(target)
    try:
        agentes = [
            db_core.serialize_row(r)
            for r in conn.execute(
                "SELECT id_agente, nome FROM agentes WHERE COALESCE(ativo,1)=1 ORDER BY nome"
            )
        ]
    finally:
        if close:
            conn.close()
    agente = escopo_agente.agente_proprio(target, usuario or {})
    return {
        "agente_proprio": (
            {"id_agente": agente["id_agente"], "nome": agente["nome"]} if agente else None
        ),
        "agentes": escopo_agente.catalogo(target, usuario, agentes),
    }
