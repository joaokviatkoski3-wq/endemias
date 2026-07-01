import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "endemias.db"
BACKUP_DIR = ROOT / "backups"


def _norm(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _busca_normalizada(row):
    return _norm(
        " ".join(
            str(row.get(k) or "")
            for k in (
                "localidade",
                "quarteirao",
                "logradouro",
                "numero",
                "sequencia",
                "lado",
                "tipo",
                "observacao",
                "agentes_texto",
            )
        )
    )


def _backup_db():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_DIR / f"endemias_pre_rg_corrige_cachoeira_1412_{stamp}.db"
    shutil.copy2(DB_PATH, destino)
    return destino


def _localidade(conn, nome):
    row = conn.execute(
        "SELECT id_localidade, nome FROM localidades WHERE nome=?",
        (nome,),
    ).fetchone()
    if not row:
        raise SystemExit(f"Localidade nao encontrada: {nome}")
    return row


def _quarteirao(conn, id_localidade, quarteirao):
    return conn.execute(
        """SELECT id_quarteirao, id_localidade, localidade, quarteirao
             FROM registro_geografico_quarteiroes
            WHERE id_localidade=? AND quarteirao=?""",
        (id_localidade, quarteirao),
    ).fetchone()


def _contar_imoveis(conn, id_quarteirao):
    return conn.execute(
        "SELECT COUNT(*) FROM registro_geografico_imoveis WHERE id_quarteirao=?",
        (id_quarteirao,),
    ).fetchone()[0]


def _atualizar_busca(conn, id_quarteirao):
    rows = conn.execute(
        """SELECT id_imovel, localidade, quarteirao, logradouro, numero, sequencia,
                  lado, tipo, observacao, agentes_texto
             FROM registro_geografico_imoveis
            WHERE id_quarteirao=?""",
        (id_quarteirao,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE registro_geografico_imoveis SET busca_normalizada=? WHERE id_imovel=?",
            (_busca_normalizada(dict(row)), row["id_imovel"]),
        )


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Banco nao encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cachoeira = _localidade(conn, "Cachoeira")
        tamboara = _localidade(conn, "Tamboara")

        cachoeira_1267 = _quarteirao(conn, cachoeira["id_localidade"], "1267")
        cachoeira_1412 = _quarteirao(conn, cachoeira["id_localidade"], "1412")
        tamboara_1412 = _quarteirao(conn, tamboara["id_localidade"], "1412")

        ja_corrigido = (
            cachoeira_1267
            and cachoeira_1412
            and not tamboara_1412
            and _contar_imoveis(conn, cachoeira_1267["id_quarteirao"]) > 0
            and _contar_imoveis(conn, cachoeira_1412["id_quarteirao"]) > 0
        )
        if ja_corrigido:
            print("Correcao ja aplicada: Cachoeira possui 1267 e 1412; Tamboara nao possui 1412.")
            return

        if not cachoeira_1412:
            raise SystemExit("Estado inesperado: Cachoeira 1412 nao encontrado para desfazer a migracao anterior.")
        if cachoeira_1267:
            raise SystemExit("Estado inesperado: Cachoeira 1267 ja existe antes da correcao.")
        if not tamboara_1412:
            raise SystemExit("Estado inesperado: Tamboara 1412 nao encontrado para mover para Cachoeira.")

        backup = _backup_db()
        agora = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                """UPDATE registro_geografico_quarteiroes
                      SET quarteirao=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                ("1267", agora, cachoeira_1412["id_quarteirao"]),
            )
            conn.execute(
                """UPDATE registro_geografico_imoveis
                      SET quarteirao=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                ("1267", agora, cachoeira_1412["id_quarteirao"]),
            )
            _atualizar_busca(conn, cachoeira_1412["id_quarteirao"])

            conn.execute(
                """UPDATE registro_geografico_quarteiroes
                      SET id_localidade=?, localidade=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                (cachoeira["id_localidade"], cachoeira["nome"], agora, tamboara_1412["id_quarteirao"]),
            )
            conn.execute(
                """UPDATE registro_geografico_imoveis
                      SET id_localidade=?, localidade=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                (cachoeira["id_localidade"], cachoeira["nome"], agora, tamboara_1412["id_quarteirao"]),
            )
            _atualizar_busca(conn, tamboara_1412["id_quarteirao"])

        total_1267 = _contar_imoveis(conn, cachoeira_1412["id_quarteirao"])
        total_1412 = _contar_imoveis(conn, tamboara_1412["id_quarteirao"])
        print(f"Backup criado: {backup}")
        print(f"Cachoeira 1267 restaurado com {total_1267} imoveis")
        print(f"Tamboara 1412 movido para Cachoeira 1412 com {total_1412} imoveis")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
