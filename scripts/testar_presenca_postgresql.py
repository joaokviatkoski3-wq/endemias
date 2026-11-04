"""Instancia PostgreSQL descartavel, porta separada, somente contas ficticias."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import auth, db, presenca


def main():
    if (os.environ.get("ENDEMIAS_PG_HOST") != "127.0.0.1"
            or os.environ.get("ENDEMIAS_PG_PORT", "5432") == "5432"
            or os.environ.get("ENDEMIAS_PG_DATABASE") != "endemias_teste"):
        raise ValueError("Exige instancia descartavel local, porta separada e endemias_teste.")
    target = db.DatabaseTarget("postgresql", "endemias_teste")
    conn = db.connect(target)
    try:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "endemias_teste"
        assert conn.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0
        conn.execute("""CREATE TABLE usuarios (id_usuario BIGINT PRIMARY KEY,
            ativo INTEGER NOT NULL DEFAULT 1, senha_hash TEXT NOT NULL)""")
        password = auth.hash_senha("SenhaFicticia123!")
        conn.execute("INSERT INTO usuarios VALUES (1,1,?), (2,1,?)", (password, password))
        conn.execute((ROOT / "migrations/postgresql/0032_presenca_usuarios.sql").read_text(encoding="utf-8"))
        conn.commit()
        user = {"id_usuario": 1, "senha_hash": password}
        for sid in ("aparelho1", "aparelho2"):
            presenca.confirmar(target, user, sid, agora=1000)
        assert presenca.resumo(target, agora=1000)["online_total"] == 1
        presenca.encerrar(target, user, "aparelho1", agora=1010)
        assert presenca.resumo(target, agora=1010)["online_total"] == 1
        presenca.encerrar(target, user, "aparelho2", agora=1010)
        presenca.confirmar(target, user, "aparelho2", agora=1040)
        assert presenca.resumo(target, agora=1040)["online_total"] == 0
        def run(i):
            if i == 0:
                presenca.encerrar(target, user, "concorrente", agora=1100)
            else:
                presenca.confirmar(target, user, "concorrente", agora=1101)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(4)))
        assert presenca.resumo(target, agora=1101)["online_total"] == 0
        presenca.confirmar(target, user, "nova", agora=1200)
        assert presenca.resumo(target, agora=1320)["online_total"] == 1
        assert presenca.resumo(target, agora=1321)["online_total"] == 0
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=1", (auth.hash_senha("NovaSenhaFicticia!"),))
        conn.commit()
        assert presenca.resumo(target, agora=1201)["online_total"] == 0
        assert presenca.resumo(target, agora=1201)["usuarios"][0]["ultima_presenca"] is not None
        presenca.confirmar(target, {"id_usuario": 2, "senha_hash": password}, "limpeza", agora=100000)
        assert conn.execute("SELECT COUNT(*) FROM usuarios_presenca_sessoes").fetchone()[0] == 1
        print("OK PostgreSQL descartavel: migracao 0032, varios aparelhos, expiracao, concorrencia/logout, senha e limpeza preservando historico.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
