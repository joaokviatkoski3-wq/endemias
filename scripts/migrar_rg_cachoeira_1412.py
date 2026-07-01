import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "endemias.db"
BACKUP_DIR = ROOT / "backups"

LOCALIDADE = "Cachoeira"
QUARTEIRAO_ORIGEM = "1267"
QUARTEIRAO_DESTINO = "1412"


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
    destino = BACKUP_DIR / f"endemias_pre_rg_cachoeira_1412_{stamp}.db"
    shutil.copy2(DB_PATH, destino)
    return destino


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Banco nao encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        loc = conn.execute(
            "SELECT id_localidade, nome FROM localidades WHERE nome=?",
            (LOCALIDADE,),
        ).fetchone()
        if not loc:
            raise SystemExit(f"Localidade nao encontrada: {LOCALIDADE}")

        origem = conn.execute(
            """SELECT id_quarteirao
                 FROM registro_geografico_quarteiroes
                WHERE id_localidade=? AND quarteirao=?""",
            (loc["id_localidade"], QUARTEIRAO_ORIGEM),
        ).fetchone()

        destino = conn.execute(
            """SELECT id_quarteirao
                 FROM registro_geografico_quarteiroes
                WHERE id_localidade=? AND quarteirao=?""",
            (loc["id_localidade"], QUARTEIRAO_DESTINO),
        ).fetchone()
        if not origem and destino:
            total = conn.execute(
                "SELECT COUNT(*) FROM registro_geografico_imoveis WHERE id_quarteirao=?",
                (destino["id_quarteirao"],),
            ).fetchone()[0]
            print(f"Migracao ja aplicada: {LOCALIDADE} {QUARTEIRAO_DESTINO} com {total} imoveis")
            return
        if not origem:
            raise SystemExit(f"Quarteirao de origem nao encontrado: {LOCALIDADE} {QUARTEIRAO_ORIGEM}")
        if destino:
            raise SystemExit(f"Quarteirao de destino ja existe: {LOCALIDADE} {QUARTEIRAO_DESTINO}")

        backup = _backup_db()
        agora = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                """UPDATE registro_geografico_quarteiroes
                      SET quarteirao=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                (QUARTEIRAO_DESTINO, agora, origem["id_quarteirao"]),
            )
            conn.execute(
                """UPDATE registro_geografico_imoveis
                      SET quarteirao=?, atualizado_em=?
                    WHERE id_quarteirao=?""",
                (QUARTEIRAO_DESTINO, agora, origem["id_quarteirao"]),
            )
            rows = conn.execute(
                """SELECT id_imovel, localidade, quarteirao, logradouro, numero, sequencia,
                          lado, tipo, observacao, agentes_texto
                     FROM registro_geografico_imoveis
                    WHERE id_quarteirao=?""",
                (origem["id_quarteirao"],),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE registro_geografico_imoveis SET busca_normalizada=? WHERE id_imovel=?",
                    (_busca_normalizada(dict(row)), row["id_imovel"]),
                )

        total = conn.execute(
            "SELECT COUNT(*) FROM registro_geografico_imoveis WHERE id_quarteirao=?",
            (origem["id_quarteirao"],),
        ).fetchone()[0]
        print(f"Backup criado: {backup}")
        print(f"{LOCALIDADE} {QUARTEIRAO_ORIGEM} -> {QUARTEIRAO_DESTINO}: {total} imoveis atualizados")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
