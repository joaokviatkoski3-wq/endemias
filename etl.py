# =============================================================================
#  ETL — PROCESSAMENTO DE PLANILHAS KOBO
#  Setor de Endemias — Almirante Tamandaré/PR
#
#  Chamado pelo app.py via rota /processar.
#  Não tem interface gráfica — retorna lista de eventos de log.
# =============================================================================

import os, glob, json, shutil, hashlib, sqlite3, traceback
import pandas as pd
from datetime import datetime
from openpyxl.utils import column_index_from_string

from app_core import esporotricose as esporotricose_core
from app_core import work_types

# =============================================================================
#  LOGGER (lista de eventos para SSE)
# =============================================================================

class Logger:
    def __init__(self, callback=None):
        """callback(msg, tag) é chamado a cada linha de log (para SSE)."""
        self.callback = callback
        self.linhas   = []

    def log(self, texto, tag="normal"):
        self.linhas.append((texto, tag))
        if self.callback:
            self.callback(texto, tag)


# =============================================================================
#  CARREGAMENTO DE CONFIG
# =============================================================================

def carregar_config(base_dir):
    caminho = os.path.join(base_dir, "config.json")
    with open(caminho, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    errors = work_types.validate_config_work_types(cfg)
    if errors:
        raise ValueError("; ".join(errors))
    return cfg, cfg["tipos_trabalho"]


# =============================================================================
#  FUNÇÕES AUXILIARES
# =============================================================================

def identificar_tipo(nome_arquivo, tipos):
    base   = os.path.basename(nome_arquivo)
    prefix = base.split("_")[0].upper()
    return prefix if prefix in tipos else None


def gerar_id_visita(kobo_uuid, seq_val):
    chave = "visita:" + str(kobo_uuid) + ":" + (seq_val or "")
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


def gerar_id_coleta(kobo_uuid, num_tubo, index_coleta):
    chave = str(kobo_uuid) + str(num_tubo) + str(index_coleta)
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


def normalizar_data(valor):
    if valor is None: return None
    try:
        if pd.isna(valor): return None
    except Exception: pass
    if isinstance(valor, datetime): return valor.date().isoformat()
    try: return pd.to_datetime(valor).date().isoformat()
    except Exception: return None


def normalizar_hora(valor):
    if valor is None: return None
    try:
        if pd.isna(valor): return None
    except Exception: pass
    try:
        dt = pd.to_datetime(str(valor), errors="coerce")
        return None if pd.isna(dt) else dt.strftime("%H:%M")
    except Exception: return None


def val_int(val):
    try:
        v = int(float(str(val).replace(",", ".")))
        return v if v >= 0 else None
    except Exception: return None


def val_real(val):
    try: return float(str(val).replace(",", "."))
    except Exception: return None


def val_bool(val):
    if val is None: return None
    s = str(val).strip().lower()
    if s in ("sim", "yes", "1", "true", "s"): return 1
    if s in ("não", "nao", "no", "0", "false", "n"): return 0
    return None


def val_str(val):
    if val is None: return None
    try:
        if pd.isna(val): return None
    except Exception: pass
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


# =============================================================================
#  NORMALIZAÇÃO DE LOCALIDADE
# =============================================================================

MAPA_LOCALIDADE = {
    "centro": "Sede", "sede": "Sede",
    "cachoeira": "Cachoeira", "graziela": "Graziela",
    "lamenha": "Lamenha",
    "paraiso": "Paraíso", "paraíso": "Paraíso",
    "roma": "Roma", "rosana": "Rosana",
    "santa maria": "Santa Maria",
    "são francisco": "São Francisco", "sao francisco": "São Francisco",
    "são joão batista": "São João Batista", "sao joao batista": "São João Batista",
    "são venâncio": "São Venâncio", "sao venancio": "São Venâncio",
    "tamboara": "Tamboara",
    "tanguá": "Tanguá", "tangua": "Tanguá",
    "tranqueira": "Tranqueira",
    "capivara dos manfron": "Capivara dos Manfron",
}


def normalizar_localidade(nome):
    if not nome: return nome
    return MAPA_LOCALIDADE.get(nome.strip().lower(), nome.strip())


def obter_ou_criar_localidade(cur, nome_bruto):
    if not nome_bruto: return None
    nome = normalizar_localidade(nome_bruto)
    cur.execute("SELECT id_localidade FROM localidades WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row: return row[0]
    cur.execute("INSERT INTO localidades (nome, cod_localidade) VALUES (?,NULL)", (nome,))
    return cur.lastrowid


# =============================================================================
#  LEITURA DE PLANILHAS
# =============================================================================

def ler_planilha_trabalho(caminho, tipo, cfg_tipo):
    # FIX ETL-04: engine='openpyxl' explícito evita falhas silenciosas de encoding
    df_visitas = pd.read_excel(
        caminho, sheet_name=0, dtype=str, engine="openpyxl"
    ).dropna(how="all")

    if "_uuid" in df_visitas.columns:
        df_visitas["__uuid__"] = (
            df_visitas["_uuid"].astype(str).str.strip().str.removeprefix("uuid:")
        )
    else:
        col_idx = column_index_from_string(cfg_tipo["col_id_visita_letra"]) - 1
        df_visitas["__uuid__"] = (
            df_visitas.iloc[:, col_idx].astype(str).str.strip().str.removeprefix("uuid:")
        )

    try:
        df_coletas = pd.read_excel(
            caminho, sheet_name=1, dtype=str, engine="openpyxl"
        ).dropna(how="all")
        uuid_col = next(
            (c for c in df_coletas.columns
             if "uuid" in c.lower() and ("submission__uuid" in c.lower() or c.lower() == "_uuid")),
            None
        )
        if not uuid_col:
            uuid_col = next((c for c in df_coletas.columns if "uuid" in c.lower()), None)

        if uuid_col:
            df_coletas["__uuid__"] = (
                df_coletas[uuid_col].astype(str).str.strip().str.removeprefix("uuid:")
            )
        else:
            col_q = cfg_tipo["col_id_coletas_idx"]
            df_coletas["__uuid__"] = (
                df_coletas.iloc[:, col_q].astype(str).str.strip().str.removeprefix("uuid:")
            )
    except Exception:
        df_coletas = pd.DataFrame()

    return df_visitas, df_coletas




# =============================================================================
#  EXPANSÃO DE SEQUÊNCIAS
# =============================================================================

def expandir_sequencia(df_visitas, cfg_tipo, logger):
    col_seq = cfg_tipo.get("col_sequencia")
    if not col_seq or col_seq not in df_visitas.columns:
        return df_visitas

    col_seq_letra = cfg_tipo.get("col_sequencia_letra")
    cols_extra    = cfg_tipo.get("cols_duplicar_extra", [])
    todas_colunas = list(df_visitas.columns)

    if col_seq in todas_colunas:
        seq_idx = todas_colunas.index(col_seq)
    elif col_seq_letra:
        seq_idx = column_index_from_string(col_seq_letra) - 1
    else:
        return df_visitas

    cols_duplicar = set(todas_colunas[:seq_idx + 1])
    for c in cols_extra:
        if c in df_visitas.columns:
            cols_duplicar.add(c)
    cols_nulificar = [c for c in todas_colunas if c not in cols_duplicar and c != col_seq]

    novos, extras = [], 0

    for _, visita in df_visitas.iterrows():
        valor_seq = str(visita.get(col_seq, "") or "").strip()
        if not valor_seq or "," not in valor_seq:
            novo = dict(visita); novo["__eh_mae__"] = True; novos.append(novo); continue
        partes = [p.strip() for p in valor_seq.split(",") if p.strip()]
        if len(partes) <= 1 or any(len(p) > 20 for p in partes):
            novo = dict(visita); novo["__eh_mae__"] = True; novos.append(novo); continue
        # FIX ETL-06: limite de segurança para evitar explosão de linhas
        MAX_PARTES = 50
        if len(partes) > MAX_PARTES:
            logger.log(
                f"  [AVISO] Sequência com {len(partes)} partes excede o limite de {MAX_PARTES}. "
                f"Truncando.", "aviso"
            )
            partes = partes[:MAX_PARTES]
        extras += len(partes) - 1
        uuid_original = visita.get("__uuid__")
        for i, parte in enumerate(partes):
            novo = dict(visita)
            novo[col_seq]       = parte
            novo["__eh_mae__"]  = (i == 0)
            if i > 0:
                for c in cols_nulificar:
                    novo[c] = None
                novo["__uuid__"] = uuid_original
            novos.append(novo)

    if extras:
        logger.log(f"  Sequências expandidas: {extras} registro(s) adicional(is).", "ok")

    return pd.DataFrame(novos, columns=todas_colunas + ["__eh_mae__"])


# =============================================================================
#  EXTRAÇÃO DE DADOS
# =============================================================================

TIPOS_DEPOSITO = ["A1", "A2", "B", "C", "D1", "D2", "E"]


def extrair_agentes(row, cfg_tipo):
    pref = cfg_tipo["prefixo_agente"]
    return [
        col.replace(pref, "").strip()
        for col in row.index
        if col.startswith(pref) and val_str(row[col]) == "1"
    ]


def normalizar_tipo_tratamento(tipo):
    if not tipo: return tipo
    if "natular" in tipo.lower(): return "Natular DT"
    return tipo


def extrair_depositos(row, tipo):
    deps = []
    fields = work_types.etl_fields_for(tipo)
    if fields.get("tratamentos_em_depositos"):
        for dep in TIPOS_DEPOSITO:
            insp  = val_int(row.get(f"Inspecionado {dep}"))
            elim  = val_int(row.get(f"Eliminado {dep}"))
            trat  = val_int(row.get(f"Tratado {dep}"))
            t_tip = val_str(row.get(f"Tipo de tratamento {dep}"))
            carga = val_real(row.get(f"Quantidade de carga usada {dep}"))
            if any(v is not None for v in [insp, elim, trat]):
                deps.append({
                    "tipo_deposito": dep, "inspecionado": insp,
                    "eliminado": elim, "tratado": trat,
                    "tipo_tratamento": t_tip, "qtd_carga": carga,
                })
    else:
        col_elim = fields.get("depositos_eliminados_col", "Depósitos eliminados")
        elim_total = val_int(row.get(col_elim))

        for dep in TIPOS_DEPOSITO:
            insp = val_int(row.get(dep))
            if insp is not None and insp > 0:
                deps.append({
                    "tipo_deposito": dep,
                    "inspecionado": insp,
                    # eliminado_total fica no primeiro tipo como aproximação
                    # (limitação do formulário KoboToolbox — só registra total)
                    "eliminado": elim_total if dep == TIPOS_DEPOSITO[0] else None,
                    "tratado": None, "tipo_tratamento": None, "qtd_carga": None,
                })
    return deps


def extrair_tratamentos(row, tipo):
    fields = work_types.etl_fields_for(tipo)
    if fields.get("tratamentos_em_depositos"):
        return []  # tratamentos do TBO ficam nos depósitos

    col_houve = fields.get("tratamento_houve_col")
    houve = val_str(row.get(col_houve, "")) if col_houve else None
    if houve and houve.lower() in ("não", "nao", "no"):
        return []

    trats = []
    for tratamento in fields.get("tratamentos", ()):
        tipo_t = val_str(row.get(tratamento["tipo_col"]))
        carga = val_real(row.get(tratamento["carga_col"]))
        qtd_col = tratamento.get("qtd_depositos_col")
        qtd_d = val_int(row.get(qtd_col)) if qtd_col else None
        if tipo_t or carga:
            trats.append({
                "tipo": tipo_t,
                "quantidade_carga": carga,
                "qtd_depositos_tratados": qtd_d,
            })
    return trats


# =============================================================================
#  INSERÇÕES NO BANCO
# =============================================================================

def obter_ou_criar_agente(cur, nome):
    cur.execute("SELECT id_agente FROM agentes WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row: return row[0]
    cur.execute("INSERT INTO agentes(nome) VALUES (?)", (nome,))
    return cur.lastrowid


def inserir_visita(cur, id_visita, kobo_uuid, row, tipo, cfg_tipo, agora_iso):
    col_data      = cfg_tipo["col_data"]
    col_hora_letra = cfg_tipo.get("col_hora_inicio_letra")
    col_hora_fim   = cfg_tipo.get("col_hora_fim_letra")

    if col_hora_letra:
        idx = column_index_from_string(col_hora_letra) - 1
        hora_val = row.iloc[idx] if idx < len(row) else None
    else:
        nome_hora = work_types.etl_fields_for(tipo).get("hora_inicio_col")
        hora_val  = row.get(nome_hora) if nome_hora else None

    hora_fim_val = None
    if col_hora_fim:
        idx = column_index_from_string(col_hora_fim) - 1
        hora_fim_val = row.iloc[idx] if idx < len(row) else None

    col_seq = cfg_tipo.get("col_sequencia")
    loc_bruto = val_str(row.get(cfg_tipo["col_localidade"]))

    cur.execute("""
        INSERT OR IGNORE INTO visitas (
            id_visita, kobo_uuid, kobo_id, tipo, data,
            hora_inicio, hora_fim, ciclo, localidade, id_localidade, logradouro,
            numero, quarteirao, sequencia, morador, tipo_imovel,
            visita, lado, agua_sanepar, observacoes, submission_time, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        id_visita, val_str(kobo_uuid), val_int(row.get("_id")), tipo,
        normalizar_data(row.get(col_data)),
        normalizar_hora(hora_val), normalizar_hora(hora_fim_val),
        val_int(row.get("Ciclo") or row.get("ciclo")),
        loc_bruto,
        obter_ou_criar_localidade(cur, loc_bruto),
        val_str(row.get("Logradouro") or row.get("logradouro")),
        val_str(row.get("Número") or row.get("numero")),
        val_int(row.get("Quarteirão") or row.get("quarteirao")),
        val_str(row.get(col_seq)) if col_seq else None,
        val_str(row.get("Morador")),
        val_str(row.get("Tipo do imóvel") or row.get("Imóvel")),
        val_str(row.get("Visita") or row.get("visita")),
        val_str(row.get("Lado") or row.get("lado")),
        val_bool(row.get("O imóvel possui água encanada fornecida pela Sanepar?")),
        val_str(row.get("Observações") or row.get("observacoes")),
        val_str(row.get("_submission_time")),
        agora_iso,
    ))
    return cur.rowcount > 0


def inserir_foco_visita(cur, id_visita, positivos, visita_row, tipo, cfg_tipo, agora_iso):
    """
    Insere (ou atualiza) UM foco por visita, agrupando todos os tubos/depósitos positivos.

    positivos: lista de dicts com chaves id_resultado, id_coleta, num_tubo, tipo_deposito
    """
    import re as _re

    # Ordenar tubos numericamente para exibição consistente
    def _num(p):
        s = _re.sub(r"\D", "", p.get("num_tubo") or "")
        return int(s) if s else 0

    positivos_ord = sorted(positivos, key=_num)

    # Campos derivados dos tubos agrupados
    tubos_str = ", ".join(p["num_tubo"] for p in positivos_ord if p.get("num_tubo"))
    deps_partes = []
    for p in positivos_ord:
        dep = p.get("tipo_deposito") or ""
        tub = p.get("num_tubo") or ""
        if dep and tub:
            deps_partes.append(f"{dep} (tubo {tub})")
        elif dep:
            deps_partes.append(dep)
        elif tub:
            deps_partes.append(f"tubo {tub}")
    deps_str = ", ".join(deps_partes) if deps_partes else None

    # código legível: YYYYMMDD + número do primeiro tubo
    data_bruta  = val_str(visita_row.get(cfg_tipo.get("col_data", "Data")))
    data_clean  = (normalizar_data(data_bruta) or "").replace("-", "")
    primeiro_num = _re.sub(r"\D", "", positivos_ord[0].get("num_tubo") or "") if positivos_ord else ""
    codigo = data_clean + primeiro_num if data_clean and primeiro_num else None

    # id_foco estável por visita (v3: um por visita)
    id_foco = hashlib.md5(("foco:v3:" + id_visita).encode()).hexdigest()

    col_loc   = cfg_tipo.get("col_localidade")
    loc_bruto = val_str(visita_row.get(col_loc)) if col_loc else None

    cur.execute("""
        SELECT GROUP_CONCAT(a.nome, ' / ')
        FROM visita_agentes va JOIN agentes a ON a.id_agente=va.id_agente
        WHERE va.id_visita=?
    """, (id_visita,))
    agentes_str = (cur.fetchone() or [None])[0]

    # Referências ao primeiro resultado/coleta (para FK; os demais ficam em num_tubo/depositos)
    id_coleta_ref   = positivos_ord[0]["id_coleta"]
    id_resultado_ref = positivos_ord[0]["id_resultado"]

    obs = val_str(visita_row.get("Observações") or visita_row.get("observacoes"))

    # Se o foco já existe (reprocessamento): atualiza tubos/depósitos/código, mantém status manual
    cur.execute("SELECT id_foco FROM focos_positivos WHERE id_foco=?", (id_foco,))
    ja_existe = cur.fetchone() is not None

    if ja_existe:
        cur.execute("""
            UPDATE focos_positivos SET
                num_tubo=?, depositos=?, codigo=?, observacoes=?, agentes=?, processado_em=?
            WHERE id_foco=?
        """, (tubos_str, deps_str, codigo, obs, agentes_str, agora_iso, id_foco))
    else:
        cur.execute("""
            INSERT INTO focos_positivos (
                id_foco, id_visita, id_coleta, id_resultado, num_tubo, codigo,
                origem, tipo_trabalho, data, id_localidade, localidade,
                quarteirao, logradouro, numero, complemento,
                nome_morador, tipo_imovel, depositos, agentes,
                observacoes, gera_notificacao, processado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            id_foco, id_visita, id_coleta_ref, id_resultado_ref, tubos_str, codigo,
            "kobo", tipo,
            normalizar_data(data_bruta),
            obter_ou_criar_localidade(cur, loc_bruto),
            normalizar_localidade(loc_bruto) if loc_bruto else None,
            val_int(visita_row.get(cfg_tipo.get("col_quarteirao", "Quarteirão"))),
            val_str(visita_row.get(cfg_tipo.get("col_logradouro", "Logradouro"))),
            val_str(visita_row.get(cfg_tipo.get("col_numero", "Número"))),
            None,
            val_str(visita_row.get("Morador")),
            val_str(visita_row.get("Tipo do imóvel") or visita_row.get("Imóvel")),
            deps_str, agentes_str, obs,
            work_types.gera_notificacao_padrao(tipo),
            agora_iso,
        ))


# =============================================================================
#  PROCESSAMENTO DE UM ARQUIVO
# =============================================================================

def processar_arquivo(caminho, tipo, cfg_tipo, cfg_larvas, larvas, conn, logger, agora_iso, dry_run=False):
    df_visitas, df_coletas = ler_planilha_trabalho(caminho, tipo, cfg_tipo)
    logger.log(f"  Visitas: {len(df_visitas)} | Coletas: {len(df_coletas)}")

    col_data = cfg_tipo["col_data"]
    if col_data not in df_visitas.columns:
        logger.log(f"  [ERRO] Coluna de data '{col_data}' não encontrada. Verifique config.json.", "erro")
        return False

    df_visitas = expandir_sequencia(df_visitas, cfg_tipo, logger)

    coletas_por_uuid = {}
    for _, row in df_coletas.iterrows():
        uuid = str(row.get("__uuid__", "")).strip()
        coletas_por_uuid.setdefault(uuid, []).append(row)

    cur = conn.cursor()
    col_tubo = cfg_tipo["col_numero_tubo_coletas"]

    visitas_novas = coletas_novas = resultados_novos = 0
    tubos_sem_resultado = []

    # ── Transação única por arquivo ──────────────────────────────────────────
    for _, visita in df_visitas.iterrows():
        kobo_uuid = str(visita.get("__uuid__", "") or "").strip()
        if not kobo_uuid or kobo_uuid.lower() in ("nan", "none", ""):
            continue

        col_seq = cfg_tipo.get("col_sequencia")
        seq_val = val_str(visita.get(col_seq)) if col_seq else None
        id_visita = gerar_id_visita(kobo_uuid, seq_val)

        if inserir_visita(cur, id_visita, kobo_uuid, visita, tipo, cfg_tipo, agora_iso):
            visitas_novas += 1

        # Agentes
        for nome in extrair_agentes(visita, cfg_tipo):
            if nome:
                id_ag = obter_ou_criar_agente(cur, nome)
                cur.execute(
                    "INSERT OR IGNORE INTO visita_agentes(id_visita,id_agente) VALUES(?,?)",
                    (id_visita, id_ag)
                )

        eh_mae = visita.get("__eh_mae__", seq_val is None or seq_val == "1")
        if eh_mae:
            for d in extrair_depositos(visita, tipo):
                cur.execute("""
                    INSERT OR IGNORE INTO depositos_inspecionados
                        (id_visita,tipo_deposito,inspecionado,eliminado,tratado,tipo_tratamento,qtd_carga)
                    VALUES (?,?,?,?,?,?,?)
                """, (id_visita, d["tipo_deposito"], d["inspecionado"], d["eliminado"],
                      d["tratado"], normalizar_tipo_tratamento(d["tipo_tratamento"]), d["qtd_carga"]))

            for t in extrair_tratamentos(visita, tipo):
                # FIX DB-03: INSERT OR IGNORE — UNIQUE(id_visita, tipo) no schema previne duplicatas
                cur.execute("""
                    INSERT OR IGNORE INTO tratamentos (id_visita,tipo,quantidade_carga,qtd_depositos_tratados)
                    VALUES (?,?,?,?)
                """, (id_visita, normalizar_tipo_tratamento(t["tipo"]),
                      t["quantidade_carga"], t["qtd_depositos_tratados"]))

            data_visita = normalizar_data(visita.get(col_data))
            positivos_visita = []  # acumula coletas positivas desta visita

            for i, coleta in enumerate(coletas_por_uuid.get(kobo_uuid, [])):
                num_tubo  = val_str(coleta.get(col_tubo)) or ""
                id_coleta = gerar_id_coleta(kobo_uuid, num_tubo, i)
                tipo_dep  = val_str(coleta.get(cfg_tipo.get("col_nome_deposito_coletas", "Depósito")))
                cur.execute("""
                    INSERT OR IGNORE INTO coletas
                        (id_coleta,id_visita,num_tubo,codigo_deposito,tipo_deposito,deposito_eliminado)
                    VALUES (?,?,?,?,?,?)
                """, (
                    id_coleta, id_visita, val_str(coleta.get(col_tubo)),
                    val_str(coleta.get(cfg_tipo.get("col_codigo_deposito_coletas", "Código do depósito"))),
                    tipo_dep,
                    val_bool(coleta.get(cfg_tipo.get("col_deposito_eliminado_coletas",
                                                      "O Depósito onde foi feita a coleta foi eliminado?"))),
                ))
                coletas_novas += 1

                row_larva = larvas.get((num_tubo, data_visita))
                if row_larva is not None:
                    def get_lab(nome):
                        v = row_larva.get("[LAB] " + nome, row_larva.get(nome))
                        return val_int(v) or 0

                    cur.execute("""
                        INSERT OR IGNORE INTO resultados_laboratorio (
                            id_coleta, num_tubo, data_coleta, laboratorista, data_leitura,
                            aegypt_larvas, aegypt_pupas, aegypt_exuvias, aegypt_adulto,
                            albopictus_larvas, albopictus_pupas, albopictus_exuvias, albopictus_adulto,
                            outra_larvas, outra_pupas, outra_exuvias, outra_adulto, kobo_uuid
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        id_coleta, val_str(row_larva.get("Número do tubito")),
                        normalizar_data(row_larva.get("Data da coleta")),
                        val_str(row_larva.get("Nome do laboratorista")),
                        normalizar_data(row_larva.get("Data da leitura")),
                        get_lab("Aegypt Larvas"), get_lab("Aegypt Pupas"),
                        get_lab("Aegypt Exúvias"), get_lab("Aegypt Adulto"),
                        get_lab("Albopictus Larvas"), get_lab("Albopictus Pupas"),
                        get_lab("Albopictus Exúvias"), get_lab("Albopictus Adulto"),
                        get_lab("Outra Espécie Larvas"), get_lab("Outra Espécie Pupas"),
                        get_lab("Outra Espécie Exúvias"), get_lab("Outra Espécie Adulto"),
                        val_str(row_larva.get("_uuid")),
                    ))
                    resultados_novos += 1

                    # Verificar se é positivo para aegypti
                    cur.execute("""
                        SELECT id_resultado, aegypt_larvas+aegypt_pupas+aegypt_exuvias+aegypt_adulto as total
                        FROM resultados_laboratorio WHERE id_coleta=? ORDER BY id_resultado DESC LIMIT 1
                    """, (id_coleta,))
                    res_row = cur.fetchone()
                    if res_row and (res_row[1] or 0) > 0:
                        positivos_visita.append({
                            "id_resultado": res_row[0],
                            "id_coleta":    id_coleta,
                            "num_tubo":     num_tubo,
                            "tipo_deposito": tipo_dep,
                        })
                elif num_tubo:
                    tubos_sem_resultado.append(num_tubo)

            # Um foco por visita, agrupando todos os tubos positivos
            if positivos_visita:
                inserir_foco_visita(cur, id_visita, positivos_visita,
                                    visita, tipo, cfg_tipo, agora_iso)

    if not dry_run:
        pass  # commit é feito pelo chamador (processar_upload), em transação única

    logger.log(
        f"  Visitas inseridas: {visitas_novas} | Coletas: {coletas_novas} | Resultados: {resultados_novos}",
        "ok"
    )
    if tubos_sem_resultado:
        logger.log(
            "  [AVISO] Tubos sem resultado de laboratório: " + ", ".join(set(tubos_sem_resultado)),
            "aviso"
        )
    # FIX ETL-02: retornar dict com contadores reais para o sumário do dry-run
    return {
        "ok": True,
        "visitas_novas": visitas_novas,
        "coletas_novas": coletas_novas,
        "resultados_novos": resultados_novos,
    }


# =============================================================================
#  ENTRY POINT — chamado pelo app.py
# =============================================================================

def processar_upload(arquivos_trabalho, arquivos_larvas, banco_path, config_path, logger, dry_run=False):
    """
    arquivos_trabalho: lista de caminhos de arquivos .xlsx com prefixos em config.json
    arquivos_larvas:   lista de caminhos de arquivos .xlsx (LARVAS_)
    banco_path:        caminho do endemias.db
    config_path:       caminho do config.json
    logger:            instância de Logger
    """
    agora     = datetime.now()
    agora_iso = agora.isoformat()

    logger.log("=" * 54, "titulo")
    logger.log("  PROCESSAMENTO DE PLANILHAS", "titulo")
    logger.log(f"  {agora.strftime('%d/%m/%Y %H:%M')}", "titulo")
    logger.log("=" * 54, "titulo")

    # Carregar config
    try:
        base_dir = os.path.dirname(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        validation_errors = work_types.validate_config_work_types(cfg)
        if validation_errors:
            raise ValueError("; ".join(validation_errors))
        TIPOS      = cfg["tipos_trabalho"]
        cfg_larvas = cfg["larvas"]
        logger.log(f"\nConfig carregada: {len(TIPOS)} tipo(s) de trabalho.", "ok")
    except Exception as e:
        logger.log(f"\n[ERRO] Falha ao carregar config.json: {e}", "erro")
        return False, []

    # Backup automático do banco
    logger.log("\n[1/4] Backup do banco...", "titulo")
    try:
        ts      = agora.strftime("%Y%m%d_%H%M%S")
        bk_dir  = os.path.join(os.path.dirname(banco_path), "backups")
        os.makedirs(bk_dir, exist_ok=True)
        bk_path = os.path.join(bk_dir, f"endemias_{ts}.db")
        shutil.copy2(banco_path, bk_path)
        logger.log(f"  Backup criado: backups/endemias_{ts}.db", "ok")
        # FIX ARQ-06: manter apenas os 10 backups mais recentes para não encher o disco
        todos_bk = sorted(glob.glob(os.path.join(bk_dir, "endemias_*.db")))
        for antigo in todos_bk[:-10]:
            try:
                os.remove(antigo)
                logger.log(f"  Backup antigo removido: {os.path.basename(antigo)}", "ok")
            except Exception:
                pass
    except Exception as e:
        logger.log(f"  [AVISO] Não foi possível criar backup: {e}", "aviso")

    # Carregar larvas
    logger.log("\n[2/4] Carregando resultados de larvas...", "titulo")
    larvas = {}
    for caminho in arquivos_larvas:
        try:
            df = pd.read_excel(
                caminho,
                dtype={cfg_larvas["col_numero_tubo"]: str},
                engine="openpyxl"  # FIX ETL-04
            ).dropna(how="all")
            for _, row in df.iterrows():
                tubo = str(row.get(cfg_larvas["col_numero_tubo"], "")).strip()
                data = normalizar_data(row.get(cfg_larvas["col_data_coleta"]))
                if tubo and data:
                    larvas[(tubo, data)] = row
            logger.log(f"  '{os.path.basename(caminho)}' — {len(larvas)} registro(s).", "ok")
        except Exception as e:
            logger.log(f"  [ERRO] '{os.path.basename(caminho)}': {e}", "erro")

    # Processar planilhas de trabalho
    logger.log("\n[3/4] Processando planilhas...", "titulo")
    if not arquivos_trabalho:
        logger.log("  [AVISO] Nenhuma planilha de trabalho enviada.", "aviso")

    conn = sqlite3.connect(banco_path)
    conn.execute("PRAGMA foreign_keys = ON")   # FIX DB-01: FK ativas em toda a sessão ETL
    conn.execute("PRAGMA journal_mode = WAL")  # FIX DB-04: consistência com app.py

    houve_erro = False
    sumario = []  # preview para tela de confirmação
    esporotricose_core.ensure_schema(conn)

    # FIX ETL-01: UMA transação para todos os arquivos — garante atomicidade total
    conn.execute("BEGIN")

    for caminho in arquivos_trabalho:
        nome = os.path.basename(caminho)
        tipo = identificar_tipo(nome, TIPOS)
        if nome.upper().startswith("ESPOROTRICOSE"):
            tipo = "ESPOROTRICOSE"
        if tipo is None:
            logger.log(f"\n  [IGNORADO] '{nome}' — prefixo não reconhecido.", "aviso")
            continue
        logger.log(f"\n  → {nome} ({tipo})")
        try:
            # FIX ETL-02: processar_arquivo agora retorna contadores reais de inserção
            if tipo == "ESPOROTRICOSE":
                resultado = esporotricose_core.processar_arquivo(
                    caminho, conn, logger, agora_iso, dry_run=dry_run, aceitar_legado=False
                )
            else:
                resultado = processar_arquivo(caminho, tipo, TIPOS[tipo], cfg_larvas, larvas, conn, logger, agora_iso, dry_run=dry_run)
            if isinstance(resultado, dict):
                ok = resultado.get("ok", False)
                if ok:
                    sumario.append({
                        "arquivo": nome,
                        "tipo": tipo,
                        "visitas_novas": resultado.get("visitas_novas", 0),
                        "coletas_novas": resultado.get("coletas_novas", 0),
                        "animais_novos": resultado.get("animais_novos", 0),
                        "resultados_novos": resultado.get("resultados_novos", 0),
                    })
            else:
                ok = bool(resultado)
            if not ok:
                houve_erro = True
        except Exception as e:
            logger.log(f"  [ERRO] {nome}: {e}", "erro")
            logger.log(traceback.format_exc(), "erro")
            houve_erro = True

    # Verificar banco dentro da transação (mostra contagens reais mesmo no dry-run)
    logger.log("\n[4/4] Verificando banco...", "titulo")
    cur = conn.cursor()
    for tabela in ["visitas", "visita_agentes", "depositos_inspecionados",
                   "tratamentos", "coletas", "resultados_laboratorio", "focos_positivos",
                   "esporotricose_visitas", "esporotricose_animais"]:
        cur.execute(f'SELECT COUNT(*) FROM "{tabela}"')
        qtd = cur.fetchone()[0]
        logger.log(f"  {tabela:<35} {qtd} registro(s)", "ok")

    # FIX ETL-01: commit ou rollback único — nunca ficam dados parciais
    if dry_run or houve_erro:
        conn.execute("ROLLBACK")  # descarta tudo — banco fica intocado
        if dry_run:
            logger.log("\n[DRY-RUN] Simulação concluída. Banco não foi alterado.", "aviso")
        else:
            logger.log("\n[ATENÇÃO] Erros detectados. Rollback executado — banco não alterado.", "erro")
    else:
        conn.execute("COMMIT")
        logger.log("\n✓ Dados gravados com sucesso.", "ok")

    conn.close()

    if houve_erro:
        logger.log("\n[ATENÇÃO] Um ou mais arquivos tiveram erros.", "aviso")
    else:
        logger.log("\n✓ Processamento concluído sem erros.", "ok")

    if not dry_run and not houve_erro:
        # ── Gerar consolidados Excel após commit real ──────────────────────
        logger.log("\n[5/5] Gerando consolidados Excel...", "titulo")
        try:
            from gerar_consolidado import gerar_todos
            gerar_todos(logger=logger)
        except Exception as e:
            logger.log(f"  [ERRO] Consolidados: {e}", "erro")

        logger.log("\n" + "=" * 54, "titulo")
        logger.log("  CONCLUÍDO", "titulo")
        logger.log("=" * 54, "titulo")

    return (not houve_erro), sumario
