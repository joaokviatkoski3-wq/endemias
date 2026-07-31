"""Ensaio controlado de concorrencia em banco PostgreSQL descartavel."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app_core import db as db_core
from app_core import postgresql


class PostgreSQLConcurrencyError(RuntimeError):
    pass


def run_probe(database, sessions=5, iterations=5, lock_timeout_ms=20):
    """Concorre numa tabela efemera e sempre tenta remove-la ao final."""
    sessions = int(sessions)
    iterations = int(iterations)
    if sessions < 2 or sessions > 10:
        raise ValueError("O ensaio exige entre 2 e 10 sessoes.")
    if iterations < 1 or iterations > 100:
        raise ValueError("Iteracoes devem ficar entre 1 e 100.")

    try:
        from psycopg2 import sql
    except ImportError as exc:
        raise PostgreSQLConcurrencyError(
            "Driver psycopg2 nao esta disponivel."
        ) from exc

    table = f"endemias_concurrency_probe_{uuid.uuid4().hex}"
    admin = postgresql.connect(database=database)
    connections = []
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE UNLOGGED TABLE {} (id integer PRIMARY KEY, value integer NOT NULL)"
                ).format(sql.Identifier(table))
            )
            cursor.execute(
                sql.SQL("INSERT INTO {} (id, value) VALUES (1, 0)").format(
                    sql.Identifier(table)
                )
            )
        admin.commit()
        created = True
        for _ in range(sessions):
            connections.append(postgresql.connect(database=database))
        barrier = Barrier(sessions)

        def worker(conn):
            retries = 0
            completed = 0
            barrier.wait(timeout=10)
            while completed < iterations:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SET LOCAL lock_timeout = %s",
                            (f"{int(lock_timeout_ms)}ms",),
                        )
                        cursor.execute(
                            sql.SQL("SELECT value FROM {} WHERE id=1 FOR UPDATE").format(
                                sql.Identifier(table)
                            )
                        )
                        value = cursor.fetchone()[0]
                        time.sleep(max(int(lock_timeout_ms), 1) / 1000 * 2)
                        cursor.execute(
                            sql.SQL("UPDATE {} SET value=%s WHERE id=1").format(
                                sql.Identifier(table)
                            ),
                            (value + 1,),
                        )
                    conn.commit()
                    completed += 1
                except Exception as exc:
                    conn.rollback()
                    if not db_core.is_concurrency_error(exc):
                        raise
                    retries += 1
                    if retries > sessions * iterations * 20:
                        raise PostgreSQLConcurrencyError(
                            "O ensaio excedeu o limite de novas tentativas."
                        ) from exc
                    time.sleep(0.01)
            return {"completed": completed, "retries": retries}

        with ThreadPoolExecutor(max_workers=sessions) as executor:
            results = list(executor.map(worker, connections))

        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT value FROM {} WHERE id=1").format(
                    sql.Identifier(table)
                )
            )
            final_value = cursor.fetchone()[0]
        admin.rollback()
        expected = sessions * iterations
        if final_value != expected:
            raise PostgreSQLConcurrencyError(
                f"Contador concorrente divergiu: {final_value}/{expected}."
            )
        return {
            "sessions": sessions,
            "iterations_per_session": iterations,
            "operations": expected,
            "retries": sum(item["retries"] for item in results),
            "final_value": final_value,
        }
    finally:
        for conn in connections:
            conn.close()
        try:
            if created:
                try:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            sql.SQL("DROP TABLE IF EXISTS {}").format(
                                sql.Identifier(table)
                            )
                        )
                    admin.commit()
                except Exception:
                    admin.rollback()
                    raise
        finally:
            admin.close()
