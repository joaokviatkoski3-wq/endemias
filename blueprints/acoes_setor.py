from datetime import datetime
import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import unicodedata
import uuid

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh


bp = Blueprint("acoes_setor", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min

TIPOS_ACAO = {
    "educativa": "Ação educativa / palestra",
    "limpeza": "Ação de limpeza / mutirão",
}
ANEXO_EXTENSOES = {".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
ANEXO_MAX_BYTES = 20 * 1024 * 1024


def ensure_schema(conn=None):
    fechar = False
    if conn is None:
        conn = bh.get_db()
        fechar = True
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS acoes_setor (
            id_acao INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ('educativa','limpeza')),
            data TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fim TEXT,
            localidade TEXT,
            endereco TEXT,
            local TEXT,
            publico_aproximado INTEGER,
            tema TEXT,
            contexto TEXT,
            coordenadas TEXT,
            observacoes TEXT,
            criado_por TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS acoes_setor_agentes (
            id_acao INTEGER NOT NULL REFERENCES acoes_setor(id_acao) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_acao, id_agente)
        );
        CREATE TABLE IF NOT EXISTS acoes_setor_anexos (
            id_anexo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_acao INTEGER NOT NULL REFERENCES acoes_setor(id_acao) ON DELETE CASCADE,
            nome_original TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            caminho_rel TEXT NOT NULL,
            mime_type TEXT,
            tamanho INTEGER NOT NULL DEFAULT 0,
            criado_por TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_data ON acoes_setor(data);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_tipo ON acoes_setor(tipo);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_localidade ON acoes_setor(localidade);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_agente ON acoes_setor_agentes(id_agente);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_anexo_acao ON acoes_setor_anexos(id_acao);
        """)
        conn.commit()
    finally:
        if fechar:
            conn.close()


def _normaliza_busca(value):
    texto = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in texto if unicodedata.category(ch) != "Mn").casefold()


def _parse_data(value):
    texto = str(value or "").strip()
    if not texto:
        raise ValueError("Informe a data da ação.")
    try:
        datetime.strptime(texto[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Data inválida.") from exc
    return texto[:10]


def _parse_hora(value):
    texto = str(value or "").strip()
    if not texto:
        return None
    try:
        datetime.strptime(texto[:5], "%H:%M")
    except ValueError as exc:
        raise ValueError("Horário inválido.") from exc
    return texto[:5]


def _parse_publico(value):
    if value in (None, ""):
        return None
    try:
        numero = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Público aproximado inválido.") from exc
    if numero < 0:
        raise ValueError("Público aproximado não pode ser negativo.")
    return numero


def _parse_agentes(value):
    ids = []
    for item in value or []:
        try:
            id_agente = int(item)
        except (TypeError, ValueError):
            continue
        if id_agente > 0 and id_agente not in ids:
            ids.append(id_agente)
    return ids


def _acao_payload(dados):
    tipo = (dados.get("tipo") or "").strip()
    if tipo not in TIPOS_ACAO:
        raise ValueError("Tipo de ação inválido.")
    payload = {
        "tipo": tipo,
        "data": _parse_data(dados.get("data")),
        "hora_inicio": _parse_hora(dados.get("hora_inicio")),
        "hora_fim": _parse_hora(dados.get("hora_fim")),
        "localidade": (dados.get("localidade") or "").strip() or None,
        "endereco": (dados.get("endereco") or "").strip() or None,
        "local": (dados.get("local") or "").strip() or None,
        "publico_aproximado": _parse_publico(dados.get("publico_aproximado")),
        "tema": (dados.get("tema") or "").strip() or None,
        "contexto": (dados.get("contexto") or "").strip() or None,
        "coordenadas": (dados.get("coordenadas") or "").strip() or None,
        "observacoes": (dados.get("observacoes") or "").strip() or None,
        "agentes": _parse_agentes(dados.get("agentes")),
    }
    return payload


def _acao_dict(row):
    item = dict(row)
    item["tipo_label"] = TIPOS_ACAO.get(item.get("tipo"), item.get("tipo") or "")
    item["agentes"] = [
        {"id_agente": int(x.split(":", 1)[0]), "nome": x.split(":", 1)[1]}
        for x in (item.pop("agentes_raw") or "").split("|")
        if ":" in x
    ]
    item["agentes_nomes"] = ", ".join(a["nome"] for a in item["agentes"])
    return item


def _base_query():
    return """
        SELECT a.*,
               GROUP_CONCAT(ag.id_agente || ':' || ag.nome, '|') AS agentes_raw
          FROM acoes_setor a
          LEFT JOIN acoes_setor_agentes aa ON aa.id_acao = a.id_acao
          LEFT JOIN agentes ag ON ag.id_agente = aa.id_agente
    """


def _salvar_agentes(conn, id_acao, agentes):
    conn.execute("DELETE FROM acoes_setor_agentes WHERE id_acao=?", (id_acao,))
    for id_agente in agentes:
        conn.execute(
            "INSERT OR IGNORE INTO acoes_setor_agentes (id_acao, id_agente) VALUES (?, ?)",
            (id_acao, id_agente),
        )


def _anexos_base_dir():
    base = Path(current_app.config["ANEXOS_DIR"]).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _acao_anexos_dir(id_acao, data=None):
    ano = str(data or datetime.now().year)[:4]
    caminho = _anexos_base_dir() / "acoes_setor" / ano / str(id_acao).zfill(6)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _path_anexo(caminho_rel):
    base = _anexos_base_dir()
    caminho = (base / caminho_rel).resolve()
    if base not in caminho.parents and caminho != base:
        abort(404)
    return caminho


def _anexo_dict(row):
    item = dict(row)
    item["url_download"] = f"/acoes-setor/anexos/{item['id_anexo']}/download"
    item["url_visualizar"] = f"/acoes-setor/anexos/{item['id_anexo']}/download?inline=1"
    item["eh_previa"] = (item.get("mime_type") or "").startswith("image/") or item.get("mime_type") == "application/pdf"
    return item


def _listar_anexos(id_acao):
    return [
        _anexo_dict(row) for row in bh.q(
            """SELECT * FROM acoes_setor_anexos
               WHERE id_acao=?
               ORDER BY criado_em DESC, id_anexo DESC""",
            (id_acao,),
        )
    ]


def _validar_upload_anexo(arquivo):
    nome_original = arquivo.filename or ""
    nome_seguro = secure_filename(nome_original)
    if not nome_seguro:
        return None, "Nome de arquivo inválido."
    ext = Path(nome_seguro).suffix.lower()
    if ext not in ANEXO_EXTENSOES:
        return None, "Tipo de arquivo não permitido."
    pos = arquivo.stream.tell()
    arquivo.stream.seek(0, os.SEEK_END)
    tamanho = arquivo.stream.tell()
    arquivo.stream.seek(pos)
    if tamanho <= 0:
        return None, "Arquivo vazio."
    if tamanho > ANEXO_MAX_BYTES:
        return None, "Arquivo maior que 20 MB."
    return {"nome_original": nome_original, "nome_seguro": nome_seguro, "ext": ext, "tamanho": tamanho}, ""


def _remover_arquivos_anexos(rows):
    for row in rows:
        try:
            caminho = _path_anexo(row["caminho_rel"])
            if caminho.exists() and caminho.is_file():
                caminho.unlink()
        except Exception:
            pass


@bp.route("/acoes-setor")
@login_required
@nivel_min("operador")
def page():
    ensure_schema()
    agentes = bh.q(
        "SELECT id_agente, nome FROM agentes WHERE COALESCE(ativo,1)=1 ORDER BY nome"
    )
    localidades = bh.q("SELECT nome FROM localidades ORDER BY nome")
    return render_template(
        "acoes_setor.html",
        tipos_acao=TIPOS_ACAO,
        agentes=agentes,
        localidades=[row["nome"] for row in localidades],
    )


@bp.route("/api/acoes-setor", methods=["GET", "POST"])
@login_required
@nivel_min("operador")
def api_acoes():
    ensure_schema()
    if request.method == "POST":
        try:
            payload = _acao_payload(request.json or {})
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400

        usuario = bh.usuario_atual() or {}
        conn = None
        try:
            conn = bh.get_db()
            cur = conn.execute(
                """INSERT INTO acoes_setor
                   (tipo, data, hora_inicio, hora_fim, localidade, endereco, local,
                    publico_aproximado, tema, contexto, coordenadas, observacoes,
                    criado_por, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["tipo"],
                    payload["data"],
                    payload["hora_inicio"],
                    payload["hora_fim"],
                    payload["localidade"],
                    payload["endereco"],
                    payload["local"],
                    payload["publico_aproximado"],
                    payload["tema"],
                    payload["contexto"],
                    payload["coordenadas"],
                    payload["observacoes"],
                    usuario.get("nome") or "sistema",
                    datetime.now().isoformat(timespec="seconds"),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            id_acao = cur.lastrowid
            _salvar_agentes(conn, id_acao, payload["agentes"])
            conn.commit()
        except sqlite3.OperationalError:
            if conn:
                conn.rollback()
            return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
        finally:
            if conn:
                conn.close()
        return jsonify({"ok": True, "id_acao": id_acao}), 201

    params = []
    where = []
    tipo = (request.args.get("tipo") or "").strip()
    ano = (request.args.get("ano") or "").strip()
    busca = (request.args.get("busca") or "").strip()
    if tipo in TIPOS_ACAO:
        where.append("a.tipo=?")
        params.append(tipo)
    if ano:
        where.append("substr(a.data, 1, 4)=?")
        params.append(ano[:4])

    sql = _base_query()
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY a.id_acao ORDER BY a.data DESC, COALESCE(a.hora_inicio, '') DESC, a.id_acao DESC"
    registros = [_acao_dict(row) for row in bh.q(sql, params)]
    if busca:
        termos = [_normaliza_busca(t) for t in busca.split() if t.strip()]
        registros = [
            r for r in registros
            if all(
                termo in _normaliza_busca(" ".join(str(r.get(c) or "") for c in (
                    "tipo_label", "data", "localidade", "endereco", "local", "tema",
                    "contexto", "coordenadas", "observacoes", "agentes_nomes",
                )))
                for termo in termos
            )
        ]
    return jsonify({"registros": registros, "total": len(registros), "tipos": TIPOS_ACAO})


@bp.route("/api/acoes-setor/<int:id_acao>", methods=["GET", "PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_acao(id_acao):
    ensure_schema()
    if request.method == "GET":
        row = bh.q1(_base_query() + " WHERE a.id_acao=? GROUP BY a.id_acao", (id_acao,))
        if not row:
            return jsonify({"erro": "Ação não encontrada."}), 404
        return jsonify(_acao_dict(row))

    conn = None
    try:
        conn = bh.get_db()
        existe = conn.execute(
            "SELECT 1 FROM acoes_setor WHERE id_acao=?",
            (id_acao,),
        ).fetchone()
        if not existe:
            return jsonify({"erro": "Ação não encontrada."}), 404
        if request.method == "DELETE":
            anexos = conn.execute(
                "SELECT caminho_rel FROM acoes_setor_anexos WHERE id_acao=?",
                (id_acao,),
            ).fetchall()
            conn.execute("DELETE FROM acoes_setor WHERE id_acao=?", (id_acao,))
            conn.commit()
            _remover_arquivos_anexos(anexos)
            try:
                shutil.rmtree(_acao_anexos_dir(id_acao), ignore_errors=True)
            except Exception:
                pass
            return jsonify({"ok": True})

        try:
            payload = _acao_payload(request.json or {})
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400
        conn.execute(
            """UPDATE acoes_setor
                  SET tipo=?, data=?, hora_inicio=?, hora_fim=?, localidade=?,
                      endereco=?, local=?, publico_aproximado=?, tema=?,
                      contexto=?, coordenadas=?, observacoes=?, atualizado_em=?
                WHERE id_acao=?""",
            (
                payload["tipo"],
                payload["data"],
                payload["hora_inicio"],
                payload["hora_fim"],
                payload["localidade"],
                payload["endereco"],
                payload["local"],
                payload["publico_aproximado"],
                payload["tema"],
                payload["contexto"],
                payload["coordenadas"],
                payload["observacoes"],
                datetime.now().isoformat(timespec="seconds"),
                id_acao,
            ),
        )
        _salvar_agentes(conn, id_acao, payload["agentes"])
        conn.commit()
    except sqlite3.OperationalError:
        if conn:
            conn.rollback()
        return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
    finally:
        if conn:
            conn.close()
    return jsonify({"ok": True, "id_acao": id_acao})


@bp.route("/api/acoes-setor/<int:id_acao>/anexos", methods=["GET", "POST"])
@login_required
@nivel_min("operador")
def api_anexos(id_acao):
    ensure_schema()
    acao = bh.q1("SELECT id_acao, data FROM acoes_setor WHERE id_acao=?", (id_acao,))
    if not acao:
        return jsonify({"erro": "Ação não encontrada."}), 404
    if request.method == "GET":
        return jsonify({"anexos": _listar_anexos(id_acao)})

    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    usuario = bh.usuario_atual() or {}
    destino_dir = _acao_anexos_dir(id_acao, acao.get("data"))
    salvos = []
    conn = None
    try:
        conn = bh.get_db()
        for arquivo in arquivos:
            meta, erro = _validar_upload_anexo(arquivo)
            if erro:
                return jsonify({"erro": erro}), 400
            nome_arquivo = f"{uuid.uuid4().hex}{meta['ext']}"
            caminho = destino_dir / nome_arquivo
            arquivo.save(caminho)
            mime_type = mimetypes.guess_type(meta["nome_seguro"])[0] or "application/octet-stream"
            caminho_rel = str(caminho.relative_to(_anexos_base_dir())).replace("\\", "/")
            cur = conn.execute(
                """INSERT INTO acoes_setor_anexos
                   (id_acao, nome_original, nome_arquivo, caminho_rel, mime_type,
                    tamanho, criado_por, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id_acao,
                    meta["nome_original"],
                    nome_arquivo,
                    caminho_rel,
                    mime_type,
                    meta["tamanho"],
                    usuario.get("nome") or "sistema",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            salvos.append(cur.lastrowid)
        conn.commit()
    except sqlite3.OperationalError:
        if conn:
            conn.rollback()
        return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
    finally:
        if conn:
            conn.close()
    return jsonify({"ok": True, "ids": salvos, "anexos": _listar_anexos(id_acao)}), 201


@bp.route("/api/acoes-setor/anexos/<int:id_anexo>", methods=["DELETE"])
@login_required
@nivel_min("operador")
def api_excluir_anexo(id_anexo):
    ensure_schema()
    conn = bh.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM acoes_setor_anexos WHERE id_anexo=?",
            (id_anexo,),
        ).fetchone()
        if not row:
            return jsonify({"erro": "Anexo não encontrado."}), 404
        conn.execute("DELETE FROM acoes_setor_anexos WHERE id_anexo=?", (id_anexo,))
        conn.commit()
    finally:
        conn.close()
    _remover_arquivos_anexos([row])
    return jsonify({"ok": True})


@bp.route("/acoes-setor/anexos/<int:id_anexo>/download")
@login_required
@nivel_min("operador")
def baixar_anexo(id_anexo):
    ensure_schema()
    row = bh.q1("SELECT * FROM acoes_setor_anexos WHERE id_anexo=?", (id_anexo,))
    if not row:
        abort(404)
    caminho = _path_anexo(row["caminho_rel"])
    if not caminho.exists() or not caminho.is_file():
        abort(404)
    inline = request.args.get("inline") == "1"
    return send_file(
        caminho,
        mimetype=row.get("mime_type") or None,
        as_attachment=not inline,
        download_name=row["nome_original"],
        max_age=0,
    )
