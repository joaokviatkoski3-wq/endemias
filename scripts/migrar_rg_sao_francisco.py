import argparse
import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


QUARTEIROES_SAO_FRANCISCO = [
    "1001", "1002", "1003", "1004", "1006", "1007", "1009", "1010",
    "1011", "1012", "0637", "0638", "0639", "0640", "0641", "0642",
    "0643", "0644", "0645", "0646", "0647", "0648", "0649", "0650",
    "0651", "0652", "0653", "0654", "0705", "0706", "0707", "0708",
    "0709", "0710", "0711", "0712", "0713", "0714", "0715", "0716",
    "0717", "0718", "0719", "0720", "0721", "0722", "0723", "0724",
    "0725", "0726", "0727", "0728", "0729", "0730", "0731", "0732",
    "0733", "0734", "0735", "0736", "0737", "0738", "0739", "0740",
    "0741", "0742", "0743", "0744", "0745", "0747", "0749", "0750",
    "0754", "0755", "0756", "0757", "0746", "0748", "0753", "0752",
    "0751", "1005", "1008", "1013", "1015", "1014",
]

QUARTEIROES_NOVOS_VAZIOS = ["0655.1"]


def _norm(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _backup(db_path):
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{db_path.stem}_pre_rg_sao_francisco_{stamp}{db_path.suffix}"
    shutil.copy2(db_path, target)
    return target


def _buscar_localidade(conn, nome_normalizado):
    for row in conn.execute("SELECT id_localidade, nome FROM localidades"):
        if _norm(row["nome"]) == nome_normalizado:
            return row
    return None


def migrar(db_path, fazer_backup=True):
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    backup_path = _backup(db_path) if fazer_backup else None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        destino = _buscar_localidade(conn, "sao francisco")
        if not destino:
            raise RuntimeError("Localidade Sao Francisco nao encontrada.")
        agora = datetime.now().isoformat(timespec="seconds")
        quarteiroes = list(dict.fromkeys(QUARTEIROES_SAO_FRANCISCO))
        novos_vazios = list(dict.fromkeys(QUARTEIROES_NOVOS_VAZIOS))
        placeholders = ",".join("?" for _ in quarteiroes)

        antes = conn.execute(
            f"""SELECT q.quarteirao, q.localidade, COUNT(i.id_imovel) AS imoveis
                  FROM registro_geografico_quarteiroes q
                  LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
                 WHERE q.quarteirao IN ({placeholders})
                 GROUP BY q.id_quarteirao, q.quarteirao, q.localidade
                 ORDER BY CAST(q.quarteirao AS INTEGER), q.quarteirao""",
            quarteiroes,
        ).fetchall()
        encontrados = {row["quarteirao"] for row in antes}
        ausentes = [q for q in quarteiroes if q not in encontrados]

        with conn:
            conn.execute(
                f"""UPDATE registro_geografico_quarteiroes
                       SET id_localidade=?, localidade=?, atualizado_em=?
                     WHERE quarteirao IN ({placeholders})""",
                [destino["id_localidade"], destino["nome"], agora, *quarteiroes],
            )
            conn.execute(
                f"""UPDATE registro_geografico_imoveis
                       SET id_localidade=?, localidade=?, atualizado_em=?
                     WHERE quarteirao IN ({placeholders})""",
                [destino["id_localidade"], destino["nome"], agora, *quarteiroes],
            )
            for q in novos_vazios:
                conn.execute(
                    """INSERT OR IGNORE INTO registro_geografico_quarteiroes
                       (id_localidade, localidade, quarteirao, criado_em, atualizado_em)
                       VALUES (?, ?, ?, ?, ?)""",
                    (destino["id_localidade"], destino["nome"], q, agora, agora),
                )

        total_imoveis = conn.execute(
            f"SELECT COUNT(*) FROM registro_geografico_imoveis WHERE quarteirao IN ({placeholders})",
            quarteiroes,
        ).fetchone()[0]
        total_quarteiroes_destino = conn.execute(
            "SELECT COUNT(*) FROM registro_geografico_quarteiroes WHERE id_localidade=?",
            (destino["id_localidade"],),
        ).fetchone()[0]
        return {
            "backup": str(backup_path) if backup_path else None,
            "destino": destino["nome"],
            "quarteiroes_movidos": len(encontrados),
            "imoveis_movidos": total_imoveis,
            "quarteiroes_ausentes": ausentes,
            "quarteiroes_vazios_criados": novos_vazios,
            "total_quarteiroes_destino": total_quarteiroes_destino,
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migra quarteiroes do RG para Sao Francisco.")
    parser.add_argument("--db", default="endemias.db", help="Caminho do banco SQLite.")
    parser.add_argument("--no-backup", action="store_true", help="Nao cria backup antes da migracao.")
    args = parser.parse_args()
    resumo = migrar(args.db, fazer_backup=not args.no_backup)
    for chave, valor in resumo.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
