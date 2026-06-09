# =============================================================================
#  CRIAR BANCO DE DADOS — SISTEMA DE ENDEMIAS  v3
#  Setor de Endemias — Almirante Tamandaré/PR
#
#  Execute UMA VEZ para criar o endemias.db.
#  Se o banco já existir, verifica a estrutura e não apaga dados.
#
#  Cria também o usuário admin inicial (troque a senha no primeiro acesso).
#  Uso: python criar_banco.py
# =============================================================================

import sqlite3, os
from datetime import datetime

from app_core import auth as auth_core
from app_core import pontos_estrategicos as pe_core

BANCO = "endemias.db"

SQL = """
PRAGMA foreign_keys = ON;

-- ── USUÁRIOS ──────────────────────────────────────────────────────────────────
-- Níveis: admin (tudo) | operador (ver + editar focos) | visualizador (só ler)
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT    NOT NULL UNIQUE,
    nome        TEXT    NOT NULL,
    senha_hash  TEXT    NOT NULL,
    nivel       TEXT    NOT NULL DEFAULT 'visualizador'
                        CHECK(nivel IN ('admin','operador','visualizador')),
    ativo       INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
    criado_em   TEXT    NOT NULL
);

-- ── LOCALIDADES ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS localidades (
    id_localidade  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           TEXT    NOT NULL UNIQUE,
    cod_localidade INTEGER
);

-- ── AGENTES ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agentes (
    id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT    NOT NULL UNIQUE,
    matricula TEXT,
    cargo     TEXT,
    ativo     INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
    data_inicio TEXT,
    data_saida  TEXT,
    observacoes TEXT
);

-- ── VISITAS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS visitas (
    id_visita       TEXT    PRIMARY KEY,
    kobo_uuid       TEXT    NOT NULL,
    kobo_id         INTEGER,
    tipo            TEXT    NOT NULL CHECK(tipo IN ('PE','TB','TBO','PVE')),
    data            DATE    NOT NULL,
    hora_inicio     TIME,
    hora_fim        TIME,
    ciclo           INTEGER,
    localidade      TEXT,
    id_localidade   INTEGER REFERENCES localidades(id_localidade),
    logradouro      TEXT,
    numero          TEXT,
    quarteirao      INTEGER,
    sequencia       TEXT,
    morador         TEXT,
    tipo_imovel     TEXT,
    visita          TEXT,
    lado            TEXT,
    agua_sanepar    INTEGER CHECK(agua_sanepar IN (0,1)),
    observacoes     TEXT,
    submission_time TEXT,
    processado_em   TEXT    NOT NULL,
    -- DB-06: colunas adicionadas por migração posterior (existem no banco real)
    -- SISPNCD: codigo de registro no SisPNCD
    -- Preenchido via formulário KoboToolbox quando disponível; NULL para registros anteriores
    SISPNCD         VARCHAR(20),
    -- CONTAOVOS_STATUS: controle do status do formulário de contagem de ovos
    -- 0 = pendente, 1 = preenchido, NULL = não aplicável (tipo diferente de TBO)
    CONTAOVOS_STATUS INTEGER CHECK(CONTAOVOS_STATUS IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_visitas_data       ON visitas(data);
CREATE INDEX IF NOT EXISTS idx_visitas_tipo       ON visitas(tipo);
CREATE INDEX IF NOT EXISTS idx_visitas_localidade ON visitas(id_localidade);
CREATE INDEX IF NOT EXISTS idx_visitas_quarteirao ON visitas(quarteirao);
CREATE INDEX IF NOT EXISTS idx_visitas_kobo_uuid  ON visitas(kobo_uuid);

-- ── VISITA_AGENTES ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS visita_agentes (
    id_visita TEXT    NOT NULL REFERENCES visitas(id_visita),
    id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
    PRIMARY KEY (id_visita, id_agente)
);
CREATE INDEX IF NOT EXISTS idx_va_agente ON visita_agentes(id_agente);

-- ── DEPOSITOS_INSPECIONADOS ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS depositos_inspecionados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_visita       TEXT    NOT NULL REFERENCES visitas(id_visita),
    tipo_deposito   TEXT    NOT NULL CHECK(tipo_deposito IN ('A1','A2','B','C','D1','D2','E')),
    inspecionado    INTEGER,
    eliminado       INTEGER,
    tratado         INTEGER,
    tipo_tratamento TEXT,
    qtd_carga       REAL,
    UNIQUE(id_visita, tipo_deposito)
);
CREATE INDEX IF NOT EXISTS idx_dep_visita ON depositos_inspecionados(id_visita);

-- ── TRATAMENTOS ───────────────────────────────────────────────────────────────
-- FIX DB-03: UNIQUE(id_visita, tipo) previne duplicatas em reprocessamento de planilhas
CREATE TABLE IF NOT EXISTS tratamentos (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_visita              TEXT    NOT NULL REFERENCES visitas(id_visita),
    tipo                   TEXT,
    quantidade_carga       REAL,
    qtd_depositos_tratados INTEGER,
    UNIQUE(id_visita, tipo)
);
CREATE INDEX IF NOT EXISTS idx_trat_visita ON tratamentos(id_visita);

-- ── COLETAS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coletas (
    id_coleta          TEXT    PRIMARY KEY,
    id_visita          TEXT    NOT NULL REFERENCES visitas(id_visita),
    num_tubo           TEXT,
    codigo_deposito    TEXT,
    tipo_deposito      TEXT,
    deposito_eliminado INTEGER CHECK(deposito_eliminado IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_col_visita ON coletas(id_visita);
CREATE INDEX IF NOT EXISTS idx_col_tubo   ON coletas(num_tubo);

-- ── RESULTADOS_LABORATORIO ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resultados_laboratorio (
    id_resultado       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_coleta          TEXT    NOT NULL UNIQUE REFERENCES coletas(id_coleta),
    num_tubo           TEXT    NOT NULL,
    data_coleta        DATE    NOT NULL,
    laboratorista      TEXT,
    data_leitura       DATE,
    aegypt_larvas      INTEGER DEFAULT 0,
    aegypt_pupas       INTEGER DEFAULT 0,
    aegypt_exuvias     INTEGER DEFAULT 0,
    aegypt_adulto      INTEGER DEFAULT 0,
    albopictus_larvas  INTEGER DEFAULT 0,
    albopictus_pupas   INTEGER DEFAULT 0,
    albopictus_exuvias INTEGER DEFAULT 0,
    albopictus_adulto  INTEGER DEFAULT 0,
    outra_larvas       INTEGER DEFAULT 0,
    outra_pupas        INTEGER DEFAULT 0,
    outra_exuvias      INTEGER DEFAULT 0,
    outra_adulto       INTEGER DEFAULT 0,
    kobo_uuid          TEXT    UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_lab_tubo_data ON resultados_laboratorio(num_tubo, data_coleta);

-- ── FOCOS_POSITIVOS ───────────────────────────────────────────────────────────
-- Gerado automaticamente quando há resultado positivo para Aedes aegypti.
-- PE nunca gera notificação (gera_notificacao = 0).
CREATE TABLE IF NOT EXISTS focos_positivos (
    id_foco            TEXT    PRIMARY KEY,
    id_visita          TEXT    REFERENCES visitas(id_visita),
    id_coleta          TEXT    REFERENCES coletas(id_coleta),
    id_resultado       INTEGER REFERENCES resultados_laboratorio(id_resultado),
    num_tubo           TEXT,   -- todos os tubos positivos, separados por vírgula
    codigo             TEXT,   -- ID legível: YYYYMMDD + número do primeiro tubo (ex: 20250508750)
    origem             TEXT    DEFAULT 'kobo',
    tipo_trabalho      TEXT,
    data               TEXT,
    id_localidade      INTEGER REFERENCES localidades(id_localidade),
    localidade         TEXT,
    quarteirao         INTEGER,
    logradouro         TEXT,
    numero             TEXT,
    complemento        TEXT,
    nome_morador       TEXT,
    tipo_imovel        TEXT,
    depositos          TEXT,
    agentes            TEXT,
    gera_notificacao   INTEGER DEFAULT 1 CHECK(gera_notificacao IN (0,1)),
    status_notificacao TEXT    DEFAULT 'pendente',
    tentativa_1        TEXT,
    tentativa_2        TEXT,
    tentativa_3        TEXT,
    data_entrega       TEXT,
    observacoes        TEXT,
    processado_em      TEXT
);
-- ── FOCOS_HISTORICO ──────────────────────────────────────────────────────────
-- Registro imutável de cada alteração feita em focos_positivos.
CREATE TABLE IF NOT EXISTS focos_historico (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_foco     TEXT    NOT NULL,
    campo       TEXT    NOT NULL,
    valor_ant   TEXT,
    valor_novo  TEXT,
    usuario     TEXT,
    alterado_em TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_foco ON focos_historico(id_foco);
CREATE INDEX IF NOT EXISTS idx_hist_em   ON focos_historico(alterado_em);

-- ── AGENDA_EVENTOS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agenda_eventos (
    id_evento    INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo       TEXT    NOT NULL,
    descricao    TEXT,
    tipo         TEXT    NOT NULL DEFAULT 'outro'
                 CHECK(tipo IN ('reuniao','planejamento','campo','prazo','treinamento','tarefa','ferias','outro')),
    data_inicio  TEXT    NOT NULL,
    data_fim     TEXT,
    dia_inteiro  INTEGER NOT NULL DEFAULT 0 CHECK(dia_inteiro IN (0,1)),
    lembrete_min INTEGER DEFAULT 60,
    cor          TEXT    DEFAULT '#1a4fba',
    criado_por   TEXT,
    criado_em    TEXT    NOT NULL,
    recorrencia  TEXT    NOT NULL DEFAULT 'nenhuma',
    recorrencia_fim TEXT
);
CREATE INDEX IF NOT EXISTS idx_agenda_inicio ON agenda_eventos(data_inicio);
CREATE INDEX IF NOT EXISTS idx_agenda_recorrencia ON agenda_eventos(recorrencia, recorrencia_fim);

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
CREATE INDEX IF NOT EXISTS idx_esporo_visitas_data ON esporotricose_visitas(data);
CREATE INDEX IF NOT EXISTS idx_esporo_visitas_localidade ON esporotricose_visitas(id_localidade);
CREATE INDEX IF NOT EXISTS idx_esporo_visitas_quarteirao ON esporotricose_visitas(quarteirao);
CREATE INDEX IF NOT EXISTS idx_esporo_visitas_kobo_uuid ON esporotricose_visitas(kobo_uuid);

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
CREATE INDEX IF NOT EXISTS idx_esporo_animais_visita ON esporotricose_animais(id_visita);
CREATE INDEX IF NOT EXISTS idx_esporo_animais_especie ON esporotricose_animais(especie);

CREATE TABLE IF NOT EXISTS importacoes (
    id_importacao INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT    NOT NULL UNIQUE,
    usuario       TEXT,
    arquivos_json TEXT    NOT NULL DEFAULT '[]',
    status        TEXT    NOT NULL DEFAULT 'upload',
    dry_run_ok    INTEGER,
    commit_ok     INTEGER,
    sumario_json  TEXT,
    erro          TEXT,
    criado_em     TEXT    NOT NULL,
    atualizado_em TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_importacoes_criado
    ON importacoes(criado_em);
CREATE INDEX IF NOT EXISTS idx_importacoes_status
    ON importacoes(status);

-- FIX DB-05: Índices compostos para queries mais frequentes
-- context_processor usa esse índice em toda requisição
CREATE INDEX IF NOT EXISTS idx_foco_notif
    ON focos_positivos(gera_notificacao, status_notificacao);
-- Filtro de data+tipo é muito comum nas rotas de dashboard e visitas
CREATE INDEX IF NOT EXISTS idx_visitas_data_tipo
    ON visitas(data, tipo);
-- Filtro por localidade nos focos positivos
CREATE INDEX IF NOT EXISTS idx_foco_localidade
    ON focos_positivos(id_localidade);
"""

