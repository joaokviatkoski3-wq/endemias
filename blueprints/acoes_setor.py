from datetime import datetime
import io
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import unicodedata
import uuid
import zipfile

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
PERIODOS_ACAO = {
    "manha": "Manhã",
    "tarde": "Tarde",
}
TIPOS_ATIVIDADE_REALIZADA = {
    "palestra": "Palestra",
    "teatro_educativo": "Teatro Educativo",
    "exposicao": "Exposição",
    "oficina": "Oficina",
    "conversa_educativa": "Conversa Educativa",
    "outro": "Outro",
}
PUBLICOS_ALVO = {
    "educacao_infantil": "Educação Infantil",
    "funcionarios": "Funcionários",
    "ensino_fundamental": "Ensino Fundamental",
    "comunidade_escolar": "Comunidade Escolar",
    "professores": "Professores",
    "outro": "Outro",
}
RECURSOS_UTILIZADOS = {
    "banner": "Banner",
    "fantasias": "Fantasias",
    "cartazes": "Cartazes",
    "material_trabalho_demonstrativo": "Material de trabalho demonstrativo",
    "videos_imagens_midia_digital": "Vídeos/Imagens/Mídia digital",
    "maquete": "Maquete",
    "outros": "Outros",
}
ANEXO_EXTENSOES = {".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
ANEXO_MAX_BYTES = 20 * 1024 * 1024


def _table_cols(conn, table):
    return {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


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
            periodo TEXT,
            hora_inicio TEXT,
            hora_fim TEXT,
            localidade TEXT,
            endereco TEXT,
            local TEXT,
            publico_aproximado INTEGER,
            tipo_atividade_realizada TEXT,
            publico_alvo TEXT,
            recurso_utilizado TEXT,
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
        cols = _table_cols(conn, "acoes_setor")
        for coluna in (
            "periodo",
            "tipo_atividade_realizada",
            "publico_alvo",
            "recurso_utilizado",
        ):
            if coluna not in cols:
                conn.execute(f"ALTER TABLE acoes_setor ADD COLUMN {coluna} TEXT")
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


def _parse_periodo(value):
    periodo = str(value or "").strip().lower()
    if periodo not in PERIODOS_ACAO:
        raise ValueError("Informe o período da ação.")
    return periodo


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


def _parse_multi(value, opcoes, label):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",")]
    else:
        raw = value
    selecionados = []
    for item in raw or []:
        codigo = str(item or "").strip()
        if not codigo:
            continue
        if codigo not in opcoes:
            raise ValueError(f"{label} inválido.")
        if codigo not in selecionados:
            selecionados.append(codigo)
    return selecionados


def _multi_db(value):
    return json.dumps(value or [], ensure_ascii=False)


def _multi_from_db(value):
    if not value:
        return []
    try:
        dados = json.loads(value)
    except (TypeError, ValueError):
        dados = [item.strip() for item in str(value).split(",")]
    return [str(item) for item in dados if str(item or "").strip()]


def _labels(codigos, opcoes):
    return [opcoes.get(codigo, codigo) for codigo in codigos if codigo in opcoes or codigo]


