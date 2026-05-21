import argparse
import re
import sqlite3
from pathlib import Path


IGNORED_PREFIXES = ("sqlite_",)
ROOT = Path(__file__).resolve().parents[1]


def dbml_name(name):
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    return f'"{name}"'


def dbml_type(sqlite_type):
    raw = (sqlite_type or "text").strip()
    return raw.lower() if raw else "text"


def singularize(name):
    if name.endswith("oes"):
        return name[:-3] + "ao"
    if name.endswith("ais"):
        return name[:-3] + "al"
    if name.endswith("is"):
        return name[:-2] + "il"
    if name.endswith("s"):
        return name[:-1]
    return name


def candidate_table_names(column_name):
    names = []
    if column_name.startswith("id_"):
        base = column_name[3:]
        names.extend([base, f"{base}s"])
    if column_name.endswith("_id"):
        base = column_name[:-3]
        names.extend([base, f"{base}s"])
    return names


def build_table_lookup(table_names):
    lookup = {}
    for table in table_names:
        lookup[table] = table
        lookup[singularize(table)] = table
    return lookup


def table_row_count(conn, table):
    try:
        return conn.execute(f"select count(*) from {dbml_name(table)}").fetchone()[0]
    except sqlite3.DatabaseError:
        return None


def load_schema(conn):
    rows = conn.execute(
        """
        select name
          from sqlite_master
         where type = 'table'
           and name not like 'sqlite_%'
         order by name
        """
    ).fetchall()
    tables = [row[0] for row in rows if not row[0].startswith(IGNORED_PREFIXES)]
    columns = {
        table: conn.execute(f"pragma table_info({dbml_name(table)})").fetchall()
        for table in tables
    }
    declared_refs = []
    for table in tables:
        for fk in conn.execute(f"pragma foreign_key_list({dbml_name(table)})").fetchall():
            declared_refs.append((table, fk[3], fk[2], fk[4], "declarada no SQLite"))
    return tables, columns, declared_refs


def primary_key_by_table(columns):
    primary_keys = {}
    for table, table_columns in columns.items():
        pk_columns = [name for _, name, _, _, _, pk in table_columns if pk]
        primary_keys[table] = pk_columns[0] if len(pk_columns) == 1 else "id"
    return primary_keys


def infer_refs(tables, columns, declared_refs):
    lookup = build_table_lookup(tables)
    primary_keys = primary_key_by_table(columns)
    known = {(src, src_col, dst, dst_col) for src, src_col, dst, dst_col, _ in declared_refs}
    declared_source_columns = {(src, src_col) for src, src_col, _, _, _ in declared_refs}
    refs = list(declared_refs)

    for table, table_columns in columns.items():
        for _, column_name, _, _, _, pk in table_columns:
            if pk or (table, column_name) in declared_source_columns:
                continue
            for candidate in candidate_table_names(column_name):
                target = lookup.get(candidate)
                if not target or target == table:
                    continue
                ref = (table, column_name, target, primary_keys[target])
                if ref not in known:
                    refs.append((*ref, "inferida pelo nome da coluna"))
                    known.add(ref)
                break
    return refs


def render_dbml(conn, tables, columns, refs):
    lines = [
        "// Schema gerado automaticamente a partir de endemias.db.",
        "// Para visualizar: acesse https://dbdiagram.io/ > New Diagram > cole este conteudo.",
        "// Referencias marcadas como inferidas dependem do nome das colunas e devem ser revisadas visualmente.",
        "",
    ]

    for table in tables:
        count = table_row_count(conn, table)
        note = f" [note: 'Registros atuais: {count}']" if count is not None else ""
        lines.append(f"Table {dbml_name(table)}{note} {{")
        for _, name, col_type, notnull, _, pk in columns[table]:
            settings = []
            if pk:
                settings.append("pk")
            if notnull:
                settings.append("not null")
            suffix = f" [{', '.join(settings)}]" if settings else ""
            lines.append(f"  {dbml_name(name)} {dbml_type(col_type)}{suffix}")
        lines.append("}")
        lines.append("")

    for src_table, src_col, dst_table, dst_col, note in refs:
        lines.append(
            f"Ref: {dbml_name(src_table)}.{dbml_name(src_col)} > "
            f"{dbml_name(dst_table)}.{dbml_name(dst_col)} // {note}"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Gera DBML para uso no dbdiagram.io.")
    parser.add_argument("--db", default=str(ROOT / "endemias.db"), help="Caminho do banco SQLite.")
    parser.add_argument("--out", default=str(ROOT / "docs" / "schema_endemias.dbml"), help="Arquivo DBML de saida.")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_path = Path(args.out)
    if not db_path.exists():
        raise SystemExit(f"Banco SQLite nao encontrado: {db_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db_uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(db_uri, uri=True) as conn:
        tables, columns, declared_refs = load_schema(conn)
        refs = infer_refs(tables, columns, declared_refs)
        out_path.write_text(render_dbml(conn, tables, columns, refs), encoding="utf-8")

    print(f"DBML gerado em {out_path}")


if __name__ == "__main__":
    main()
