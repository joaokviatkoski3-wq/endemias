"""Prova SQL/concorrrencia em instancia descartavel, nunca na porta oficial."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import auth, db, recuperacao_senha as recovery


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
        conn.execute("""CREATE TABLE usuarios (id_usuario BIGINT PRIMARY KEY, usuario TEXT,
            nome TEXT, nivel TEXT, ativo INTEGER NOT NULL DEFAULT 1, senha_hash TEXT NOT NULL)""")
        old = auth.hash_senha("SenhaFicticiaAnterior!")
        conn.execute("INSERT INTO usuarios VALUES (1,'admin-ficticio','Administrador Ficticio','admin',1,?), (21,'pessoa-ficticia','Pessoa Ficticia','usuario',1,?)", (old, old))
        conn.execute((ROOT / "migrations/postgresql/0031_recuperacao_senha.sql").read_text(encoding="utf-8"))
        conn.commit()
        token = recovery.gerar(target, 21, 1, agora=1000)
        newer = recovery.gerar(target, 21, 1, agora=1001)
        try:
            recovery.consumir(target, token, "NovaSenhaFicticia!", agora=1100)
        except ValueError:
            pass
        else:
            raise AssertionError("Link substituido aceito.")
        conn.rollback()
        def consume(_):
            try:
                recovery.consumir(target, newer, "NovaSenhaFicticia!", agora=1100)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(consume, range(2))) == 1
        stored = conn.execute("SELECT senha_hash FROM usuarios WHERE id_usuario=21").fetchone()[0]
        assert auth.verificar_senha("NovaSenhaFicticia!", stored)[0]
        conn.rollback()
        token = recovery.gerar(target, 21, 1, agora=2000)
        try:
            recovery.consumir(target, token, "SenhaDeRetornoFicticia!", agora=2100,
                auditar=lambda *args: (_ for _ in ()).throw(RuntimeError("falha ficticia")))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Nao simulou falha.")
        assert conn.execute("SELECT usado_em FROM usuarios_recuperacao_senha WHERE usuario_id=21").fetchone()[0] is None
        assert conn.execute("SELECT senha_hash FROM usuarios WHERE id_usuario=21").fetchone()[0] == stored
        conn.rollback()
        try:
            recovery.consumir(target, token, "SenhaDeRetornoFicticia!", agora=2900)
        except ValueError:
            pass
        else:
            raise AssertionError("Link expirado aceito.")
        assert recovery.consumir(target, token, "SenhaDeRetornoFicticia!", agora=2100) == 21
        print("OK PostgreSQL descartavel: migracao 0031, substituicao, expiracao, rollback e consumo concorrente unico.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
