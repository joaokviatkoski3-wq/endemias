from collections import Counter, defaultdict
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
    "vistoria": "Vistoria / atendimento técnico",
    "reuniao": "Reunião / planejamento",
    "outro": "Outro",
}
PERIODOS_ACAO = {
    "manha": "Manhã",
    "tarde": "Tarde",
    "integral": "Dia inteiro",
    "nao_informado": "Não informado",
}
SITUACOES_ACAO = {
    "realizada": "Realizada",
    "em_acompanhamento": "Em acompanhamento",
    "planejada": "Planejada",
    "cancelada": "Cancelada",
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
ANEXO_EXTENSOES = {
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp",
}
ANEXO_VIDEO_EXTENSOES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp"}
ANEXO_MAX_BYTES = 200 * 1024 * 1024

ACOES_SETOR_COLUNAS = (
    "id_acao", "tipo", "situacao", "data", "data_fim", "periodo",
    "hora_inicio", "hora_fim", "caso", "localidade", "endereco", "local",
    "publico_aproximado", "tipo_atividade_realizada", "publico_alvo",
    "recurso_utilizado", "tema", "contexto", "resultados", "parceiros",
    "coordenadas", "observacoes", "criado_por", "criado_em", "atualizado_em",
)


def _acoes_setor_table_sql(nome="acoes_setor", if_not_exists=True):
    prefixo = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    tipos = ",".join(f"'{codigo}'" for codigo in TIPOS_ACAO)
    situacoes = ",".join(f"'{codigo}'" for codigo in SITUACOES_ACAO)
    return f"""
        {prefixo} {nome} (
            id_acao INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ({tipos})),
            situacao TEXT NOT NULL DEFAULT 'realizada'
                CHECK(situacao IN ({situacoes})),
            data TEXT NOT NULL,
            data_fim TEXT,
            periodo TEXT,
            hora_inicio TEXT,
            hora_fim TEXT,
            caso TEXT,
            localidade TEXT,
            endereco TEXT,
            local TEXT,
            publico_aproximado INTEGER,
            tipo_atividade_realizada TEXT,
            publico_alvo TEXT,
            recurso_utilizado TEXT,
            tema TEXT,
            contexto TEXT,
            resultados TEXT,
            parceiros TEXT,
            coordenadas TEXT,
            observacoes TEXT,
            criado_por TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT
        )
    """


def _migrar_tabela_acoes_setor(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='acoes_setor'"
    ).fetchone()
    if not row:
        conn.execute(_acoes_setor_table_sql())
        return

    sql_atual = (row["sql"] if hasattr(row, "keys") else row[0]) or ""
    colunas_atuais = _table_cols(conn, "acoes_setor")
    precisa_recriar = (
        "'vistoria'" not in sql_atual
        or "'reuniao'" not in sql_atual
        or "'outro'" not in sql_atual
        or "'em_acompanhamento'" not in sql_atual
    )
    if not precisa_recriar:
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE IF EXISTS acoes_setor_nova")
        conn.execute(_acoes_setor_table_sql("acoes_setor_nova", if_not_exists=False))
        comuns = [coluna for coluna in ACOES_SETOR_COLUNAS if coluna in colunas_atuais]
        colunas_sql = ", ".join(comuns)
        conn.execute(
            f"INSERT INTO acoes_setor_nova ({colunas_sql}) "
            f"SELECT {colunas_sql} FROM acoes_setor"
        )
        conn.execute("DROP TABLE acoes_setor")
        conn.execute("ALTER TABLE acoes_setor_nova RENAME TO acoes_setor")
        erros_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if erros_fk:
            raise RuntimeError(
                "A migração de ações e atendimentos deixaria vínculos inválidos."
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


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
        _migrar_tabela_acoes_setor(conn)
        conn.executescript("""
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
            restrito INTEGER NOT NULL DEFAULT 0 CHECK(restrito IN (0,1)),
            criado_por TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_data ON acoes_setor(data);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_tipo ON acoes_setor(tipo);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_situacao ON acoes_setor(situacao);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_caso ON acoes_setor(caso);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_localidade ON acoes_setor(localidade);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_agente ON acoes_setor_agentes(id_agente);
        CREATE INDEX IF NOT EXISTS idx_acoes_setor_anexo_acao ON acoes_setor_anexos(id_acao);
        """)
        cols = _table_cols(conn, "acoes_setor")
        colunas_texto = (
            "data_fim", "periodo", "caso", "tipo_atividade_realizada",
            "publico_alvo", "recurso_utilizado", "resultados", "parceiros",
        )
        for coluna in colunas_texto:
            if coluna not in cols:
                conn.execute(f"ALTER TABLE acoes_setor ADD COLUMN {coluna} TEXT")
        if "situacao" not in cols:
            conn.execute(
                "ALTER TABLE acoes_setor ADD COLUMN situacao TEXT "
                "NOT NULL DEFAULT 'realizada'"
            )
        anexos_cols = _table_cols(conn, "acoes_setor_anexos")
        if "restrito" not in anexos_cols:
            conn.execute(
                "ALTER TABLE acoes_setor_anexos ADD COLUMN restrito INTEGER "
                "NOT NULL DEFAULT 0 CHECK(restrito IN (0,1))"
            )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_acoes_setor_anexo_restrito
               ON acoes_setor_anexos(restrito, id_acao)"""
        )
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
        raise ValueError("Informe a data inicial do registro.")
    try:
        datetime.strptime(texto[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Data inválida.") from exc
    return texto[:10]


def _parse_data_fim(value, data_inicio):
    texto = str(value or "").strip()
    if not texto:
        return None
    data_fim = _parse_data(texto)
    if data_fim < data_inicio:
        raise ValueError("A data final não pode ser anterior à data inicial.")
    return data_fim


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
        raise ValueError("Informe o período do registro.")
    return periodo


def _parse_situacao(value):
    situacao = str(value or "realizada").strip().lower()
    if situacao not in SITUACOES_ACAO:
        raise ValueError("Situação do registro inválida.")
    return situacao


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


def _usuario_admin():
    usuario = bh.usuario_atual() or {}
    return usuario.get("nivel") == "admin"


def _restrito_form_value(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "sim"}


def _acao_payload(dados):
    tipo = (dados.get("tipo") or "").strip()
    if tipo not in TIPOS_ACAO:
        raise ValueError("Tipo de registro inválido.")
    educativa = tipo == "educativa"
    data_inicio = _parse_data(dados.get("data"))
    payload = {
        "tipo": tipo,
        "situacao": _parse_situacao(dados.get("situacao")),
        "data": data_inicio,
        "data_fim": _parse_data_fim(dados.get("data_fim"), data_inicio),
        "periodo": _parse_periodo(dados.get("periodo")),
        "hora_inicio": _parse_hora(dados.get("hora_inicio")),
        "hora_fim": _parse_hora(dados.get("hora_fim")),
        "caso": (dados.get("caso") or "").strip() or None,
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
        "resultados": (dados.get("resultados") or "").strip() or None,
        "parceiros": (dados.get("parceiros") or "").strip() or None,
        "coordenadas": (dados.get("coordenadas") or "").strip() or None,
        "observacoes": (dados.get("observacoes") or "").strip() or None,
        "agentes": _parse_agentes(dados.get("agentes")),
    }
    return payload


def _acao_dict(row):
    item = dict(row)
    item["tipo_label"] = TIPOS_ACAO.get(item.get("tipo"), item.get("tipo") or "")
    item["situacao_label"] = SITUACOES_ACAO.get(
        item.get("situacao") or "realizada",
        item.get("situacao") or "",
    )
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
    filtro_anexos = "" if _usuario_admin() else " AND COALESCE(ax.restrito,0)=0"
    return f"""
        SELECT a.*,
               (SELECT COUNT(*)
                  FROM acoes_setor_anexos ax
                 WHERE ax.id_acao=a.id_acao{filtro_anexos}) AS total_anexos,
               GROUP_CONCAT(ag.id_agente || ':' || ag.nome, '|') AS agentes_raw
          FROM acoes_setor a
          LEFT JOIN acoes_setor_agentes aa ON aa.id_acao = a.id_acao
          LEFT JOIN agentes ag ON ag.id_agente = aa.id_agente
    """


def _consultar_acoes(args):
    params = []
    where = []
    tipo = (args.get("tipo") or "").strip()
    situacao = (args.get("situacao") or "").strip()
    periodo = (args.get("periodo") or "").strip()
    localidade = (args.get("localidade") or "").strip()
    caso = (args.get("caso") or "").strip()
    id_agente = (args.get("id_agente") or "").strip()
    data_inicio = (args.get("data_inicio") or "").strip()[:10]
    data_fim = (args.get("data_fim") or "").strip()[:10]
    ano = (args.get("ano") or "").strip()
    busca = (args.get("busca") or "").strip()
    ordem = (args.get("ordem") or "recentes").strip()

    if tipo in TIPOS_ACAO:
        where.append("a.tipo=?")
        params.append(tipo)
    if situacao in SITUACOES_ACAO:
        where.append("a.situacao=?")
        params.append(situacao)
    if periodo in PERIODOS_ACAO:
        where.append("a.periodo=?")
        params.append(periodo)
    if localidade:
        where.append("a.localidade=?")
        params.append(localidade)
    if caso:
        where.append("a.caso=?")
        params.append(caso)
    if id_agente.isdigit():
        where.append(
            """EXISTS (
                SELECT 1 FROM acoes_setor_agentes af
                 WHERE af.id_acao=a.id_acao AND af.id_agente=?
            )"""
        )
        params.append(int(id_agente))
    if data_inicio:
        where.append("date(COALESCE(a.data_fim,a.data))>=date(?)")
        params.append(data_inicio)
    if data_fim:
        where.append("date(a.data)<=date(?)")
        params.append(data_fim)
    if ano:
        where.append("substr(a.data, 1, 4)=?")
        params.append(ano[:4])

    sql = _base_query()
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY a.id_acao"
    if ordem == "antigas":
        sql += " ORDER BY a.data, COALESCE(a.hora_inicio,''), a.id_acao"
    elif ordem == "localidade":
        sql += " ORDER BY COALESCE(a.localidade,''), a.data DESC, a.id_acao DESC"
    elif ordem == "tipo":
        sql += " ORDER BY a.tipo, a.data DESC, a.id_acao DESC"
    elif ordem == "publico":
        sql += " ORDER BY COALESCE(a.publico_aproximado,0) DESC, a.data DESC"
    else:
        sql += " ORDER BY a.data DESC, COALESCE(a.hora_inicio,'') DESC, a.id_acao DESC"

    registros = [_acao_dict(row) for row in bh.q(sql, params)]
    if busca:
        termos = [_normaliza_busca(t) for t in busca.split() if t.strip()]
        registros = [
            registro for registro in registros
            if all(
                termo in _normaliza_busca(
                    " ".join(str(registro.get(campo) or "") for campo in (
                        "tipo_label", "data", "localidade", "endereco", "local",
                        "tema", "caso", "contexto", "resultados", "parceiros",
                        "coordenadas", "observacoes", "agentes_nomes",
                        "situacao_label", "periodo_label",
                        "tipo_atividade_realizada_labels",
                        "publico_alvo_labels", "recurso_utilizado_labels",
                    ))
                )
                for termo in termos
            )
        ]
    return registros


def _data_br(valor):
    try:
        return datetime.strptime(str(valor or "")[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(valor or "")


def _anexos_relatorio(ids_acoes):
    ids = sorted({int(item) for item in ids_acoes if int(item) > 0})
    agrupados = defaultdict(list)
    if not ids:
        return agrupados
    admin = _usuario_admin()
    placeholders = ",".join("?" for _ in ids)
    restricao = "" if admin else " AND COALESCE(restrito,0)=0"
    rows = bh.q(
        f"""SELECT *
              FROM acoes_setor_anexos
             WHERE id_acao IN ({placeholders}){restricao}
             ORDER BY id_acao, criado_em, id_anexo""",
        ids,
    )
    base = _anexos_base_dir()
    for row in rows:
        item = _anexo_dict(row, admin)
        caminho = (base / item["caminho_rel"]).resolve()
        if (base not in caminho.parents and caminho != base) or not caminho.is_file():
            continue
        item["eh_imagem"] = (item.get("mime_type") or "").startswith("image/")
        agrupados[int(item["id_acao"])].append(item)
    return agrupados


def _resumo_relatorio(registros):
    por_tipo = Counter(item.get("tipo") or "outro" for item in registros)
    publico_tipo = Counter()
    por_situacao = Counter(item.get("situacao") or "realizada" for item in registros)
    por_localidade = Counter(item.get("localidade") or "Não informada" for item in registros)
    localidades_informadas = {
        item["localidade"] for item in registros if item.get("localidade")
    }
    por_mes = Counter()
    servidores = set()
    for item in registros:
        publico_tipo[item.get("tipo") or "outro"] += int(item.get("publico_aproximado") or 0)
        data = str(item.get("data") or "")
        if len(data) >= 7:
            por_mes[f"{data[5:7]}/{data[:4]}"] += 1
        servidores.update(agente["nome"] for agente in item.get("agentes") or [])
    return {
        "total": len(registros),
        "publico": sum(int(item.get("publico_aproximado") or 0) for item in registros),
        "anexos": sum(len(item.get("anexos_relatorio") or []) for item in registros),
        "imagens": sum(len(item.get("imagens_relatorio") or []) for item in registros),
        "localidades": len(localidades_informadas),
        "servidores": len(servidores),
        "por_tipo": [
            {
                "codigo": codigo,
                "label": TIPOS_ACAO[codigo],
                "total": por_tipo[codigo],
                "publico": publico_tipo[codigo],
            }
            for codigo in TIPOS_ACAO if por_tipo[codigo]
        ],
        "por_situacao": [
            {"label": SITUACOES_ACAO[codigo], "total": por_situacao[codigo]}
            for codigo in SITUACOES_ACAO if por_situacao[codigo]
        ],
        "por_localidade": [
            {"label": label, "total": total}
            for label, total in sorted(
                por_localidade.items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )
        ],
        "por_mes": [
            {"label": label, "total": total}
            for label, total in sorted(
                por_mes.items(),
                key=lambda item: (item[0][3:], item[0][:2]),
            )
        ],
    }


def _filtros_relatorio(args):
    itens = []
    mapas = (
        ("tipo", "Tipo", TIPOS_ACAO),
        ("situacao", "Situação", SITUACOES_ACAO),
        ("periodo", "Período", PERIODOS_ACAO),
    )
    for campo, label, opcoes in mapas:
        valor = (args.get(campo) or "").strip()
        if valor in opcoes:
            itens.append(f"{label}: {opcoes[valor]}")
    campos_texto = (
        ("localidade", "Localidade"),
        ("caso", "Caso / acompanhamento"),
        ("busca", "Pesquisa"),
    )
    for campo, label in campos_texto:
        valor = (args.get(campo) or "").strip()
        if valor:
            itens.append(f"{label}: {valor}")
    data_inicio = (args.get("data_inicio") or "").strip()[:10]
    data_fim = (args.get("data_fim") or "").strip()[:10]
    if data_inicio:
        itens.append(f"Data inicial: {_data_br(data_inicio)}")
    if data_fim:
        itens.append(f"Data final: {_data_br(data_fim)}")
    id_agente = (args.get("id_agente") or "").strip()
    if id_agente.isdigit():
        agente = bh.q1("SELECT nome FROM agentes WHERE id_agente=?", (int(id_agente),))
        if agente:
            itens.append(f"Servidor: {agente['nome']}")
    return itens or ["Todos os registros"]


def _salvar_agentes(conn, id_acao, agentes):
    conn.execute("DELETE FROM acoes_setor_agentes WHERE id_acao=?", (id_acao,))
    for id_agente in agentes:
        conn.execute(
            "INSERT OR IGNORE INTO acoes_setor_agentes (id_acao, id_agente) VALUES (?, ?)",
            (id_acao, id_agente),
        )


def _criar_acao(conn, payload, usuario_nome):
    agora = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT INTO acoes_setor
           (tipo, situacao, data, data_fim, periodo, hora_inicio, hora_fim,
            caso, localidade, endereco, local,
            publico_aproximado, tipo_atividade_realizada, publico_alvo, recurso_utilizado,
            tema, contexto, resultados, parceiros, coordenadas, observacoes,
            criado_por, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload["tipo"],
            payload["situacao"],
            payload["data"],
            payload["data_fim"],
            payload["periodo"],
            payload["hora_inicio"],
            payload["hora_fim"],
            payload["caso"],
            payload["localidade"],
            payload["endereco"],
            payload["local"],
            payload["publico_aproximado"],
            _multi_db(payload["tipo_atividade_realizada"]),
            _multi_db(payload["publico_alvo"]),
            _multi_db(payload["recurso_utilizado"]),
            payload["tema"],
            payload["contexto"],
            payload["resultados"],
            payload["parceiros"],
            payload["coordenadas"],
            payload["observacoes"],
            usuario_nome,
            agora,
            agora,
        ),
    )
    id_acao = cur.lastrowid
    _salvar_agentes(conn, id_acao, payload["agentes"])
    return id_acao


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


def _anexo_dict(row, pode_gerenciar_restritos=None):
    item = dict(row)
    item["restrito"] = bool(item.get("restrito"))
    if pode_gerenciar_restritos is None:
        pode_gerenciar_restritos = _usuario_admin()
    item["pode_gerenciar_restritos"] = pode_gerenciar_restritos
    item["url_download"] = f"/acoes-setor/anexos/{item['id_anexo']}/download"
    item["url_visualizar"] = f"/acoes-setor/anexos/{item['id_anexo']}/download?inline=1"
    mime_type = item.get("mime_type") or ""
    item["eh_previa"] = mime_type.startswith("image/") or mime_type.startswith("video/") or mime_type == "application/pdf"
    tipo_acao = item.get("acao_tipo")
    if tipo_acao:
        item["acao_tipo_label"] = TIPOS_ACAO.get(tipo_acao, tipo_acao)
    if item.get("acao_periodo"):
        item["acao_periodo_label"] = PERIODOS_ACAO.get(
            item["acao_periodo"], item["acao_periodo"]
        )
    if (
        item.get("acao_tema")
        or item.get("acao_caso")
        or item.get("acao_local")
        or item.get("acao_localidade")
    ):
        item["acao_titulo"] = (
            item.get("acao_tema")
            or item.get("acao_caso")
            or item.get("acao_local")
            or item.get("acao_localidade")
        )
    return item


def _listar_anexos(id_acao):
    admin = _usuario_admin()
    restricao = "" if admin else " AND COALESCE(restrito,0)=0"
    return [
        _anexo_dict(row, admin) for row in bh.q(
            f"""SELECT * FROM acoes_setor_anexos
                WHERE id_acao=?{restricao}
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
    localidade = (request.args.get("localidade") or "").strip()
    caso = (request.args.get("caso") or "").strip()
    id_agente = (request.args.get("id_agente") or "").strip()
    data_inicio = (request.args.get("data_inicio") or "").strip()[:10]
    data_fim = (request.args.get("data_fim") or "").strip()[:10]
    busca = (request.args.get("busca") or "").strip()
    admin = _usuario_admin()
    if not admin:
        where.append("COALESCE(an.restrito,0)=0")
    if tipo_acao in TIPOS_ACAO:
        where.append("a.tipo=?")
        params.append(tipo_acao)
    if ano:
        where.append("substr(a.data, 1, 4)=?")
        params.append(ano[:4])
    if localidade:
        where.append("a.localidade=?")
        params.append(localidade)
    if caso:
        where.append("a.caso=?")
        params.append(caso)
    if id_agente.isdigit():
        where.append(
            """EXISTS (
                SELECT 1 FROM acoes_setor_agentes af
                 WHERE af.id_acao=a.id_acao AND af.id_agente=?
            )"""
        )
        params.append(int(id_agente))
    if data_inicio:
        where.append("date(COALESCE(a.data_fim,a.data))>=date(?)")
        params.append(data_inicio)
    if data_fim:
        where.append("date(a.data)<=date(?)")
        params.append(data_fim)
    if tipo_arquivo == "imagem":
        where.append("an.mime_type LIKE 'image/%'")
    elif tipo_arquivo == "video":
        video_like = " OR ".join(["lower(an.nome_original) LIKE ?"] * len(ANEXO_VIDEO_EXTENSOES))
        where.append(f"(an.mime_type LIKE 'video/%' OR {video_like})")
        params.extend([f"%{ext}" for ext in sorted(ANEXO_VIDEO_EXTENSOES)])
    elif tipo_arquivo == "pdf":
        where.append("an.mime_type='application/pdf'")
    elif tipo_arquivo == "documento":
        where.append("an.mime_type NOT LIKE 'image/%' AND an.mime_type NOT LIKE 'video/%' AND an.mime_type<>'application/pdf'")
    sql = """
        SELECT an.*,
               a.data AS acao_data,
               a.tipo AS acao_tipo,
               a.localidade AS acao_localidade,
               a.local AS acao_local,
               a.tema AS acao_tema,
               a.caso AS acao_caso,
               a.observacoes AS acao_observacoes,
               a.periodo AS acao_periodo
          FROM acoes_setor_anexos an
          JOIN acoes_setor a ON a.id_acao=an.id_acao
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.data DESC, an.criado_em DESC, an.id_anexo DESC"
    anexos = [_anexo_dict(row, admin) for row in bh.q(sql, params)]
    if busca:
        termos = [_normaliza_busca(t) for t in busca.split() if t.strip()]
        anexos = [
            item for item in anexos
            if all(
                termo in _normaliza_busca(" ".join(str(item.get(c) or "") for c in (
                    "nome_original", "mime_type", "acao_tipo_label", "acao_data",
                    "acao_localidade", "acao_local", "acao_tema", "acao_caso",
                    "acao_observacoes",
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
        return None, "Arquivo maior que 200 MB."
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
    casos = bh.q(
        """SELECT DISTINCT caso
             FROM acoes_setor
            WHERE caso IS NOT NULL AND TRIM(caso)<>''
            ORDER BY caso"""
    )
    return render_template(
        "acoes_setor.html",
        tipos_acao=TIPOS_ACAO,
        periodos_acao=PERIODOS_ACAO,
        situacoes_acao=SITUACOES_ACAO,
        tipos_atividade_realizada=TIPOS_ATIVIDADE_REALIZADA,
        publicos_alvo=PUBLICOS_ALVO,
        recursos_utilizados=RECURSOS_UTILIZADOS,
        agentes=agentes,
        localidades=[row["nome"] for row in localidades],
        casos=[row["caso"] for row in casos],
        pode_gerenciar_restritos=_usuario_admin(),
    )


@bp.route("/acoes-setor/relatorio/pdf")
@login_required
@nivel_min("operador")
def relatorio_pdf():
    ensure_schema()
    registros = _consultar_acoes(request.args)
    anexos_por_acao = _anexos_relatorio(
        item["id_acao"] for item in registros
    )
    incluir_imagens = str(request.args.get("imagens", "1")).strip().lower() not in {
        "0", "false", "nao", "não",
    }
    for item in registros:
        anexos = anexos_por_acao.get(int(item["id_acao"]), [])
        item["anexos_relatorio"] = anexos
        item["imagens_relatorio"] = (
            [anexo for anexo in anexos if anexo["eh_imagem"]]
            if incluir_imagens else []
        )
        item["documentos_relatorio"] = [
            anexo for anexo in anexos if not anexo["eh_imagem"]
        ]

    datas_inicio = [item["data"] for item in registros if item.get("data")]
    datas_fim = [
        item.get("data_fim") or item.get("data")
        for item in registros if item.get("data_fim") or item.get("data")
    ]
    data_inicio = (
        (request.args.get("data_inicio") or "").strip()[:10]
        or (min(datas_inicio) if datas_inicio else "")
    )
    data_fim = (
        (request.args.get("data_fim") or "").strip()[:10]
        or (max(datas_fim) if datas_fim else "")
    )
    periodo_label = (
        f"{_data_br(data_inicio)} a {_data_br(data_fim)}"
        if data_inicio and data_fim
        else "Período não delimitado"
    )
    ordem = (request.args.get("ordem") or "recentes").strip()
    ordem_label = {
        "recentes": "Mais recentes primeiro",
        "antigas": "Mais antigas primeiro",
        "localidade": "Localidade",
        "tipo": "Tipo de registro",
        "publico": "Maior público",
    }.get(ordem, "Mais recentes primeiro")
    usuario = bh.usuario_atual() or {}
    return render_template(
        "acoes_setor_relatorio.html",
        registros=registros,
        resumo=_resumo_relatorio(registros),
        filtros=_filtros_relatorio(request.args),
        periodo_label=periodo_label,
        ordem_label=ordem_label,
        incluir_imagens=incluir_imagens,
        gerado_por=usuario.get("nome") or "Sistema",
        gerado_em=datetime.now().strftime("%d/%m/%Y às %H:%M"),
        data_br=_data_br,
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
            id_acao = _criar_acao(
                conn,
                payload,
                usuario.get("nome") or "sistema",
            )
            conn.commit()
        except sqlite3.OperationalError:
            if conn:
                conn.rollback()
            return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
        finally:
            if conn:
                conn.close()
        return jsonify({"ok": True, "id_acao": id_acao}), 201

    registros = _consultar_acoes(request.args)
    return jsonify({"registros": registros, "total": len(registros), "tipos": TIPOS_ACAO})


@bp.route("/api/acoes-setor/<int:id_acao>", methods=["GET", "PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_acao(id_acao):
    ensure_schema()
    if request.method == "GET":
        row = bh.q1(_base_query() + " WHERE a.id_acao=? GROUP BY a.id_acao", (id_acao,))
        if not row:
            return jsonify({"erro": "Registro não encontrado."}), 404
        return jsonify(_acao_dict(row))

    conn = None
    try:
        conn = bh.get_db()
        existe = conn.execute(
            "SELECT 1 FROM acoes_setor WHERE id_acao=?",
            (id_acao,),
        ).fetchone()
        if not existe:
            return jsonify({"erro": "Registro não encontrado."}), 404
        if request.method == "DELETE":
            if not _usuario_admin():
                tem_restrito = conn.execute(
                    """SELECT 1 FROM acoes_setor_anexos
                        WHERE id_acao=? AND COALESCE(restrito,0)=1
                        LIMIT 1""",
                    (id_acao,),
                ).fetchone()
                if tem_restrito:
                    return jsonify({
                        "erro": "Este registro possui anexos restritos e só pode ser excluído pela administração."
                    }), 403
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
                  SET tipo=?, situacao=?, data=?, data_fim=?, periodo=?,
                      hora_inicio=?, hora_fim=?, caso=?, localidade=?,
                      endereco=?, local=?, publico_aproximado=?,
                      tipo_atividade_realizada=?, publico_alvo=?, recurso_utilizado=?,
                      tema=?, contexto=?, resultados=?, parceiros=?, coordenadas=?,
                      observacoes=?, atualizado_em=?
                WHERE id_acao=?""",
            (
                payload["tipo"],
                payload["situacao"],
                payload["data"],
                payload["data_fim"],
                payload["periodo"],
                payload["hora_inicio"],
                payload["hora_fim"],
                payload["caso"],
                payload["localidade"],
                payload["endereco"],
                payload["local"],
                payload["publico_aproximado"],
                _multi_db(payload["tipo_atividade_realizada"]),
                _multi_db(payload["publico_alvo"]),
                _multi_db(payload["recurso_utilizado"]),
                payload["tema"],
                payload["contexto"],
                payload["resultados"],
                payload["parceiros"],
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
        return jsonify({"erro": "Registro não encontrado."}), 404
    if request.method == "GET":
        return jsonify({"anexos": _listar_anexos(id_acao)})

    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    restrito = _restrito_form_value(request.form.get("restrito"))
    if restrito and not _usuario_admin():
        return jsonify({"erro": "Somente administradores podem adicionar anexos restritos."}), 403
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
                    tamanho, restrito, criado_por, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id_acao,
                    meta["nome_original"],
                    nome_arquivo,
                    caminho_rel,
                    mime_type,
                    meta["tamanho"],
                    1 if restrito else 0,
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
        return jsonify({"erro": "Registro não encontrado."}), 404
    restricao = "" if _usuario_admin() else " AND COALESCE(restrito,0)=0"
    rows = bh.q(
        f"""SELECT * FROM acoes_setor_anexos
            WHERE id_acao=?{restricao}
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


@bp.route("/api/acoes-setor/anexos/<int:id_anexo>", methods=["PUT", "DELETE"])
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
        if row["restrito"] and not _usuario_admin():
            return jsonify({"erro": "Anexo restrito à administração."}), 403
        if request.method == "PUT":
            if not _usuario_admin():
                return jsonify({"erro": "Somente administradores podem alterar a restrição."}), 403
            restrito = bool((request.get_json(silent=True) or {}).get("restrito"))
            conn.execute(
                "UPDATE acoes_setor_anexos SET restrito=? WHERE id_anexo=?",
                (1 if restrito else 0, id_anexo),
            )
            conn.commit()
            atualizado = conn.execute(
                "SELECT * FROM acoes_setor_anexos WHERE id_anexo=?",
                (id_anexo,),
            ).fetchone()
            return jsonify({"ok": True, "anexo": _anexo_dict(atualizado)})
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
    if row["restrito"] and not _usuario_admin():
        abort(403)
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