TABELAS_ESPERADAS = [
    "usuarios", "localidades", "agentes", "visitas", "visita_agentes",
    "depositos_inspecionados", "tratamentos", "coletas",
    "resultados_laboratorio", "focos_positivos", "agenda_eventos",
    "importacoes", "pontos_estrategicos",
]


def _hash_senha(senha):
    return auth_core.hash_senha(senha)


def main():
    banco_existe = os.path.exists(BANCO)
    print("=" * 54)
    print("  CRIADOR DE BANCO — SISTEMA DE ENDEMIAS  v3")
    print("  %s" % datetime.now().strftime("%d/%m/%Y %H:%M"))
    print("=" * 54)

    if banco_existe:
        print(f"\n[INFO] Banco '{BANCO}' já existe. Verificando/atualizando...")
    else:
        print(f"\n[INFO] Banco '{BANCO}' não encontrado. Criando...")

    conn = sqlite3.connect(BANCO)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SQL)
    pe_core.ensure_schema(conn)
    conn.commit()

    # Migração: adicionar coluna 'codigo' se banco já existia sem ela
    try:
        conn.execute("ALTER TABLE focos_positivos ADD COLUMN codigo TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_foco_codigo ON focos_positivos(codigo)")
        conn.commit()
        print("[OK] Coluna 'codigo' adicionada à tabela focos_positivos.")
    except Exception:
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_foco_codigo ON focos_positivos(codigo)")
            conn.commit()
        except Exception:
            pass

    # Migração: criar focos_historico se não existir
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS focos_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_foco TEXT NOT NULL,
            campo TEXT NOT NULL, valor_ant TEXT, valor_novo TEXT,
            usuario TEXT, alterado_em TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_foco ON focos_historico(id_foco)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_em ON focos_historico(alterado_em)")
        conn.commit()
        print("[OK] Tabela 'focos_historico' verificada.")
    except Exception:
        pass

    # Verificar tabelas
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tabelas = {r[0] for r in cur.fetchall()}
    ausentes = [t for t in TABELAS_ESPERADAS if t not in tabelas]
    if ausentes:
        print(f"\n[ERRO] Tabelas ausentes: {ausentes}")
        conn.close(); return

    print("\n[OK] Tabelas:")
    for t in TABELAS_ESPERADAS:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        print(f"  [OK] {t:<30} {cur.fetchone()[0]} registro(s)")

    # Criar admin inicial se não existir nenhum usuário
    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        import secrets as _sec, string as _str
        _alpha = _str.ascii_letters + _str.digits
        senha_gerada = ''.join(_sec.choice(_alpha) for _ in range(12))
        cur.execute("""
            INSERT INTO usuarios (usuario, nome, senha_hash, nivel, criado_em)
            VALUES (?, ?, ?, 'admin', ?)
        """, ("admin", "Administrador", _hash_senha(senha_gerada),
               datetime.now().isoformat()))
        conn.commit()
        print(f"\n[OK] Usuário admin criado.")
        print(f"     Login : admin")
        print(f"     Senha : {senha_gerada}")
        print("     [!] Anote esta senha — ela não será exibida novamente.")
    else:
        print("\n[OK] Usuários existentes mantidos.")

    migrar_agenda(conn)
    print("[OK] Tabela agenda_eventos verificada.")
    migrar_boletim_mensal(conn)
    print("[OK] Tabela boletim_mensal_itens verificada.")

    # FIX DB-04: Definir WAL mode persistentemente UMA VEZ no banco
    # A partir daqui, WAL persiste mesmo sem o PRAGMA por conexão
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.commit()
    print("[OK] WAL mode configurado persistentemente.")

    conn.close()
    print("\n" + "=" * 54)
    print("  Próximo passo: rode iniciar.bat")
    print("=" * 54)


