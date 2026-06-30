import hashlib
import re
import unicodedata
from datetime import datetime

import pandas as pd

from app_core import agentes as agentes_db
from app_core import db as db_core
from app_core import normalizadores


VISITAS_TABLE = "esporotricose_visitas"
ANIMAIS_TABLE = "esporotricose_animais"
VISITA_AGENTES_TABLE = "esporotricose_visita_agentes"
DOENTES_TABLE = "esporotricose_doentes_animais"
DOENTES_RECEITAS_TABLE = "esporotricose_doentes_receitas"
DOENTES_ENTREGAS_TABLE = "esporotricose_doentes_entregas"
DOENTES_ANEXOS_TABLE = "esporotricose_doentes_anexos"
DOENTES_STATUS_TABLE = "esporotricose_doentes_status"
NORMAL_IMPORT_MARKER = "esporotricose_kobo_v2"
LEGACY_IMPORT_MARKER = "esporotricose_historico_legado"
MOTIVO_ATENCAO_SQL = """CASE
    WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 'Ferida informada'
    WHEN a.feridas IS NULL OR LOWER(COALESCE(a.feridas,'')) = 'desconhecido' THEN 'Feridas sem confirma\u00e7\u00e3o'
    WHEN a.vacinado IS NULL OR LOWER(COALESCE(a.vacinado,'')) = 'desconhecido' THEN 'Vacina sem confirma\u00e7\u00e3o'
    WHEN a.castrado IS NULL OR LOWER(COALESCE(a.castrado,'')) = 'desconhecido' THEN 'Castra\u00e7\u00e3o sem confirma\u00e7\u00e3o'
    WHEN a.ambiente IS NULL OR TRIM(COALESCE(a.ambiente,'')) = '' THEN 'Ambiente n\u00e3o informado'
    ELSE ''
END"""

AGENTE_COMPOSTO = {
    "ana beatriz": "Ana Beatriz",
}

AGENTE_ALIASES = {
    "ana_beatriz": "Ana Beatriz",
    "cecon": "Ceccon",
    "ceccon": "Ceccon",
    "marcio": "Márcio",
    "m_rcio": "Márcio",
    "m_arcio": "Márcio",
}

LOCALIDADES_PADRAO = {
    "sao venancio": "Sao Venancio",
    "são venâncio": "São Venâncio",
    "sao venâncio": "São Venâncio",
    "são venancio": "São Venâncio",
    "grasiela": "Graziela",
    "graziela": "Graziela",
    "tangua": "Tanguá",
    "tanguá": "Tanguá",
}

CHOICE_LABELS = {
    "c_o": "Cão",
    "cao": "Cão",
    "cão": "Cão",
    "gato": "Gato",
    "outro": "Outro",
    "outros": "Outros",
    "macho": "Macho",
    "f_mea": "Fêmea",
    "femea": "Fêmea",
    "fêmea": "Fêmea",
    "domiciliado": "Domiciliado",
    "semi_domiciliado": "Semi-domiciliado",
    "semidomiciliado": "Semi-domiciliado",
    "de_rua": "De rua",
    "derua": "De rua",
    "comunit_rio": "Comunitário",
    "comunitario": "Comunitário",
    "comunitário": "Comunitário",
    "sim": "Sim",
    "n_o": "Não",
    "nao": "Não",
    "não": "Não",
    "desconhecido": "Desconhecido",
    "resid_ncia": "Residência",
    "residencia": "Residência",
    "residência": "Residência",
    "com_rcio": "Comércio",
    "comercio": "Comércio",
    "comércio": "Comércio",
    "terreno_baldio": "Terreno Baldio",
    "terrenobaldio": "Terreno Baldio",
    "normal": "Normal",
    "fechado": "Fechado",
    "recusa": "Recusa",
    "recuperado": "Recuperado",
}

DOENTES_STATUS_PADRAO = (
    "Em tratamento",
    "Aguardando documentos",
    "Aguardando medicação",
    "Medicação disponível",
    "Acabou tratamento",
    "Faleceu",
    "Outro",
)


class ValidationError(Exception):
    pass


DOENTES_STATUS_PADRAO = (
    "Em tratamento",
    "Aguardando documentos",
    "Aguardando medicação",
    "Medicação disponível",
    "Acabou tratamento",
    "Faleceu",
    "Não é esporotricose",
    "Outro",
)

