"""
migrar_codigo_focos.py
Preenche o campo 'codigo' nos focos_positivos que já existem no banco.
Execute UMA VEZ, antes de subir o sistema v3.

Uso: python migrar_codigo_focos.py
"""
import sqlite3, os, re

BANCO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "endemias.db")

conn = sqlite3.connect(BANCO)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Garantir que a coluna existe
try:
    cur.execute("ALTER TABLE focos_positivos ADD COLUMN codigo TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_foco_codigo ON focos_positivos(codigo)")
    conn.commit()
    print("[OK] Coluna 'codigo' criada.")
except Exception:
    print("[OK] Coluna 'codigo' já existe.")

# Buscar focos sem codigo ainda
focos = cur.execute("""
    SELECT id_foco, data, num_tubo
    FROM focos_positivos
    WHERE codigo IS NULL OR codigo = ''
""").fetchall()

print(f"Focos sem código: {len(focos)}")

atualizados = 0
for f in focos:
    data_clean = (f["data"] or "")[:10].replace("-", "")
    # Pega só o primeiro tubo (antes da vírgula) e extrai dígitos
    primeiro_tubo = (f["num_tubo"] or "").split(",")[0].strip()
    num = re.sub(r"\D", "", primeiro_tubo)
    if data_clean and num:
        codigo = data_clean + num
        cur.execute("UPDATE focos_positivos SET codigo=? WHERE id_foco=?",
                    (codigo, f["id_foco"]))
        atualizados += 1

conn.commit()
conn.close()
print(f"Códigos gerados: {atualizados}")
print("Concluído.")
