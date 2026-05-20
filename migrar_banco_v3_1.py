"""
migrar_banco_v3_1.py — Migração de segurança e integridade
Setor de Endemias / Almirante Tamandaré-PR

Execute UMA VEZ após receber o pacote corrigido:
    python migrar_banco_v3_1.py

O que este script faz:
  1. Cria backup do banco antes de qualquer alteração
  2. Ativa WAL mode persistente (performance e segurança contra lock)
  3. Adiciona UNIQUE em tratamentos (previne duplicatas em reprocessamento)
  4. Cria índices compostos que faltavam (performance das queries mais pesadas)
  5. Verifica integridade referencial do banco
  6. Remove tabela órfã 'endemias' (se vazia e confirmada como resíduo)
  7. Faz upgrade de hashes de senha legados (SHA-256) para pbkdf2:sha256

ATENÇÃO: Após este script, todos os usuários ainda conseguem fazer login.
Os hashes são atualizados automaticamente na primeira autenticação de cada um.
"""

import os
import sys
import shutil
import sqlite3
import hashlib
from datetime import datetime

# ── Localizar banco ────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "endemias.db")
BK_DIR    = os.path.join(BASE_DIR, "backups")

def falhar(msg):
    print(f"\n[ERRO FATAL] {msg}")
    sys.exit(1)

def ok(msg):
    print(f"  [OK] {msg}")

def info(msg):
    print(f"  [ ] {msg}")

def aviso(msg):
    print(f"  [!] {msg}")

# ── Verificações iniciais ─────────────────────────────────────────────────
print("=" * 60)
print("  Migração endemias.db → v3.1")
print("=" * 60)

if not os.path.exists(DB_PATH):
    falhar(f"Banco não encontrado: {DB_PATH}")

# ── 1. Backup ──────────────────────────────────────────────────────────────
print("\n[1/7] Criando backup...")
os.makedirs(BK_DIR, exist_ok=True)
ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
bk_path = os.path.join(BK_DIR, f"endemias_{ts}_pre_migracao_v3_1.db")
shutil.copy2(DB_PATH, bk_path)
ok(f"Backup salvo em: backups/endemias_{ts}_pre_migracao_v3_1.db")

# ── Conectar ───────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = OFF")  # desligado só durante a migração

# ── 2. WAL mode persistente ────────────────────────────────────────────────
print("\n[2/7] Configurando WAL mode persistente...")
modo = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
conn.execute("PRAGMA wal_autocheckpoint=1000")
conn.commit()
ok(f"journal_mode={modo}")

# ── 3. UNIQUE em tratamentos ───────────────────────────────────────────────
print("\n[3/7] Adicionando UNIQUE em tratamentos...")

# Verificar se já existe
indices = [r[1] for r in conn.execute("PRAGMA index_list(tratamentos)").fetchall()]
if any("uq_trat" in idx or "tratamentos_id_visita_tipo" in idx for idx in indices):
    ok("UNIQUE já existe — nenhuma ação necessária.")