def migrar_agenda(conn):
    """Adiciona tabela de eventos da agenda. Seguro rodar mesmo se já existir."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS agenda_eventos (
        id_evento    INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo       TEXT    NOT NULL,
        descricao    TEXT,
        tipo         TEXT    NOT NULL DEFAULT 'outro'
                     CHECK(tipo IN ('reuniao','planejamento','campo','prazo','treinamento','tarefa','ferias','outro')),
        data_inicio  TEXT    NOT NULL,
        data_fim     TEXT,
        dia_inteiro  INTEGER NOT NULL DEFAULT 0 CHECK(dia_inteiro IN (0,1)),
        lembrete_min INTEGER DEFAULT 60,
        cor          TEXT    DEFAULT '#1a4fba',
        criado_por   TEXT,
        criado_em    TEXT    NOT NULL,
        recorrencia  TEXT    NOT NULL DEFAULT 'nenhuma',
        recorrencia_fim TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_agenda_inicio ON agenda_eventos(data_inicio);
    CREATE INDEX IF NOT EXISTS idx_agenda_recorrencia ON agenda_eventos(recorrencia, recorrencia_fim);
    """)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agenda_eventos)").fetchall()}
    if "recorrencia" not in cols:
        conn.execute("ALTER TABLE agenda_eventos ADD COLUMN recorrencia TEXT NOT NULL DEFAULT 'nenhuma'")
    if "recorrencia_fim" not in cols:
        conn.execute("ALTER TABLE agenda_eventos ADD COLUMN recorrencia_fim TEXT")
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='agenda_eventos'"
    ).fetchone()
    if sql and "ferias" not in (sql[0] or ""):
        conn.executescript("""
        ALTER TABLE agenda_eventos RENAME TO agenda_eventos_old;
        CREATE TABLE agenda_eventos (
            id_evento    INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo       TEXT    NOT NULL,
            descricao    TEXT,
            tipo         TEXT    NOT NULL DEFAULT 'outro'
                         CHECK(tipo IN ('reuniao','planejamento','campo','prazo','treinamento','tarefa','ferias','outro')),
            data_inicio  TEXT    NOT NULL,
            data_fim     TEXT,
            dia_inteiro  INTEGER NOT NULL DEFAULT 0 CHECK(dia_inteiro IN (0,1)),
            lembrete_min INTEGER DEFAULT 60,
            cor          TEXT    DEFAULT '#1a4fba',
            criado_por   TEXT,
            criado_em    TEXT    NOT NULL,
            recorrencia  TEXT    NOT NULL DEFAULT 'nenhuma',
            recorrencia_fim TEXT
        );
        INSERT INTO agenda_eventos (
            id_evento, titulo, descricao, tipo, data_inicio, data_fim, dia_inteiro,
            lembrete_min, cor, criado_por, criado_em, recorrencia, recorrencia_fim
        )
        SELECT
            id_evento, titulo, descricao, tipo, data_inicio, data_fim, dia_inteiro,
            lembrete_min, cor, criado_por, criado_em,
            COALESCE(recorrencia, 'nenhuma'), recorrencia_fim
        FROM agenda_eventos_old;
        DROP TABLE agenda_eventos_old;
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agenda_inicio ON agenda_eventos(data_inicio)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agenda_recorrencia ON agenda_eventos(recorrencia, recorrencia_fim)")
    conn.execute(
        """UPDATE agenda_eventos
              SET tipo='ferias', cor='#06b6d4'
            WHERE tipo <> 'ferias'
              AND (
                  lower(titulo) LIKE '%ferias%'
                  OR lower(titulo) LIKE '%férias%'
                  OR titulo LIKE '%Férias%'
                  OR titulo LIKE '%FÉRIAS%'
              )"""
    )
    conn.commit()


def migrar_boletim_mensal(conn):
    """Adiciona tabela de itens editaveis do boletim mensal."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS boletim_mensal_itens (
        id_item     INTEGER PRIMARY KEY AUTOINCREMENT,
        ano_mes     TEXT NOT NULL,
        chave       TEXT NOT NULL,
        origem      TEXT NOT NULL DEFAULT 'manual'
                   CHECK(origem IN ('auto','manual')),
        ordem       INTEGER NOT NULL DEFAULT 0,
        indicador   TEXT NOT NULL,
        quantidade  INTEGER NOT NULL DEFAULT 0,
        unidade     TEXT,
        ativo       INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
        atualizado_em TEXT NOT NULL,
        UNIQUE(ano_mes, chave)
    );
    CREATE INDEX IF NOT EXISTS idx_boletim_mensal_mes
        ON boletim_mensal_itens(ano_mes, ordem);
    """)
    conn.commit()


if __name__ == "__main__":
    main()