BLOQUEIO_DOENTE_OPCOES = (
    "Realizado",
    "Não realizado",
    "Não necessário",
)


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS esporotricose_visitas (
            id_visita       TEXT PRIMARY KEY,
            kobo_uuid       TEXT NOT NULL UNIQUE,
            kobo_id         INTEGER,
            data            DATE NOT NULL,
            hora_inicio     TIME,
            hora_fim        TIME,
            inicio_registro TEXT,
            fim_registro    TEXT,
            agentes_texto   TEXT,
            localidade      TEXT,
            id_localidade   INTEGER REFERENCES localidades(id_localidade),
            quarteirao      INTEGER,
            tipo_imovel     TEXT,
            logradouro      TEXT,
            numero          TEXT,
            morador         TEXT,
            visita          TEXT,
            telefone        TEXT,
            observacoes     TEXT,
            deseja_cadastrar_animal TEXT,
            origem_estrutura TEXT NOT NULL DEFAULT 'nova',
            arquivo_origem  TEXT,
            submission_time TEXT,
            processado_em   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_visita_agentes (
            id_visita TEXT NOT NULL REFERENCES esporotricose_visitas(id_visita) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_visita, id_agente)
        );

        CREATE TABLE IF NOT EXISTS esporotricose_animais (
            id_animal       TEXT PRIMARY KEY,
            id_visita       TEXT NOT NULL REFERENCES esporotricose_visitas(id_visita) ON DELETE CASCADE,
            kobo_uuid       TEXT,
            especie         TEXT,
            outro_animal    TEXT,
            nome            TEXT,
            raca            TEXT,
            sexo            TEXT,
            ambiente        TEXT,
            vacinado        TEXT,
            castrado        TEXT,
            feridas         TEXT,
            regiao_ferida   TEXT,
            atendimento_veterinario TEXT,
            data_atendimento DATE,
            evolucao_caso   TEXT,
            arquivo_origem  TEXT,
            processado_em   TEXT NOT NULL,
            UNIQUE(id_visita, kobo_uuid)
        );

        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_data ON esporotricose_visitas(data);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_localidade ON esporotricose_visitas(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_quarteirao ON esporotricose_visitas(quarteirao);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_kobo_uuid ON esporotricose_visitas(kobo_uuid);
        CREATE INDEX IF NOT EXISTS idx_esporo_animais_visita ON esporotricose_animais(id_visita);
        CREATE INDEX IF NOT EXISTS idx_esporo_animais_especie ON esporotricose_animais(especie);

        CREATE TABLE IF NOT EXISTS esporotricose_doentes_status (
            id_status INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_doentes_animais (
            id_animal_doente INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT NOT NULL UNIQUE,
            tutor TEXT,
            nome TEXT NOT NULL,
            especie TEXT,
            sexo TEXT,
            telefone TEXT,
            localidade TEXT,
            quarteirao TEXT,
            endereco TEXT,
            latitude REAL,
            longitude REAL,
            sinan TEXT,
            status TEXT,
            bloqueio TEXT,
            data_bloqueio DATE,
            observacoes_entomologica TEXT,
            pedido_zoomed TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_doentes_receitas (
            id_receita INTEGER PRIMARY KEY AUTOINCREMENT,
            id_animal_doente INTEGER NOT NULL REFERENCES esporotricose_doentes_animais(id_animal_doente) ON DELETE CASCADE,
            data_notificacao DATE,
            inicio_sintomas DATE,
            data_receita DATE,
            visita_va_veterinario DATE,
            capsulas_total INTEGER,
            posologia TEXT,
            status TEXT,
            observacoes TEXT,
            origem_linha INTEGER,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_doentes_entregas (
            id_entrega INTEGER PRIMARY KEY AUTOINCREMENT,
            id_receita INTEGER NOT NULL REFERENCES esporotricose_doentes_receitas(id_receita) ON DELETE CASCADE,
            quantidade INTEGER NOT NULL,
            data_entrega DATE,
            baixa_zoomed TEXT NOT NULL DEFAULT 'Não',
            observacoes TEXT,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_doentes_anexos (
            id_anexo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_animal_doente INTEGER NOT NULL REFERENCES esporotricose_doentes_animais(id_animal_doente) ON DELETE CASCADE,
            id_receita INTEGER REFERENCES esporotricose_doentes_receitas(id_receita) ON DELETE SET NULL,
            nome_original TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            caminho_rel TEXT NOT NULL,
            mime_type TEXT,
            tamanho INTEGER NOT NULL,
            criado_por TEXT,
            criado_em TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_esporo_doentes_status ON esporotricose_doentes_animais(status);
        CREATE INDEX IF NOT EXISTS idx_esporo_doentes_localidade ON esporotricose_doentes_animais(localidade);
        CREATE INDEX IF NOT EXISTS idx_esporo_doentes_receitas_animal ON esporotricose_doentes_receitas(id_animal_doente);
        CREATE INDEX IF NOT EXISTS idx_esporo_doentes_entregas_receita ON esporotricose_doentes_entregas(id_receita);
        CREATE INDEX IF NOT EXISTS idx_esporo_doentes_anexos_animal ON esporotricose_doentes_anexos(id_animal_doente);
        """
    )
    _ensure_column(conn, DOENTES_TABLE, "especie", "TEXT")
    _ensure_column(conn, DOENTES_ENTREGAS_TABLE, "baixa_zoomed", "TEXT NOT NULL DEFAULT 'Sim'")
    _seed_doentes_status(conn)
    _normalizar_doentes_existentes(conn)
    _normalizar_agentes_existentes(conn)
    conn.commit()


def _ensure_column(conn, table, column, definition):
    cols = {_db_value(row, "name", 1) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_doentes_status(conn):
    agora = datetime.now().isoformat(timespec="seconds")
    conn.execute(f"UPDATE {DOENTES_STATUS_TABLE} SET ativo=0")
    for nome in DOENTES_STATUS_PADRAO:
        conn.execute(
            f"""INSERT INTO {DOENTES_STATUS_TABLE}(nome, ativo, criado_em)
                VALUES (?,1,?)
                ON CONFLICT(nome) DO UPDATE SET ativo=1""",
            (nome, agora),
        )


def _normalizar_doentes_existentes(conn):
    for tabela, id_col in ((DOENTES_TABLE, "id_animal_doente"), (DOENTES_RECEITAS_TABLE, "id_receita")):
        rows = conn.execute(f"SELECT {id_col}, status FROM {tabela}").fetchall()
        for row in rows:
            status = _normalizar_status_doente(row["status"])
            if status != (row["status"] or ""):
                conn.execute(f"UPDATE {tabela} SET status=? WHERE {id_col}=?", (status, row[id_col]))

    rows = conn.execute(f"SELECT id_animal_doente, pedido_zoomed FROM {DOENTES_TABLE}").fetchall()
    for row in rows:
        zoomed = _normalizar_sim_nao(row["pedido_zoomed"])
        if zoomed != (row["pedido_zoomed"] or ""):
            conn.execute(
                f"UPDATE {DOENTES_TABLE} SET pedido_zoomed=? WHERE id_animal_doente=?",
                (zoomed, row["id_animal_doente"]),
            )

    rows = conn.execute(f"SELECT id_animal_doente, bloqueio FROM {DOENTES_TABLE}").fetchall()
    for row in rows:
        bloqueio = _normalizar_bloqueio_doente(row["bloqueio"])
        if bloqueio != (row["bloqueio"] or ""):
            conn.execute(
                f"UPDATE {DOENTES_TABLE} SET bloqueio=? WHERE id_animal_doente=?",
                (bloqueio, row["id_animal_doente"]),
            )

    rows = conn.execute(f"SELECT id_entrega, baixa_zoomed FROM {DOENTES_ENTREGAS_TABLE}").fetchall()
    for row in rows:
        baixa = _normalizar_sim_nao(row["baixa_zoomed"]) or "Sim"
        if baixa != (row["baixa_zoomed"] or ""):
            conn.execute(
                f"UPDATE {DOENTES_ENTREGAS_TABLE} SET baixa_zoomed=? WHERE id_entrega=?",
                (baixa, row["id_entrega"]),
            )


def _normalizar_agentes_existentes(conn):
    if not _table_exists(conn, "agentes"):
        return
    for alias, correto in AGENTE_ALIASES.items():
        if _table_exists(conn, VISITAS_TABLE):
            conn.execute(
                f"UPDATE {VISITAS_TABLE} SET agentes_texto=REPLACE(agentes_texto, ?, ?) WHERE agentes_texto LIKE ?",
                (alias, correto, f"%{alias}%"),
            )
    for alias, correto in AGENTE_ALIASES.items():
        alias_norm = _norm_col(alias)
        rows = conn.execute("SELECT id_agente, nome FROM agentes").fetchall()
        aliases = [row for row in rows if _norm_col(_db_value(row, "nome", 1)) == alias_norm and _db_value(row, "nome", 1) != correto]
        if not aliases:
            continue
        destino = conn.execute("SELECT id_agente FROM agentes WHERE nome=?", (correto,)).fetchone()
        if destino:
            id_destino = _db_value(destino, "id_agente", 0)
        else:
            primeiro = aliases[0]
            id_destino = _db_value(primeiro, "id_agente", 0)
            conn.execute("UPDATE agentes SET nome=? WHERE id_agente=?", (correto, id_destino))
            aliases = aliases[1:]
        for row in aliases:
            id_origem = _db_value(row, "id_agente", 0)
            _migrar_vinculos_agente(conn, id_origem, id_destino)
            conn.execute("DELETE FROM agentes WHERE id_agente=?", (id_origem,))


def _migrar_vinculos_agente(conn, id_origem, id_destino):
    tabelas = (
        ("visita_agentes", "id_visita"),
        ("esporotricose_visita_agentes", "id_visita"),
        ("recolhimento_agentes", "id_recolhimento"),
        ("amostra_animais_agentes", "id_amostra"),
        ("bri_agentes", "id_bri"),
        ("acoes_setor_agentes", "id_acao"),
        ("ovitrampas_calendario_agentes", "id_evento"),
        ("registro_geografico_imovel_agentes", "id_imovel"),
    )
    for tabela, chave in tabelas:
        if not _table_exists(conn, tabela):
            continue
        rows = conn.execute(
            f"SELECT {chave} FROM {tabela} WHERE id_agente=?",
            (id_origem,),
        ).fetchall()
        for row in rows:
            valor_chave = _db_value(row, chave, 0)
            conn.execute(
                f"INSERT OR IGNORE INTO {tabela}({chave}, id_agente) VALUES (?, ?)",
                (valor_chave, id_destino),
            )
        conn.execute(f"DELETE FROM {tabela} WHERE id_agente=?", (id_origem,))


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _db_value(row, key, index):
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _norm_col(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _has_col(columns, candidates):
    col_norms = [_norm_col(col) for col in columns]
    for candidate in candidates:
        wanted = _norm_col(candidate)
        if any(col == wanted or col.endswith(wanted) for col in col_norms):
            return True
    return False


def _row_get(row, candidates):
    for candidate in candidates:
        if candidate in row.index:
            value = row.get(candidate)
            if not _is_empty(value):
                return value
    indexed = [(_norm_col(col), col) for col in row.index]
    for candidate in candidates:
        wanted = _norm_col(candidate)
        for col_norm, col in indexed:
            if col_norm == wanted or col_norm.endswith(wanted):
                value = row.get(col)
                if not _is_empty(value):
                    return value
    return None


def _is_empty(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def is_new_format(path):
    df = pd.read_excel(path, sheet_name=0, nrows=1, engine="openpyxl")
    return (
        _has_col(df.columns, ["start"])
        and _has_col(df.columns, ["end"])
        and _has_col(df.columns, ["Dados do morador/Hora Inicio", "Hora_inicio"])
        and _has_col(df.columns, ["Hora Final", "Hora_fim"])
        and _has_col(df.columns, ["Dados do morador/Agentes", "Agentes"])
        and _has_col(df.columns, ["meta/rootUuid", "_uuid", "meta/instanceID"])
    )


def processar_arquivo(path, conn, logger, agora_iso, dry_run=False, aceitar_legado=False):
    estrutura = "nova" if is_new_format(path) else "legada"
    if estrutura != "nova" and not aceitar_legado:
        raise ValidationError("Planilha de esporotricose em formato legado. Use a importacao historica unica.")

    visitas, animais = parse_workbook(path, estrutura)
    logger.log(f"  Estrutura: {estrutura} | Visitas: {len(visitas)} | Animais: {len(animais)}")

    inseridas = animais_inseridos = vinculos = duplicadas = 0
    for visita in visitas:
        visita["arquivo_origem"] = _basename(path)
        visita["origem_estrutura"] = estrutura
        nova = _inserir_visita(conn, visita, agora_iso)
        if nova:
            inseridas += 1
        else:
            duplicadas += 1
        vinculos += _inserir_agentes(conn, visita["id_visita"], visita.get("agentes_texto"))

    for animal in animais:
        animal["arquivo_origem"] = _basename(path)
        if _inserir_animal(conn, animal, agora_iso):
            animais_inseridos += 1

    logger.log(
        f"  Visitas novas: {inseridas} | Duplicadas: {duplicadas} | "
        f"Animais novos: {animais_inseridos} | Vinculos agentes: {vinculos}",
        "ok",
    )
    return {
        "ok": True,
        "tipo": "ESPOROTRICOSE",
        "visitas_novas": inseridas,
        "animais_novos": animais_inseridos,
        "coletas_novas": animais_inseridos,
        "resultados_novos": 0,
        "duplicadas": duplicadas,
    }


def parse_workbook(path, estrutura=None):
    with pd.ExcelFile(path, engine="openpyxl") as xls:
        sheet_names = list(xls.sheet_names)
    main = pd.read_excel(path, sheet_name=sheet_names[0], engine="openpyxl").dropna(how="all")
    animals_df = pd.read_excel(path, sheet_name=sheet_names[1], engine="openpyxl").dropna(how="all")
    estrutura = estrutura or ("nova" if is_new_format(path) else "legada")

    visitas = []
    uuid_to_id = {}
    index_to_id = {}
    for _, row in main.iterrows():
        uuid = _uuid(row.get("_uuid"))
        if not uuid:
            continue
        data = _date(_row_get(row, ["Dados do morador/Data", "Data"]))
        if not data:
            continue
        id_visita = _hash("esporotricose:visita", uuid)
        visita = {
            "id_visita": id_visita,
            "kobo_uuid": uuid,
            "kobo_id": _int(row.get("_id")),
            "data": data,
            "hora_inicio": _time(_row_get(row, ["Dados do morador/Hora Inicio", "Hora_inicio", "Dados do morador/Hora"])),
            "hora_fim": _time(_row_get(row, ["Hora Final", "Hora_fim"])) if estrutura == "nova" else None,
            "inicio_registro": _datetime(row.get("start")) if estrutura == "nova" else None,
            "fim_registro": _datetime(row.get("end")) if estrutura == "nova" else None,
            "agentes_texto": _text(_row_get(row, ["Dados do morador/Agentes", "Dados do morador/Nome do(s) agente(s)", "Agentes"])),
            "localidade": _localidade(_row_get(row, ["Dados do morador/Localidade", "Localidade"])),
            "quarteirao": _int(_row_get(row, ["Dados do morador/Quarteirão", "Quarteirao", "Quarteir_o"])),
            "tipo_imovel": _choice(_row_get(row, ["Dados do morador/Tipo do imóvel", "Tipo_do_im_vel", "Tipo do imovel"])),
            "logradouro": _text(_row_get(row, ["Dados do morador/Logradouro", "Logradouro"])),
            "numero": _text(_row_get(row, ["Dados do morador/Número", "Numero", "N_mero"])),
            "morador": _text(_row_get(row, ["Dados do morador/Morador", "Morador"])),
            "visita": _choice(_row_get(row, ["Dados do morador/Visita:", "Visita"])),
            "telefone": _text(_row_get(row, ["Dados do morador/Telefone", "Telefone"])),
            "observacoes": _text(_row_get(row, ["Dados do morador/Observações", "Observacoes", "Observa_es"])),
            "deseja_cadastrar_animal": _text(_row_get(row, ["Deseja cadastrar um animal?", "Deseja_cadastrar_um_animal"])),
            "submission_time": _datetime(row.get("_submission_time")),
        }
        visitas.append(visita)
        uuid_to_id[uuid] = id_visita
        idx = _text(row.get("_index"))
        if idx:
            index_to_id[idx] = id_visita

    animais = []
    for _, row in animals_df.iterrows():
        sub_uuid = _uuid(row.get("_submission__uuid"))
        parent_idx = _text(row.get("_parent_index"))
        id_visita = uuid_to_id.get(sub_uuid) or index_to_id.get(parent_idx)
        if not id_visita:
            continue
        animal_uuid = f"{sub_uuid or parent_idx}:{_text(row.get('_index')) or len(animais)}"
        animais.append({
            "id_animal": _hash("esporotricose:animal", animal_uuid),
            "id_visita": id_visita,
            "kobo_uuid": animal_uuid,
            "especie": _choice(_row_get(row, ["Dados do animal/Escolha o animal a ser cadastrado:", "Escolha_o_animal_a_ser_cadastr"])),
            "outro_animal": _choice(_row_get(row, ["Dados do animal/Qual animal?", "Esp_cie", "Especie"])),
            "nome": _text(_row_get(row, ["Dados do animal/Nome do animal:", "Nome_do_animal"])),
            "raca": _text(_row_get(row, ["Dados do animal/Raça:", "Raca", "Ra_a"])),
            "sexo": _choice(_row_get(row, ["Dados do animal/Sexo:", "Sexo"])),
            "ambiente": _choice(_row_get(row, ["Dados do animal/Classificação quanto ao ambiente em que o animal vive:", "Classifica_o_quanto_em_que_o_animal_vive"])),
            "vacinado": _choice(_row_get(row, ["Dados do animal/Vacinado?", "Vacinado"])),
            "castrado": _choice(_row_get(row, ["Dados do animal/Castrado?", "Castrado"])),
            "feridas": _choice(_row_get(row, ["Dados do animal/Apresenta feridas pelo corpo?", "Apresenta_feridas_pelo_corpo"])),
            "regiao_ferida": _text(_row_get(row, ["Dados do animal/Região:", "Regiao", "Regi_o"])),
            "atendimento_veterinario": _choice(_row_get(row, ["Dados do animal/Já passou por atendimento veterinário?", "J_passou_por_atendimento_vete"])),
            "data_atendimento": _date(_row_get(row, ["Dados do animal/Data do atendimento:", "Data_do_atendimento"])),
            "evolucao_caso": _text(_row_get(row, ["Dados do animal/Evolução do caso:", "Evolu_o_do_caso"])),
        })
    return visitas, animais


def importar_historico(paths, db_path, logger, dry_run=False):
    conn = __import__("sqlite3").connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_schema(conn)
    agora_iso = datetime.now().isoformat(timespec="seconds")
    total = {"visitas": 0, "animais": 0}
    try:
        conn.execute("BEGIN")
        for path in paths:
            result = processar_arquivo(path, conn, logger, agora_iso, dry_run=dry_run, aceitar_legado=True)
            total["visitas"] += result.get("visitas_novas", 0)
            total["animais"] += result.get("animais_novos", 0)
        if dry_run:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return total


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        totais = dict(conn.execute(
            f"""SELECT
                COUNT(*) AS visitas,
                COUNT(DISTINCT data) AS dias,
                COUNT(DISTINCT localidade) AS localidades,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='normal' THEN 1 ELSE 0 END) AS normais,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='fechado' THEN 1 ELSE 0 END) AS fechadas,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='recusa' THEN 1 ELSE 0 END) AS recusas,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='recuperado' THEN 1 ELSE 0 END) AS recuperadas
              FROM esporotricose_visitas v {where}""",
            params,
        ).fetchone())
        animais = dict(conn.execute(
            f"""SELECT
                COUNT(a.id_animal) AS total,
                SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'c%' THEN 1 ELSE 0 END) AS caes,
                SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'gato%' THEN 1 ELSE 0 END) AS gatos,
                SUM(CASE WHEN LOWER(COALESCE(a.feridas,''))='sim' THEN 1 ELSE 0 END) AS com_feridas
              FROM esporotricose_visitas v
              LEFT JOIN esporotricose_animais a ON a.id_visita=v.id_visita
              {where}""",
            params,
        ).fetchone())
        por_localidade = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(v.localidade,'-') AS localidade, COUNT(*) AS total
                FROM esporotricose_visitas v {where}
                GROUP BY COALESCE(v.localidade,'-') ORDER BY total DESC, localidade LIMIT 12""",
            params,
        )]
        recentes = [dict(r) for r in conn.execute(
            f"""SELECT v.id_visita, v.data, v.localidade, v.quarteirao, v.logradouro, v.numero,
                       v.morador, v.telefone, v.visita, COUNT(a.id_animal) AS animais
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita=v.id_visita
                {where}
                GROUP BY v.id_visita
                ORDER BY v.data DESC, v.hora_inicio DESC
                LIMIT 100""",
            params,
        )]
    finally:
        conn.close()
    return {
        "totais": {k: (v or 0) for k, v in totais.items()},
        "animais": {k: (v or 0) for k, v in animais.items()},
        "por_localidade": por_localidade,
        "recentes": recentes,
    }


