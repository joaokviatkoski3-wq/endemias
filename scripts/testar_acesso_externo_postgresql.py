"""Exercita somente banco descartavel em porta diferente da producao."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import auth, db, formularios, termos_uso


def main():
    if os.environ.get("ENDEMIAS_PG_HOST") != "127.0.0.1" or os.environ.get("ENDEMIAS_PG_PORT", "5432") == "5432":
        raise SystemExit("Exige instancia descartavel em loopback e porta diferente de 5432.")
    target = db.DatabaseTarget("postgresql", "endemias_teste")
    conn = db.connect(target)
    try:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "endemias_teste"
        conn.execute("CREATE TEMPORARY TABLE usuarios (id_usuario BIGINT PRIMARY KEY)")
        conn.execute("INSERT INTO usuarios VALUES (21),(22)")
        conn.execute("CREATE TEMPORARY TABLE login_tentativas (chave TEXT PRIMARY KEY, tentativas BIGINT NOT NULL, primeira_em DOUBLE PRECISION NOT NULL, atualizado_em TEXT NOT NULL)")
        for version in ("0028", "0030"):
            sql = next((ROOT / "migrations/postgresql").glob(version + "_*.sql")).read_text(encoding="utf-8")
            sql = sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMPORARY TABLE IF NOT EXISTS").replace("CREATE TABLE formularios", "CREATE TEMPORARY TABLE formularios")
            conn.execute(sql)
        conn.commit()
        class Shared:
            backend = "postgresql"
            def __getattr__(self, name): return getattr(conn, name)
            def close(self): pass
        shared = Shared()
        with patch.object(db, "connect", return_value=shared):
            auth.registrar_login_falha_db(lambda: shared, "prova", agora=100)
            auth.registrar_login_falha_db(lambda: shared, "prova", agora=101)
            assert conn.execute("SELECT tentativas FROM login_tentativas WHERE chave='prova'").fetchone()[0] == 2
            auth.registrar_login_falha_db(lambda: shared, "prova", agora=2000)
            assert conn.execute("SELECT tentativas FROM login_tentativas WHERE chave='prova'").fetchone()[0] == 1
            fid = formularios.salvar(target, "rg_atualizacao", {"sintetico": True}, {"id_usuario": 21}, uuid_cliente="ensaio")
            try:
                formularios.salvar(target, "rg_atualizacao", {}, {"id_usuario": 22}, uuid_cliente="ensaio")
            except ValueError: pass
            else: raise AssertionError("Aceitou sobrescrita alheia")
            formularios.salvar(target, "rg_atualizacao", {"atualizado": True}, {"id_usuario": 21}, uuid_cliente="ensaio")
            assert formularios.obter(target, fid)["payload"] == {"atualizado": True}
            app = Flask(__name__)
            with app.test_request_context("/"):
                assert not termos_uso.aceitou(target, 21)
                termos_uso.registrar(target, 21)
                termos_uso.registrar(target, 21)
                assert termos_uso.aceitou(target, 21)
                assert conn.execute("SELECT COUNT(*) FROM usuarios_termos").fetchone()[0] == 1
        print("OK PostgreSQL descartavel: migracao 0030, aceite, idempotencia, formularios e limites de login.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