def _acao_payload(dados):
    tipo = (dados.get("tipo") or "").strip()
    if tipo not in TIPOS_ACAO:
        raise ValueError("Tipo de ação inválido.")
    educativa = tipo == "educativa"
    payload = {
        "tipo": tipo,
        "data": _parse_data(dados.get("data")),
        "periodo": _parse_periodo(dados.get("periodo")),
        "hora_inicio": _parse_hora(dados.get("hora_inicio")),
        "hora_fim": _parse_hora(dados.get("hora_fim")),
        "localidade": (dados.get("localidade") or "").strip() or None,
        "endereco": (dados.get("endereco") or "").strip() or None,
        "local": (dados.get("local") or "").strip() or None,
        "publico_aproximado": _parse_publico(dados.get("publico_aproximado")),
        "tipo_atividade_realizada": (
            _parse_multi(dados.get("tipo_atividade_realizada"), TIPOS_ATIVIDADE_REALIZADA, "Tipo de atividade realizada")
            if educativa else []
        ),
        "publico_alvo": _parse_multi(dados.get("publico_alvo"), PUBLICOS_ALVO, "Público alvo") if educativa else [],
        "recurso_utilizado": _parse_multi(dados.get("recurso_utilizado"), RECURSOS_UTILIZADOS, "Recurso utilizado") if educativa else [],
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
    item["periodo_label"] = PERIODOS_ACAO.get(item.get("periodo") or "", item.get("periodo") or "")
    item["tipo_atividade_realizada"] = _multi_from_db(item.get("tipo_atividade_realizada"))
    item["publico_alvo"] = _multi_from_db(item.get("publico_alvo"))
    item["recurso_utilizado"] = _multi_from_db(item.get("recurso_utilizado"))
    item["tipo_atividade_realizada_labels"] = _labels(item["tipo_atividade_realizada"], TIPOS_ATIVIDADE_REALIZADA)
    item["publico_alvo_labels"] = _labels(item["publico_alvo"], PUBLICOS_ALVO)
    item["recurso_utilizado_labels"] = _labels(item["recurso_utilizado"], RECURSOS_UTILIZADOS)
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
    tipo_acao = item.get("acao_tipo")
    if tipo_acao:
        item["acao_tipo_label"] = TIPOS_ACAO.get(tipo_acao, tipo_acao)
    if item.get("acao_tema") or item.get("acao_local") or item.get("acao_localidade"):
        item["acao_titulo"] = item.get("acao_tema") or item.get("acao_local") or item.get("acao_localidade")
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


def _listar_anexos_galeria():
    params = []
    where = []
    tipo_acao = (request.args.get("tipo_acao") or "").strip()
    ano = (request.args.get("ano") or "").strip()
    tipo_arquivo = (request.args.get("tipo_arquivo") or "").strip()
    busca = (request.args.get("busca") or "").strip()
    if tipo_acao in TIPOS_ACAO:
        where.append("a.tipo=?")
        params.append(tipo_acao)
    if ano:
        where.append("substr(a.data, 1, 4)=?")
        params.append(ano[:4])
    if tipo_arquivo == "imagem":
        where.append("an.mime_type LIKE 'image/%'")
    elif tipo_arquivo == "pdf":
        where.append("an.mime_type='application/pdf'")
    elif tipo_arquivo == "documento":
        where.append("an.mime_type NOT LIKE 'image/%' AND an.mime_type<>'application/pdf'")
    sql = """
        SELECT an.*,
               a.data AS acao_data,
               a.tipo AS acao_tipo,
               a.localidade AS acao_localidade,
               a.local AS acao_local,
               a.tema AS acao_tema,
               a.observacoes AS acao_observacoes
          FROM acoes_setor_anexos an
          JOIN acoes_setor a ON a.id_acao=an.id_acao
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.data DESC, an.criado_em DESC, an.id_anexo DESC"
    anexos = [_anexo_dict(row) for row in bh.q(sql, params)]
    if busca:
        termos = [_normaliza_busca(t) for t in busca.split() if t.strip()]
        anexos = [
            item for item in anexos
            if all(
                termo in _normaliza_busca(" ".join(str(item.get(c) or "") for c in (
                    "nome_original", "mime_type", "acao_tipo_label", "acao_data",
                    "acao_localidade", "acao_local", "acao_tema", "acao_observacoes",
                )))
                for termo in termos
            )
        ]
    return anexos


def _zip_anexos(id_acao, rows):
    buffer = io.BytesIO()
    usados = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            caminho = _path_anexo(row["caminho_rel"])
            if not caminho.exists() or not caminho.is_file():
                continue
            nome = secure_filename(row["nome_original"] or row["nome_arquivo"] or caminho.name) or caminho.name
            base, ext = os.path.splitext(nome)
            candidato = nome
            idx = 2
            while candidato.casefold() in usados:
                candidato = f"{base}_{idx}{ext}"
                idx += 1
            usados.add(candidato.casefold())
            zf.write(caminho, candidato)
    if not usados:
        return None
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"acao_{str(id_acao).zfill(6)}_anexos.zip",
        max_age=0,
    )


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
        periodos_acao=PERIODOS_ACAO,
        tipos_atividade_realizada=TIPOS_ATIVIDADE_REALIZADA,
        publicos_alvo=PUBLICOS_ALVO,
        recursos_utilizados=RECURSOS_UTILIZADOS,
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
                   (tipo, data, periodo, hora_inicio, hora_fim, localidade, endereco, local,
                    publico_aproximado, tipo_atividade_realizada, publico_alvo, recurso_utilizado,
                    tema, contexto, coordenadas, observacoes,
                    criado_por, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["tipo"],
                    payload["data"],
                    payload["periodo"],
                    payload["hora_inicio"],
                    payload["hora_fim"],
                    payload["localidade"],
                    payload["endereco"],
                    payload["local"],
                    payload["publico_aproximado"],
                    _multi_db(payload["tipo_atividade_realizada"]),
                    _multi_db(payload["publico_alvo"]),
                    _multi_db(payload["recurso_utilizado"]),
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
                    "periodo_label", "tipo_atividade_realizada_labels",
                    "publico_alvo_labels", "recurso_utilizado_labels",
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
                  SET tipo=?, data=?, periodo=?, hora_inicio=?, hora_fim=?, localidade=?,
                      endereco=?, local=?, publico_aproximado=?,
                      tipo_atividade_realizada=?, publico_alvo=?, recurso_utilizado=?,
                      tema=?, contexto=?, coordenadas=?, observacoes=?, atualizado_em=?
                WHERE id_acao=?""",
            (
                payload["tipo"],
                payload["data"],
                payload["periodo"],
                payload["hora_inicio"],
                payload["hora_fim"],
                payload["localidade"],
                payload["endereco"],
                payload["local"],
                payload["publico_aproximado"],
                _multi_db(payload["tipo_atividade_realizada"]),
                _multi_db(payload["publico_alvo"]),
                _multi_db(payload["recurso_utilizado"]),
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


@bp.route("/api/acoes-setor/<int:id_acao>/anexos/baixar-todos")
@login_required
@nivel_min("operador")
def baixar_todos_anexos(id_acao):
    ensure_schema()
    acao = bh.q1("SELECT id_acao FROM acoes_setor WHERE id_acao=?", (id_acao,))
    if not acao:
        return jsonify({"erro": "Ação não encontrada."}), 404
    rows = bh.q(
        """SELECT * FROM acoes_setor_anexos
           WHERE id_acao=?
           ORDER BY criado_em DESC, id_anexo DESC""",
        (id_acao,),
    )
    resposta = _zip_anexos(id_acao, rows)
    if resposta is None:
        return jsonify({"erro": "Nenhum anexo disponível para download."}), 404
    return resposta


@bp.route("/api/acoes-setor/anexos")
@login_required
@nivel_min("operador")
def api_galeria_anexos():
    ensure_schema()
    anexos = _listar_anexos_galeria()
    return jsonify({"anexos": anexos, "total": len(anexos), "tipos_acao": TIPOS_ACAO})


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