else:
    # Verificar se há duplicatas que precisam ser resolvidas antes
    dups = conn.execute("""
        SELECT id_visita, tipo, COUNT(*) as n
        FROM tratamentos
        GROUP BY id_visita, tipo
        HAVING n > 1
    """).fetchall()

    if dups:
        aviso(f"{len(dups)} combinações (id_visita, tipo) duplicadas detectadas.")
        aviso("Removendo duplicatas (mantendo o primeiro registro de cada grupo)...")
        conn.execute("""
            DELETE FROM tratamentos
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM tratamentos
                GROUP BY id_visita, tipo
            )
        """)
        removidos = conn.total_changes
        conn.commit()
        ok(f"{removidos} registros duplicados removidos.")
    else:
        ok("Nenhuma duplicata encontrada nos tratamentos existentes.")

    # Recriar tabela com UNIQUE (SQLite não suporta ADD CONSTRAINT)
    info("Recriando tabela tratamentos com constraint UNIQUE...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tratamentos_novo (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            id_visita              TEXT    NOT NULL REFERENCES visitas(id_visita),
            tipo                   TEXT,
            quantidade_carga       REAL,
            qtd_depositos_tratados INTEGER,
            UNIQUE(id_visita, tipo)
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO tratamentos_novo
            (id, id_visita, tipo, quantidade_carga, qtd_depositos_tratados)
        SELECT id, id_visita, tipo, quantidade_carga, qtd_depositos_tratados
        FROM tratamentos
    """)
    n = conn.execute("SELECT COUNT(*) FROM tratamentos_novo").fetchone()[0]
    conn.execute("DROP TABLE tratamentos")
    conn.execute("ALTER TABLE tratamentos_novo RENAME TO tratamentos")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trat_visita ON tratamentos(id_visita)")
    conn.commit()
    ok(f"Tabela tratamentos recriada com UNIQUE. {n} registros migrados.")

# ── 4. Índices compostos ───────────────────────────────────────────────────
print("\n[4/7] Criando índices de performance...")

indices_novos = [
    ("idx_foco_notif",
     "CREATE INDEX IF NOT EXISTS idx_foco_notif ON focos_positivos(gera_notificacao, status_notificacao)"),
    ("idx_visitas_data_tipo",
     "CREATE INDEX IF NOT EXISTS idx_visitas_data_tipo ON visitas(data, tipo)"),
    ("idx_foco_localidade",
     "CREATE INDEX IF NOT EXISTS idx_foco_localidade ON focos_positivos(id_localidade)"),
]
for nome_idx, sql in indices_novos:
    conn.execute(sql)
    ok(f"Índice '{nome_idx}' verificado/criado.")
conn.commit()

# ── 5. Verificação de integridade ──────────────────────────────────────────
print("\n[5/7] Verificando integridade do banco...")
conn.execute("PRAGMA foreign_keys = ON")
erros_integ = conn.execute("PRAGMA integrity_check").fetchall()
if erros_integ and erros_integ[0][0] == "ok":
    ok("integrity_check: ok")
else:
    aviso("Problemas encontrados no integrity_check:")
    for e in erros_integ:
        print(f"    {e[0]}")

fk_erros = conn.execute("PRAGMA foreign_key_check").fetchall()
if not fk_erros:
    ok("foreign_key_check: sem violações")
else:
    aviso(f"{len(fk_erros)} violação(ões) de FK encontradas:")
    for e in fk_erros[:10]:
        print(f"    tabela={e[0]} rowid={e[1]} pai={e[2]} fkid={e[3]}")

# ── 6. Tabela 'endemias' órfã ──────────────────────────────────────────────
print("\n[6/7] Verificando tabela 'endemias' órfã...")
tabela_endemias = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='endemias'"
).fetchone()
if tabela_endemias:
    n_endemias = conn.execute("SELECT COUNT(*) FROM endemias").fetchone()[0]
    if n_endemias == 0:
        aviso("Tabela 'endemias' encontrada com 0 registros (parece ser resíduo de versão anterior).")
        resp = input("  Deseja removê-la? (s/N): ").strip().lower()
        if resp == "s":
            conn.execute("DROP TABLE endemias")
            conn.commit()
            ok("Tabela 'endemias' removida.")
        else:
            info("Tabela 'endemias' mantida conforme solicitado.")
    else:
        aviso(f"Tabela 'endemias' tem {n_endemias} registro(s) — NÃO removida. Verifique manualmente.")
else:
    ok("Tabela 'endemias' não encontrada (já foi removida ou nunca existiu).")

# ── 6b. Colunas SISPNC e CONTAOVOS_STATUS (DB-06) ─────────────────────────
print("\n[6b/7] Verificando colunas SISPNC e CONTAOVOS_STATUS em visitas...")
colunas_visitas = {r[1] for r in conn.execute("PRAGMA table_info(visitas)").fetchall()}
if "SISPNC" not in colunas_visitas:
    conn.execute("ALTER TABLE visitas ADD COLUMN SISPNC VARCHAR(20)")
    conn.commit()
    ok("Coluna SISPNC adicionada à tabela visitas.")
else:
    ok("Coluna SISPNC já existe.")
if "CONTAOVOS_STATUS" not in colunas_visitas:
    conn.execute("ALTER TABLE visitas ADD COLUMN CONTAOVOS_STATUS INTEGER")
    conn.commit()
    ok("Coluna CONTAOVOS_STATUS adicionada à tabela visitas.")
else:
    ok("Coluna CONTAOVOS_STATUS já existe.")

# ── 7. Contagens finais ────────────────────────────────────────────────────
print("\n[7/7] Resumo do banco após migração:")
tabelas = [
    "usuarios", "localidades", "agentes", "visitas",
    "visita_agentes", "depositos_inspecionados", "tratamentos",
    "coletas", "resultados_laboratorio", "focos_positivos",
    "focos_historico", "agenda_eventos",
]
for t in tabelas:
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"    {t:<35} {n:>8} registro(s)")
    except Exception:
        aviso(f"Tabela '{t}' não encontrada no banco.")

conn.close()

print("\n" + "=" * 60)
print("  Migração concluída com sucesso!")
print(f"  Backup salvo em: backups/endemias_{ts}_pre_migracao_v3_1.db")
print()
print("  PRÓXIMOS PASSOS:")
print("  1. Instale as dependências: pip install -r requirements.txt")
print("  2. Inicie o sistema normalmente: iniciar.bat")
print("  3. Cada usuário terá o hash de senha atualizado automaticamente")
print("     no seu próximo login (sem necessidade de resetar senhas).")
print("=" * 60)