def listar_visitas(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where_visitas(filtros)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM esporotricose_visitas v {where}",
            params,
        ).fetchone()[0]
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    v.id_visita, v.kobo_uuid, v.data, v.hora_inicio, v.hora_fim,
                    v.inicio_registro, v.fim_registro, v.agentes_texto,
                    v.localidade, v.id_localidade, v.quarteirao, v.tipo_imovel,
                    v.logradouro, v.numero, v.morador, v.telefone, v.visita,
                    v.observacoes, v.deseja_cadastrar_animal, v.submission_time,
                    v.processado_em, COUNT(a.id_animal) AS animais,
                    COALESCE(GROUP_CONCAT(DISTINCT ag.nome), '') AS agentes
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
                LEFT JOIN esporotricose_visita_agentes va ON va.id_visita = v.id_visita
                LEFT JOIN agentes ag ON ag.id_agente = va.id_agente
                {where}
                GROUP BY v.id_visita
                ORDER BY v.data DESC, v.hora_inicio DESC, v.localidade, v.quarteirao
                LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"total": total or 0, "registros": registros}


def atualizar_visita(db_path, id_visita, dados):
    campos = []
    params = []
    for coluna in ("data", "hora_inicio", "hora_fim", "agentes_texto", "localidade",
                     "quarteirao", "tipo_imovel", "logradouro", "numero", "morador",
                     "telefone", "visita", "observacoes", "deseja_cadastrar_animal"):
        if coluna in dados:
            campos.append(f"{coluna} = ?")
            params.append(dados[coluna])
    if not campos:
        raise ValueError("Nenhum campo para atualizar.")
    params.append(id_visita)
    conn = db_core.connect(db_path)
    try:
        conn.execute(
            f"UPDATE esporotricose_visitas SET {', '.join(campos)} WHERE id_visita = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def atualizar_animal(db_path, id_animal, dados):
    campos = []
    params = []
    for coluna in ("especie", "outro_animal", "nome", "raca", "sexo", "ambiente",
                     "vacinado", "castrado", "feridas", "regiao_ferida",
                     "atendimento_veterinario", "data_atendimento", "evolucao_caso"):
        if coluna in dados:
            campos.append(f"{coluna} = ?")
            params.append(dados[coluna])
    if not campos:
        raise ValueError("Nenhum campo para atualizar.")
    params.append(id_animal)
    conn = db_core.connect(db_path)
    try:
        conn.execute(
            f"UPDATE esporotricose_animais SET {', '.join(campos)} WHERE id_animal = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def listar_animais(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where_animais(filtros)
    try:
        total = conn.execute(
            f"""SELECT COUNT(*)
                FROM esporotricose_animais a
                JOIN esporotricose_visitas v ON v.id_visita = a.id_visita
                {where}""",
            params,
        ).fetchone()[0]
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    a.id_animal, a.especie, a.outro_animal, a.nome, a.raca, a.sexo,
                    a.ambiente, a.vacinado, a.castrado, a.feridas, a.regiao_ferida,
                    a.atendimento_veterinario, a.data_atendimento, a.evolucao_caso,
                    {MOTIVO_ATENCAO_SQL} AS motivo_atencao,
                    v.data, v.localidade, v.quarteirao, v.logradouro, v.numero,
                    v.morador, v.telefone, v.visita
                FROM esporotricose_animais a
                JOIN esporotricose_visitas v ON v.id_visita = a.id_visita
                {where}
                ORDER BY
                    CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 0 ELSE 1 END,
                    v.data DESC,
                    v.localidade,
                    a.especie,
                    a.nome
                LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"total": total or 0, "registros": registros}


def resumo_localidades(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    COALESCE(v.localidade, '-') AS localidade,
                    COUNT(DISTINCT v.id_visita) AS visitas,
                    COUNT(a.id_animal) AS animais,
                    SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'c%' THEN 1 ELSE 0 END) AS caes,
                    SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'gato%' THEN 1 ELSE 0 END) AS gatos,
                    SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 1 ELSE 0 END) AS com_feridas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,'')) = 'fechado' THEN v.id_visita END) AS fechadas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,'')) = 'recusa' THEN v.id_visita END) AS recusas
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
                {where}
                GROUP BY COALESCE(v.localidade, '-')
                ORDER BY visitas DESC, localidade""",
            params,
        )]
    finally:
        conn.close()
    return {"registros": [{k: (v or 0) if k != "localidade" else v for k, v in row.items()} for row in registros]}


def dashboard(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        evolucao = _rows(conn, f"""
            SELECT substr(v.data, 1, 7) AS mes, COUNT(*) AS visitas
            FROM esporotricose_visitas v {where}
            GROUP BY substr(v.data, 1, 7)
            ORDER BY mes
        """, params)
        status = _rows(conn, f"""
            SELECT COALESCE(NULLIF(v.visita, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v {where}
            GROUP BY COALESCE(NULLIF(v.visita, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        especies = _rows(conn, f"""
            SELECT COALESCE(NULLIF(a.especie, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v
            JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(NULLIF(a.especie, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        ambiente = _rows(conn, f"""
            SELECT COALESCE(NULLIF(a.ambiente, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v
            JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(NULLIF(a.ambiente, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        localidades = _rows(conn, f"""
            SELECT COALESCE(v.localidade, '-') AS nome, COUNT(DISTINCT v.id_visita) AS visitas, COUNT(a.id_animal) AS animais
            FROM esporotricose_visitas v
            LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(v.localidade, '-')
            ORDER BY visitas DESC, nome
            LIMIT 12
        """, params)
        saude = _rows(conn, f"""
            SELECT 'Feridas' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 1 ELSE 0 END) AS sim,
                   SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'não' THEN 1 ELSE 0 END) AS nao,
                   SUM(CASE WHEN a.feridas IS NULL OR LOWER(COALESCE(a.feridas,'')) = 'desconhecido' THEN 1 ELSE 0 END) AS desconhecido
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
            UNION ALL
            SELECT 'Vacinados' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.vacinado,'')) = 'sim' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN LOWER(COALESCE(a.vacinado,'')) = 'não' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN a.vacinado IS NULL OR LOWER(COALESCE(a.vacinado,'')) = 'desconhecido' THEN 1 ELSE 0 END)
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
            UNION ALL
            SELECT 'Castrados' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.castrado,'')) = 'sim' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN LOWER(COALESCE(a.castrado,'')) = 'não' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN a.castrado IS NULL OR LOWER(COALESCE(a.castrado,'')) = 'desconhecido' THEN 1 ELSE 0 END)
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
        """, params * 3)
    finally:
        conn.close()
    return {
        "evolucao": evolucao,
        "status": status,
        "especies": especies,
        "ambiente": ambiente,
        "localidades": localidades,
        "saude": saude,
    }


def listar_doentes(db_path, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where = []
        params = []
        busca = _text(filtros.get("busca"))
        status = _text(filtros.get("status"))
        especie = _text(filtros.get("especie"))
        localidade = _text(filtros.get("localidade"))
        bloqueio = _normalizar_bloqueio_doente(filtros.get("bloqueio"))
        pedido_zoomed = _normalizar_sim_nao(filtros.get("pedido_zoomed"))
        baixa_zoomed = _text(filtros.get("baixa_zoomed"))
        if status:
            where.append("d.status=?")
            params.append(status)
        if localidade:
            where.append("d.localidade=?")
            params.append(localidade)
        if bloqueio:
            where.append("d.bloqueio=?")
            params.append(bloqueio)
        if pedido_zoomed:
            where.append("d.pedido_zoomed=?")
            params.append(pedido_zoomed)
        if busca:
            termo = f"%{busca}%"
            where.append(
                "(d.tutor LIKE ? OR d.nome LIKE ? OR d.telefone LIKE ? OR d.endereco LIKE ? OR d.sinan LIKE ?)"
            )
            params.extend([termo] * 5)
        sql = """
            SELECT d.*,
                   COUNT(DISTINCT r.id_receita) AS receitas,
                   COUNT(DISTINCT an.id_anexo) AS anexos,
                   MAX(r.data_notificacao) AS ultima_notificacao,
                   MAX(r.data_receita) AS ultima_receita,
                   MAX(e.data_entrega) AS ultima_entrega,
                   COALESCE(SUM(e.quantidade), 0) AS capsulas_entregues,
                   COUNT(DISTINCT e.id_entrega) AS entregas,
                   COUNT(DISTINCT CASE WHEN e.baixa_zoomed='Não' THEN e.id_entrega END) AS entregas_zoomed_pendentes
              FROM esporotricose_doentes_animais d
              LEFT JOIN esporotricose_doentes_receitas r ON r.id_animal_doente=d.id_animal_doente
              LEFT JOIN esporotricose_doentes_entregas e ON e.id_receita=r.id_receita
              LEFT JOIN esporotricose_doentes_anexos an ON an.id_animal_doente=d.id_animal_doente
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY d.id_animal_doente"
        if baixa_zoomed == "Pendente":
            sql += """ HAVING COUNT(DISTINCT CASE WHEN e.baixa_zoomed='Não' THEN e.id_entrega END) > 0
                        OR (d.status='Em tratamento' AND COUNT(DISTINCT e.id_entrega)=0)"""
        elif baixa_zoomed == "Sim":
            sql += """ HAVING COUNT(DISTINCT CASE WHEN e.baixa_zoomed='Não' THEN e.id_entrega END) = 0
                        AND NOT (d.status='Em tratamento' AND COUNT(DISTINCT e.id_entrega)=0)"""
        sql += """
                   ORDER BY COALESCE(MAX(r.data_notificacao), '') DESC,
                            d.id_animal_doente DESC"""
        rows = [_doente_row(row) for row in conn.execute(sql, params).fetchall()]
        if especie:
            especie_norm = _sem_acentos(especie).strip().casefold()
            rows = [row for row in rows if _sem_acentos(row.get("especie")).strip().casefold() == especie_norm]
        return {"registros": rows, "total": len(rows)}
    finally:
        conn.close()


def listar_doentes_csv(db_path, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where = []
        params = []
        busca = _text(filtros.get("busca"))
        status = _text(filtros.get("status"))
        localidade = _text(filtros.get("localidade"))
        bloqueio = _normalizar_bloqueio_doente(filtros.get("bloqueio"))
        pedido_zoomed = _normalizar_sim_nao(filtros.get("pedido_zoomed"))
        baixa_zoomed = _text(filtros.get("baixa_zoomed"))
        if status:
            where.append("d.status=?")
            params.append(status)
        if localidade:
            where.append("d.localidade=?")
            params.append(localidade)
        if bloqueio:
            where.append("d.bloqueio=?")
            params.append(bloqueio)
        if pedido_zoomed:
            where.append("d.pedido_zoomed=?")
            params.append(pedido_zoomed)
        if busca:
            termo = f"%{busca}%"
            where.append(
                "(d.tutor LIKE ? OR d.nome LIKE ? OR d.telefone LIKE ? OR d.endereco LIKE ? OR d.sinan LIKE ?)"
            )
            params.extend([termo] * 5)
        sql = """
            SELECT d.id_animal_doente,
                   d.nome AS animal,
                   d.tutor,
                   d.telefone,
                   d.especie,
                   d.sexo,
                   d.status,
                   d.localidade,
                   d.quarteirao,
                   d.endereco,
                   d.latitude,
                   d.longitude,
                   d.sinan,
                   d.bloqueio,
                   d.data_bloqueio,
                   d.pedido_zoomed,
                   d.observacoes_entomologica,
                   MIN(r.data_notificacao) AS primeira_notificacao,
                   MAX(r.data_notificacao) AS ultima_notificacao,
                   MAX(r.data_receita) AS ultima_receita,
                   COUNT(DISTINCT r.id_receita) AS receitas,
                   (
                       SELECT COALESCE(SUM(e.quantidade), 0)
                         FROM esporotricose_doentes_entregas e
                         JOIN esporotricose_doentes_receitas re ON re.id_receita=e.id_receita
                        WHERE re.id_animal_doente=d.id_animal_doente
                   ) AS capsulas_entregues,
                   (
                       SELECT COUNT(*)
                         FROM esporotricose_doentes_entregas e
                         JOIN esporotricose_doentes_receitas re ON re.id_receita=e.id_receita
                        WHERE re.id_animal_doente=d.id_animal_doente
                   ) AS entregas,
                   (
                       SELECT COUNT(*)
                         FROM esporotricose_doentes_entregas e
                         JOIN esporotricose_doentes_receitas re ON re.id_receita=e.id_receita
                        WHERE re.id_animal_doente=d.id_animal_doente
                          AND e.baixa_zoomed='Não'
                   ) AS entregas_zoomed_pendentes,
                   (
                       SELECT COUNT(*)
                         FROM esporotricose_doentes_anexos an
                        WHERE an.id_animal_doente=d.id_animal_doente
                   ) AS anexos
              FROM esporotricose_doentes_animais d
              LEFT JOIN esporotricose_doentes_receitas r ON r.id_animal_doente=d.id_animal_doente
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY d.id_animal_doente"
        if baixa_zoomed == "Pendente":
            sql += """ HAVING entregas_zoomed_pendentes > 0
                        OR (d.status='Em tratamento' AND entregas=0)"""
        elif baixa_zoomed == "Sim":
            sql += """ HAVING entregas_zoomed_pendentes = 0
                        AND NOT (d.status='Em tratamento' AND entregas=0)"""
        sql += """
                   ORDER BY COALESCE(MAX(r.data_notificacao), '') DESC,
                            d.id_animal_doente DESC"""
        rows = []
        for row in conn.execute(sql, params).fetchall():
            item = dict(row)
            pendentes = int(item.get("entregas_zoomed_pendentes") or 0)
            entregas = int(item.get("entregas") or 0)
            if entregas == 0 and item.get("status") == "Em tratamento" and pendentes == 0:
                pendentes = 1
            item["baixa_zoomed"] = "Pendente" if pendentes else "Sim"
            item["data_notificacao"] = item.get("ultima_notificacao") or item.get("primeira_notificacao")
            item["especie"] = _especie_doente(item)
            rows.append(item)
        return rows
    finally:
        conn.close()


def obter_doente(db_path, id_animal_doente):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM esporotricose_doentes_animais WHERE id_animal_doente=?",
            (id_animal_doente,),
        ).fetchone()
        if not row:
            return None
        animal = _doente_row(row)
        receitas = []
        for receita in conn.execute(
            """SELECT * FROM esporotricose_doentes_receitas
                WHERE id_animal_doente=?
                ORDER BY COALESCE(data_receita, data_notificacao, criado_em) DESC, id_receita DESC""",
            (id_animal_doente,),
        ).fetchall():
            item = dict(receita)
            item["prazo_receita_dias"] = _dias_desde(item.get("data_receita"))
            item["entregas"] = [
                dict(e) for e in conn.execute(
                    """SELECT * FROM esporotricose_doentes_entregas
                        WHERE id_receita=?
                        ORDER BY data_entrega, id_entrega""",
                    (item["id_receita"],),
                ).fetchall()
            ]
            receitas.append(item)
        animal["receitas"] = receitas
        animal["anexos"] = [_anexo_doente_dict(row) for row in conn.execute(
            """SELECT * FROM esporotricose_doentes_anexos
                WHERE id_animal_doente=?
                ORDER BY criado_em DESC, id_anexo DESC""",
            (id_animal_doente,),
        ).fetchall()]
        return animal
    finally:
        conn.close()


def salvar_doente(db_path, dados):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        agora = datetime.now().isoformat(timespec="seconds")
        payload = _doente_payload(dados)
        id_animal = _int(dados.get("id_animal_doente"))
        if payload.get("status"):
            _salvar_status_doente(conn, payload["status"])
        if id_animal:
            conn.execute(
                """UPDATE esporotricose_doentes_animais
                      SET tutor=?, nome=?, especie=?, sexo=?, telefone=?, localidade=?, quarteirao=?,
                          endereco=?, latitude=?, longitude=?, sinan=?, status=?, bloqueio=?,
                          data_bloqueio=?, observacoes_entomologica=?, pedido_zoomed=?,
                          atualizado_em=?
                    WHERE id_animal_doente=?""",
                (
                    payload["tutor"], payload["nome"], payload["especie"], payload["sexo"], payload["telefone"],
                    payload["localidade"], payload["quarteirao"], payload["endereco"],
                    payload["latitude"], payload["longitude"], payload["sinan"], payload["status"],
                    payload["bloqueio"], payload["data_bloqueio"], payload["observacoes_entomologica"],
                    payload["pedido_zoomed"], agora, id_animal,
                ),
            )
        else:
            chave = _doente_chave(payload)
            cur = conn.execute(
                """INSERT INTO esporotricose_doentes_animais
                   (chave, tutor, nome, especie, sexo, telefone, localidade, quarteirao, endereco,
                    latitude, longitude, sinan, status, bloqueio, data_bloqueio,
                    observacoes_entomologica, pedido_zoomed, criado_em, atualizado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    chave, payload["tutor"], payload["nome"], payload["especie"], payload["sexo"], payload["telefone"],
                    payload["localidade"], payload["quarteirao"], payload["endereco"],
                    payload["latitude"], payload["longitude"], payload["sinan"], payload["status"],
                    payload["bloqueio"], payload["data_bloqueio"], payload["observacoes_entomologica"],
                    payload["pedido_zoomed"], agora, agora,
                ),
            )
            id_animal = cur.lastrowid
        conn.commit()
        return id_animal
    finally:
        conn.close()


def salvar_receita_doente(db_path, id_animal_doente, dados):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        existe = conn.execute(
            "SELECT 1 FROM esporotricose_doentes_animais WHERE id_animal_doente=?",
            (id_animal_doente,),
        ).fetchone()
        if not existe:
            raise ValidationError("Animal doente não encontrado.")
        agora = datetime.now().isoformat(timespec="seconds")
        payload = _receita_payload(dados)
        id_receita = _int(dados.get("id_receita"))
        if payload.get("status"):
            _salvar_status_doente(conn, payload["status"])
        if id_receita:
            conn.execute(
                """UPDATE esporotricose_doentes_receitas
                      SET data_notificacao=?, inicio_sintomas=?, data_receita=?,
                          visita_va_veterinario=?, capsulas_total=?, posologia=?,
                          status=?, observacoes=?, atualizado_em=?
                    WHERE id_receita=? AND id_animal_doente=?""",
                (
                    payload["data_notificacao"], payload["inicio_sintomas"], payload["data_receita"],
                    payload["visita_va_veterinario"], payload["capsulas_total"], payload["posologia"],
                    payload["status"], payload["observacoes"], agora, id_receita, id_animal_doente,
                ),
            )
        else:
            cur = conn.execute(
                """INSERT INTO esporotricose_doentes_receitas
                   (id_animal_doente, data_notificacao, inicio_sintomas, data_receita,
                    visita_va_veterinario, capsulas_total, posologia, status, observacoes,
                    origem_linha, criado_em, atualizado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    id_animal_doente, payload["data_notificacao"], payload["inicio_sintomas"],
                    payload["data_receita"], payload["visita_va_veterinario"], payload["capsulas_total"],
                    payload["posologia"], payload["status"], payload["observacoes"], None, agora, agora,
                ),
            )
            id_receita = cur.lastrowid
        conn.execute(
            "UPDATE esporotricose_doentes_animais SET atualizado_em=? WHERE id_animal_doente=?",
            (agora, id_animal_doente),
        )
        conn.commit()
        return id_receita
    finally:
        conn.close()


def salvar_entrega_doente(db_path, id_receita, dados):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        receita = conn.execute(
            "SELECT id_animal_doente FROM esporotricose_doentes_receitas WHERE id_receita=?",
            (id_receita,),
        ).fetchone()
        if not receita:
            raise ValidationError("Receita não encontrada.")
        quantidade = _int(dados.get("quantidade"))
        if not quantidade:
            raise ValidationError("Informe a quantidade de cápsulas.")
        baixa_zoomed = _normalizar_sim_nao(dados.get("baixa_zoomed")) or "Não"
        agora = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            """INSERT INTO esporotricose_doentes_entregas
               (id_receita, quantidade, data_entrega, baixa_zoomed, observacoes, criado_em)
               VALUES (?,?,?,?,?,?)""",
            (id_receita, quantidade, _date(dados.get("data_entrega")), baixa_zoomed, _text(dados.get("observacoes")), agora),
        )
        conn.execute(
            "UPDATE esporotricose_doentes_animais SET atualizado_em=? WHERE id_animal_doente=?",
            (agora, receita["id_animal_doente"]),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def atualizar_entrega_doente(db_path, id_entrega, dados):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            """SELECT e.id_entrega, r.id_animal_doente
                 FROM esporotricose_doentes_entregas e
                 JOIN esporotricose_doentes_receitas r ON r.id_receita=e.id_receita
                WHERE e.id_entrega=?""",
            (id_entrega,),
        ).fetchone()
        if not row:
            raise ValidationError("Entrega não encontrada.")
        quantidade = _int(dados.get("quantidade"))
        if not quantidade:
            raise ValidationError("Informe a quantidade de cápsulas.")
        baixa_zoomed = _normalizar_sim_nao(dados.get("baixa_zoomed")) or "Não"
        conn.execute(
            """UPDATE esporotricose_doentes_entregas
                  SET quantidade=?, data_entrega=?, baixa_zoomed=?, observacoes=?
                WHERE id_entrega=?""",
            (
                quantidade,
                _date(dados.get("data_entrega")),
                baixa_zoomed,
                _text(dados.get("observacoes")),
                id_entrega,
            ),
        )
        conn.execute(
            "UPDATE esporotricose_doentes_animais SET atualizado_em=? WHERE id_animal_doente=?",
            (datetime.now().isoformat(timespec="seconds"), row["id_animal_doente"]),
        )
        conn.commit()
    finally:
        conn.close()


def excluir_doente(db_path, id_animal_doente):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        animal = conn.execute(
            f"SELECT * FROM {DOENTES_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        ).fetchone()
        if not animal:
            raise ValidationError("Animal doente não encontrado.")
        anexos = conn.execute(
            f"SELECT * FROM {DOENTES_ANEXOS_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        ).fetchall()
        receitas = conn.execute(
            f"SELECT id_receita FROM {DOENTES_RECEITAS_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        ).fetchall()
        receita_ids = [row["id_receita"] for row in receitas]
        if receita_ids:
            placeholders = ",".join("?" for _ in receita_ids)
            conn.execute(
                f"DELETE FROM {DOENTES_ENTREGAS_TABLE} WHERE id_receita IN ({placeholders})",
                receita_ids,
            )
        conn.execute(
            f"DELETE FROM {DOENTES_ANEXOS_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        )
        conn.execute(
            f"DELETE FROM {DOENTES_RECEITAS_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        )
        conn.execute(
            f"DELETE FROM {DOENTES_TABLE} WHERE id_animal_doente=?",
            (id_animal_doente,),
        )
        conn.commit()
        return {"animal": _doente_row(animal), "anexos": [dict(row) for row in anexos]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def excluir_receita_doente(db_path, id_receita):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            f"SELECT id_animal_doente FROM {DOENTES_RECEITAS_TABLE} WHERE id_receita=?",
            (id_receita,),
        ).fetchone()
        if not row:
            raise ValidationError("Receita não encontrada.")
        id_animal_doente = row["id_animal_doente"]
        conn.execute(
            f"DELETE FROM {DOENTES_RECEITAS_TABLE} WHERE id_receita=?",
            (id_receita,),
        )
        conn.execute(
            f"UPDATE {DOENTES_TABLE} SET atualizado_em=? WHERE id_animal_doente=?",
            (datetime.now().isoformat(timespec="seconds"), id_animal_doente),
        )
        conn.commit()
        return id_animal_doente
    finally:
        conn.close()


def excluir_entrega_doente(db_path, id_entrega):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM esporotricose_doentes_entregas WHERE id_entrega=?", (id_entrega,))
        conn.commit()
    finally:
        conn.close()


def status_doentes(db_path):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        rows = [dict(row) for row in conn.execute(
            "SELECT id_status, nome, ativo FROM esporotricose_doentes_status WHERE ativo=1"
        )]
        ordem = {nome: i for i, nome in enumerate(DOENTES_STATUS_PADRAO)}
        return sorted(rows, key=lambda row: ordem.get(row["nome"], 999))
    finally:
        conn.close()


def salvar_status_doente(db_path, nome):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        _salvar_status_doente(conn, nome)
        conn.commit()
    finally:
        conn.close()


def importar_doentes_planilha(db_path, caminho):
    df = pd.read_excel(caminho, dtype=object, engine="openpyxl")
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        existentes = 0
        animais_novos = 0
        receitas_novas = 0
        entregas_novas = 0
        for idx, row in df.iterrows():
            animal_payload = {
                "tutor": _text(row.get("TUTOR")),
                "nome": _text(row.get("NOME")),
                "especie": _normalizar_especie_doente(row.get("ESPECIE") or row.get("ESPÉCIE")) or "Gato",
                "sexo": _choice(row.get("SEXO")) or _text(row.get("SEXO")),
                "telefone": _telefone(row.get("TELEFONE")),
                "localidade": normalizadores.normalizar_localidade(row.get("LOCALIDADE")),
                "quarteirao": _text(row.get("QUARTEIRÃO")),
                "endereco": _text(row.get("ENDEREÇO")),
                "latitude": _real(row.get("LATITUDE")),
                "longitude": _real(row.get("LONGITUDE")),
                "sinan": _text(row.get("SINAN")),
                "status": _status_planilha(row.get("STATUS")),
                "bloqueio": _text(row.get("BLOQUEIO")),
                "data_bloqueio": _date(row.get("DATA BLOQUEIO")),
                "observacoes_entomologica": _text(row.get("OBSERVAÇÕES ENTOMOLOGICA")),
                "pedido_zoomed": _text(row.get("PEDIDO ZOOMED")),
            }
            if not animal_payload["nome"] or not animal_payload["tutor"]:
                continue
            chave = _doente_chave(animal_payload)
            agora = datetime.now().isoformat(timespec="seconds")
            animal = conn.execute(
                "SELECT id_animal_doente FROM esporotricose_doentes_animais WHERE chave=?",
                (chave,),
            ).fetchone()
            if animal:
                id_animal = animal["id_animal_doente"]
                existentes += 1
                conn.execute(
                    """UPDATE esporotricose_doentes_animais
                          SET telefone=COALESCE(?, telefone), sinan=COALESCE(?, sinan),
                              status=COALESCE(?, status), atualizado_em=?
                        WHERE id_animal_doente=?""",
                    (animal_payload["telefone"], animal_payload["sinan"], animal_payload["status"], agora, id_animal),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO esporotricose_doentes_animais
                       (chave, tutor, nome, especie, sexo, telefone, localidade, quarteirao, endereco,
                        latitude, longitude, sinan, status, bloqueio, data_bloqueio,
                        observacoes_entomologica, pedido_zoomed, criado_em, atualizado_em)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        chave, animal_payload["tutor"], animal_payload["nome"], animal_payload["especie"], animal_payload["sexo"],
                        animal_payload["telefone"], animal_payload["localidade"], animal_payload["quarteirao"],
                        animal_payload["endereco"], animal_payload["latitude"], animal_payload["longitude"],
                        animal_payload["sinan"], animal_payload["status"], animal_payload["bloqueio"],
                        animal_payload["data_bloqueio"], animal_payload["observacoes_entomologica"],
                        animal_payload["pedido_zoomed"], agora, agora,
                    ),
                )
                id_animal = cur.lastrowid
                animais_novos += 1
            if animal_payload.get("status"):
                _salvar_status_doente(conn, animal_payload["status"])
            receita_payload = {
                "data_notificacao": _date(row.get("DATA NOTIFICAÇÃO")),
                "inicio_sintomas": _date(row.get("INICIO DOS SINTOMAS")),
                "data_receita": _date(row.get("RECEITA ")),
                "visita_va_veterinario": _date(row.get("Visita  VA + Veterinario")),
                "capsulas_total": _int(row.get("Cápsulas total da receita")),
                "posologia": _text(row.get("Posologia")),
                "status": animal_payload["status"],
                "observacoes": _text(row.get("OBSERVAÇÕES ENTOMOLOGICA")),
            }
            cur = conn.execute(
                """INSERT INTO esporotricose_doentes_receitas
                   (id_animal_doente, data_notificacao, inicio_sintomas, data_receita,
                    visita_va_veterinario, capsulas_total, posologia, status, observacoes,
                    origem_linha, criado_em, atualizado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    id_animal, receita_payload["data_notificacao"], receita_payload["inicio_sintomas"],
                    receita_payload["data_receita"], receita_payload["visita_va_veterinario"],
                    receita_payload["capsulas_total"], receita_payload["posologia"], receita_payload["status"],
                    receita_payload["observacoes"], int(idx) + 2, agora, agora,
                ),
            )
            id_receita = cur.lastrowid
            receitas_novas += 1
            for qtd, col in ((10, "Entregue/data\n10"), (30, "Entregue/data\n30"), (60, "Entregue/data\n60"), (90, "Entregue/data\n90")):
                data_entrega = _date(row.get(col))
                if data_entrega:
                    conn.execute(
                        """INSERT INTO esporotricose_doentes_entregas
                           (id_receita, quantidade, data_entrega, baixa_zoomed, observacoes, criado_em)
                           VALUES (?,?,?,?,?,?)""",
                        (id_receita, qtd, data_entrega, "Sim", None, agora),
                    )
                    entregas_novas += 1
        conn.commit()
        return {
            "animais_novos": animais_novos,
            "animais_existentes": existentes,
            "receitas_novas": receitas_novas,
            "entregas_novas": entregas_novas,
        }
    finally:
        conn.close()


def _doente_row(row):
    item = dict(row)
    item["especie"] = _especie_doente(item)
    if (
        int(item.get("entregas") or 0) == 0
        and item.get("status") == "Em tratamento"
        and int(item.get("entregas_zoomed_pendentes") or 0) == 0
    ):
        item["entregas_zoomed_pendentes"] = 1
    item["prazo_receita_dias"] = _dias_desde(item.get("ultima_receita"))
    item["whatsapp_documentos"] = whatsapp_documentos_url(item)
    item["whatsapp_retirada"] = whatsapp_retirada_url(item)
    return item


def _especie_doente(item):
    especie = _normalizar_especie_doente(item.get("especie"))
    if especie:
        return especie
    nome = _sem_acentos(item.get("nome") or item.get("animal")).strip().casefold()
    tutor = _sem_acentos(item.get("tutor")).strip().casefold()
    if nome == "belinha" and tutor == "jose altair natel":
        return "Cão"
    return "Gato"


def _normalizar_especie_doente(value):
    text = _text(value)
    if not text:
        return ""
    low = _sem_acentos(text).strip().casefold()
    if low in {"gato", "gata", "felino", "felina", "felino a"}:
        return "Gato"
    if low in {"cao", "caes", "cachorro", "cachorra", "canino", "canina"}:
        return "Cão"
    if low in {"outro", "outros", "outra", "outras"}:
        return "Outros"
    return text


def _anexo_doente_dict(row):
    item = dict(row)
    item["url_download"] = f"/esporotricose/doentes/anexos/{item['id_anexo']}/download"
    item["url_visualizar"] = f"/esporotricose/doentes/anexos/{item['id_anexo']}/download?inline=1"
    item["eh_previa"] = (item.get("mime_type") or "").startswith("image/") or item.get("mime_type") == "application/pdf"
    return item


def whatsapp_documentos_url(item):
    telefone = _telefone(item.get("telefone"))
    if not telefone:
        return ""
    nome = item.get("nome") or "felino(a)"
    msg = (
        "Olá! Tudo bem? Aqui é da Vigilância Ambiental da Prefeitura Municipal de Almirante Tamandaré-PR. "
        f"Recebemos uma notificação do(a) felino(a) {nome}. Por gentileza, para dar andamento do pedido da medicação ao SUS, "
        "precisamos que nos envie a cópia da receita, do comprovante de endereço atualizado e documento com CPF. "
        "Obrigado, ficamos à disposição para qualquer dúvida."
    )
    return _wa_url(telefone, msg)


def whatsapp_retirada_url(item):
    telefone = _telefone(item.get("telefone"))
    if not telefone:
        return ""
    nome = item.get("nome") or "felino(a)"
    msg = (
        f"Olá! Tudo bem? Estamos retornando para informar que chegou a medicação do(a) felino(a) {nome}! "
        "Local para retirada: Rua Bertholina Kendrick de Oliveira, 681 – Centro – Almirante Tamandaré – PR – CEP 83501-150 - em cima Detran"
    )
    return _wa_url(telefone, msg)


def _wa_url(telefone, msg):
    from urllib.parse import quote
    return f"https://wa.me/{telefone}?text={quote(msg)}"


def _normalizar_status_doente(value):
    text = _text(value)
    if not text:
        return "Em tratamento"
    low = _sem_acentos(text).lower()
    low = re.sub(r"[^a-z0-9]+", " ", low).strip()
    if "nao e esporotricose" in low or "nao esporotricose" in low or "nao eh esporotricose" in low:
        return "Não é esporotricose"
    if "faleceu" in low or "obito" in low or "morreu" in low:
        return "Faleceu"
    if "document" in low or "nao mandou" in low or "nao enviou" in low or low == "aguardando":
        return "Aguardando documentos"
    if "aguardando medic" in low or "pedido zoomed" in low or "sus" in low:
        return "Aguardando medicação"
    if "medicacao disponivel" in low or "retirada" in low or "chegou" in low or "buscar medicacao" in low:
        return "Medicação disponível"
    if "acabou" in low or "final" in low or "conclu" in low or "alta" in low:
        return "Acabou tratamento"
    if "tratamento" in low or low in {"ativo", "em andamento"}:
        return "Em tratamento"
    for status in DOENTES_STATUS_PADRAO:
        if _sem_acentos(status).lower() == low:
            return status
    return "Outro"


def _normalizar_sim_nao(value):
    text = _text(value)
    if not text:
        return ""
    low = _sem_acentos(text).lower()
    if low in {"sim", "s", "1", "true", "positivo"}:
        return "Sim"
    if low in {"nao", "n", "0", "false", "negativo"}:
        return "Não"
    return "Sim" if low.startswith("s") else "Não" if low.startswith("n") else ""


def _normalizar_bloqueio_doente(value):
    text = _text(value)
    if not text:
        return ""
    low = _sem_acentos(text).lower()
    low = re.sub(r"[^a-z0-9]+", " ", low).strip()
    if low in {"sim", "s", "1", "realizado", "feito", "concluido"}:
        return "Realizado"
    if low in {"nao", "n", "0", "nao realizado", "pendente", "aguardando"}:
        return "Não realizado"
    if low in {"nao necessario", "desnecessario", "dispensado"}:
        return "Não necessário"
    for opcao in BLOQUEIO_DOENTE_OPCOES:
        if _sem_acentos(opcao).lower() == low:
            return opcao
    return text


def _doente_payload(dados):
    nome = _text(dados.get("nome"))
    tutor = _text(dados.get("tutor"))
    if not nome:
        raise ValidationError("Informe o nome do animal.")
    if not tutor:
        raise ValidationError("Informe o tutor.")
    status = _normalizar_status_doente(dados.get("status"))
    return {
        "tutor": tutor,
        "nome": nome,
        "especie": _normalizar_especie_doente(dados.get("especie")) or "Gato",
        "sexo": _text(dados.get("sexo")),
        "telefone": _telefone(dados.get("telefone")),
        "localidade": normalizadores.normalizar_localidade(dados.get("localidade")),
        "quarteirao": _text(dados.get("quarteirao")),
        "endereco": _text(dados.get("endereco")),
        "latitude": _real(dados.get("latitude")),
        "longitude": _real(dados.get("longitude")),
        "sinan": _text(dados.get("sinan")),
        "status": status,
        "bloqueio": _normalizar_bloqueio_doente(dados.get("bloqueio")),
        "data_bloqueio": _date(dados.get("data_bloqueio")),
        "observacoes_entomologica": _text(dados.get("observacoes_entomologica")),
        "pedido_zoomed": _normalizar_sim_nao(dados.get("pedido_zoomed")),
    }


def _receita_payload(dados):
    return {
        "data_notificacao": _date(dados.get("data_notificacao")),
        "inicio_sintomas": _date(dados.get("inicio_sintomas")),
        "data_receita": _date(dados.get("data_receita")),
        "visita_va_veterinario": _date(dados.get("visita_va_veterinario")),
        "capsulas_total": _int(dados.get("capsulas_total")),
        "posologia": _text(dados.get("posologia")),
        "status": _normalizar_status_doente(dados.get("status")) if _text(dados.get("status")) else "",
        "observacoes": _text(dados.get("observacoes")),
    }


def _doente_chave(payload):
    partes = [
        payload.get("tutor") or "",
        payload.get("nome") or "",
        payload.get("telefone") or "",
        payload.get("endereco") or "",
    ]
    text = "|".join(_norm_col(p) for p in partes)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _salvar_status_doente(conn, nome):
    nome = _normalizar_status_doente(nome)
    if not nome:
        return
    if nome not in DOENTES_STATUS_PADRAO:
        nome = "Outro"
    conn.execute(
        f"""INSERT INTO {DOENTES_STATUS_TABLE}(nome, ativo, criado_em)
            VALUES (?,1,?)
            ON CONFLICT(nome) DO UPDATE SET ativo=1""",
        (nome, datetime.now().isoformat(timespec="seconds")),
    )


def _status_planilha(value):
    return _normalizar_status_doente(value)
    text = _text(value)
    if not text:
        return "Em tratamento"
    low = _sem_acentos(text).lower()
    if "faleceu" in low or "obito" in low:
        return "Faleceu"
    if "acabou" in low or "final" in low:
        return "Acabou tratamento"
    if "retirada" in low or "chegou" in low:
        return "Medicação disponível"
    return text.title() if text.isupper() or text.islower() else text


def _dias_desde(value):
    data = _date(value)
    if not data:
        return None
    try:
        return (datetime.now().date() - datetime.fromisoformat(data).date()).days
    except ValueError:
        return None


def _telefone(value):
    text = _text(value)
    if not text:
        return None
    digits = re.sub(r"\D+", "", text)
    if not digits:
        return None
    if len(digits) in (10, 11):
        digits = "55" + digits
    if len(digits) == 12 and digits.startswith("5541") and digits[4] != "9":
        pass
    return digits


def _real(value):
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _sem_acentos(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _rows(conn, sql, params):
    return [{k: (v or 0) if k not in {"nome", "mes", "grupo"} else v for k, v in dict(r).items()} for r in conn.execute(sql, params)]


def _where(filtros):
    clauses = ["1=1"]
    params = []
    if filtros.get("d_ini"):
        clauses.append("v.data >= ?")
        params.append(filtros["d_ini"])
    if filtros.get("d_fim"):
        clauses.append("v.data <= ?")
        params.append(filtros["d_fim"])
    localidade = filtros.get("localidade")
    if localidade:
        if isinstance(localidade, (list, tuple)):
            valores = [v for v in localidade if v]
            if valores:
                clauses.append(f"v.localidade IN ({','.join('?' * len(valores))})")
                params.extend(valores)
        else:
            clauses.append("v.localidade = ?")
            params.append(localidade)
    if filtros.get("visita"):
        clauses.append("v.visita = ?")
        params.append(filtros["visita"])
    agente = filtros.get("agente")
    if agente:
        if isinstance(agente, (list, tuple)):
            valores = [v for v in agente if v]
            if valores:
                clauses.append(
                    f"""EXISTS (
                        SELECT 1 FROM esporotricose_visita_agentes va
                        JOIN agentes ag ON ag.id_agente = va.id_agente
                        WHERE va.id_visita = v.id_visita AND ag.nome IN ({','.join('?' * len(valores))})
                    )"""
                )
                params.extend(valores)
        else:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM esporotricose_visita_agentes va
                    JOIN agentes ag ON ag.id_agente = va.id_agente
                    WHERE va.id_visita = v.id_visita AND ag.nome = ?
                )"""
            )
            params.append(agente)
    return "WHERE " + " AND ".join(clauses), params


def _where_visitas(filtros):
    where, params = _where(filtros)
    clauses = [where[6:]]
    busca = _text(filtros.get("busca"))
    if busca:
        like = f"%{busca.lower()}%"
        clauses.append(
            """(
                LOWER(COALESCE(v.localidade,'')) LIKE ?
                OR LOWER(COALESCE(v.logradouro,'')) LIKE ?
                OR LOWER(COALESCE(v.numero,'')) LIKE ?
                OR LOWER(COALESCE(v.morador,'')) LIKE ?
                OR LOWER(COALESCE(v.telefone,'')) LIKE ?
                OR LOWER(COALESCE(v.data,'')) LIKE ?
                OR LOWER(COALESCE(v.quarteirao,'')) LIKE ?
                OR LOWER(COALESCE(v.visita,'')) LIKE ?
            )"""
        )
        params.extend([like] * 8)
    return "WHERE " + " AND ".join(clauses), params


def _where_animais(filtros):
    where, params = _where(filtros)
    clauses = [where[6:]]
    busca = _text(filtros.get("busca"))
    if busca:
        like = f"%{busca.lower()}%"
        clauses.append(
            """(
                LOWER(COALESCE(v.localidade,'')) LIKE ?
                OR LOWER(COALESCE(v.logradouro,'')) LIKE ?
                OR LOWER(COALESCE(v.numero,'')) LIKE ?
                OR LOWER(COALESCE(v.morador,'')) LIKE ?
                OR LOWER(COALESCE(v.telefone,'')) LIKE ?
                OR LOWER(COALESCE(v.data,'')) LIKE ?
                OR LOWER(COALESCE(a.nome,'')) LIKE ?
                OR LOWER(COALESCE(a.raca,'')) LIKE ?
                OR LOWER(COALESCE(a.especie,'')) LIKE ?
            )"""
        )
        params.extend([like] * 9)
    if filtros.get("especie"):
        clauses.append("a.especie = ?")
        params.append(filtros["especie"])
    if filtros.get("feridas"):
        clauses.append("a.feridas = ?")
        params.append(filtros["feridas"])
    if filtros.get("vacinado"):
        clauses.append("a.vacinado = ?")
        params.append(filtros["vacinado"])
    if filtros.get("castrado"):
        clauses.append("a.castrado = ?")
        params.append(filtros["castrado"])
    if filtros.get("ambiente"):
        clauses.append("a.ambiente = ?")
        params.append(filtros["ambiente"])
    if filtros.get("motivo_atencao"):
        clauses.append(f"({MOTIVO_ATENCAO_SQL}) = ?")
        params.append(filtros["motivo_atencao"])
    if filtros.get("evolucao"):
        clauses.append("LOWER(COALESCE(a.evolucao_caso, '')) = LOWER(?)")
        params.append(filtros["evolucao"])
    if filtros.get("prioritarios"):
        clauses.append(f"({MOTIVO_ATENCAO_SQL}) <> ''")
    return "WHERE " + " AND ".join(clauses), params


def _inserir_visita(conn, visita, agora_iso):
    cur = conn.cursor()
    id_localidade = _obter_ou_criar_localidade(cur, visita.get("localidade"))
    cur.execute(
        """INSERT OR IGNORE INTO esporotricose_visitas (
            id_visita, kobo_uuid, kobo_id, data, hora_inicio, hora_fim, inicio_registro,
            fim_registro, agentes_texto, localidade, id_localidade, quarteirao, tipo_imovel,
            logradouro, numero, morador, visita, telefone, observacoes, deseja_cadastrar_animal,
            origem_estrutura, arquivo_origem, submission_time, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            visita["id_visita"], visita["kobo_uuid"], visita.get("kobo_id"), visita["data"],
            visita.get("hora_inicio"), visita.get("hora_fim"), visita.get("inicio_registro"),
            visita.get("fim_registro"), visita.get("agentes_texto"), visita.get("localidade"),
            id_localidade, visita.get("quarteirao"), visita.get("tipo_imovel"), visita.get("logradouro"),
            visita.get("numero"), visita.get("morador"), visita.get("visita"), visita.get("telefone"),
            visita.get("observacoes"), visita.get("deseja_cadastrar_animal"), visita.get("origem_estrutura"),
            visita.get("arquivo_origem"), visita.get("submission_time"), agora_iso,
        ),
    )
    return cur.rowcount > 0


def _inserir_agentes(conn, id_visita, agentes_texto):
    nomes = _split_agentes(conn, agentes_texto)
    count = 0
    cur = conn.cursor()
    for nome in nomes:
        id_agente = _obter_ou_criar_agente(cur, nome)
        cur.execute(
            "INSERT OR IGNORE INTO esporotricose_visita_agentes(id_visita, id_agente) VALUES (?,?)",
            (id_visita, id_agente),
        )
        count += cur.rowcount
    return count


def _inserir_animal(conn, animal, agora_iso):
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO esporotricose_animais (
            id_animal, id_visita, kobo_uuid, especie, outro_animal, nome, raca, sexo,
            ambiente, vacinado, castrado, feridas, regiao_ferida, atendimento_veterinario,
            data_atendimento, evolucao_caso, arquivo_origem, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            animal["id_animal"], animal["id_visita"], animal.get("kobo_uuid"),
            animal.get("especie"), animal.get("outro_animal"), animal.get("nome"),
            animal.get("raca"), animal.get("sexo"), animal.get("ambiente"), animal.get("vacinado"),
            animal.get("castrado"), animal.get("feridas"), animal.get("regiao_ferida"),
            animal.get("atendimento_veterinario"), animal.get("data_atendimento"),
            animal.get("evolucao_caso"), animal.get("arquivo_origem"), agora_iso,
        ),
    )
    return cur.rowcount > 0


def _obter_ou_criar_localidade(cur, nome):
    nome = normalizadores.normalizar_localidade(nome)
    if not nome:
        return None
    cur.execute("SELECT id_localidade FROM localidades WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)", (nome,))
    return cur.lastrowid


def _obter_ou_criar_agente(cur, nome):
    nome = _normalizar_agente_nome(nome)
    return agentes_db.obter_ou_criar(cur, nome)


def _split_agentes(conn, texto):
    texto = _text(texto)
    if not texto:
        return []
    texto = _normalizar_agentes_texto(texto)
    cur = conn.cursor()
    conhecidos = [r[0] for r in cur.execute("SELECT nome FROM agentes ORDER BY LENGTH(nome) DESC, nome")]
    restantes = texto
    nomes = []
    for nome in conhecidos:
        padrao = re.compile(rf"(^|\s){re.escape(nome)}(?=\s|$)", re.I)
        if padrao.search(restantes):
            nomes.append(nome)
            restantes = padrao.sub(" ", restantes).strip()
    for original, normalizado in AGENTE_COMPOSTO.items():
        if re.search(rf"(^|\s){re.escape(original)}(?=\s|$)", restantes, re.I) and normalizado not in nomes:
            nomes.append(normalizado)
            restantes = re.sub(rf"(^|\s){re.escape(original)}(?=\s|$)", " ", restantes, flags=re.I).strip()
    for parte in re.split(r"[,;/]|\s{2,}", restantes):
        parte = _normalizar_agente_nome(parte.strip())
        if parte and parte not in nomes:
            nomes.append(parte)
    return nomes


def _normalizar_agentes_texto(texto):
    normalizado = texto
    for original, correto in AGENTE_ALIASES.items():
        normalizado = re.sub(rf"(^|\s){re.escape(original)}(?=\s|$)", rf"\1{correto}", normalizado, flags=re.I)
    return normalizado


def _normalizar_agente_nome(nome):
    texto = _text(nome)
    if not texto:
        return None
    chave = _sem_acentos(texto).lower()
    chave = re.sub(r"[^a-z0-9_]+", " ", chave).strip()
    if texto.lower() in AGENTE_ALIASES:
        return AGENTE_ALIASES[texto.lower()]
    if chave in AGENTE_ALIASES:
        return AGENTE_ALIASES[chave]
    return texto


def _localidade(valor):
    texto = _text(valor)
    if not texto:
        return None
    return normalizadores.normalizar_localidade(texto)


def _choice(valor):
    texto = _text(valor)
    if not texto:
        return None
    return CHOICE_LABELS.get(texto.lower(), texto)


def _text(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    texto = str(valor).strip()
    if texto.lower() in {"nan", "nat", "none"}:
        return None
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto or None


def _int(valor):
    texto = _text(valor)
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except Exception:
        return None


def _date(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    try:
        return pd.to_datetime(valor).date().isoformat()
    except Exception:
        return None


def _time(valor):
    texto = _text(valor)
    if not texto:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", texto)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    try:
        parsed = pd.to_datetime(texto, errors="coerce")
        return None if pd.isna(parsed) else parsed.strftime("%H:%M")
    except Exception:
        return None


def _datetime(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(valor).isoformat()
    except Exception:
        return None


def _uuid(valor):
    texto = _text(valor)
    if texto and texto.startswith("uuid:"):
        return texto[5:]
    return texto


def _hash(prefix, value):
    return hashlib.md5(f"{prefix}:{value}".encode("utf-8")).hexdigest()


def _basename(path):
    return str(path).replace("\\", "/").split("/")[-1]
