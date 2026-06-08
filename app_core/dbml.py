"""Geracao de DBML a partir do schema SQLite atual."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name):
    text = str(name or "")
    if _IDENT_RE.match(text):
        return text
    return '"' + text.replace('"', '\\"') + '"'


def _default(value):
    if value is None:
        return None
    return "`" + str(value).replace("`", "\\`") + "`"


def _sqlite_rows(conn, sql, params=()):
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, params).fetchall()


def _table_names(conn):
    rows = _sqlite_rows(
        conn,
        """
        SELECT name
          FROM sqlite_master
         WHERE type='table'
           AND name NOT LIKE 'sqlite_%'
         ORDER BY name
        """,
    )
    return [row["name"] for row in rows]


def _indexes_for_table(conn, table):
    blocks = []
    for index in _sqlite_rows(conn, f"PRAGMA index_list({_ident(table)})"):
        if str(index["origin"]) == "pk":
            continue
        columns = [
            row["name"]
            for row in _sqlite_rows(conn, f"PRAGMA index_info({_ident(index['name'])})")
            if row["name"]
        ]
        if not columns:
            continue
        settings = []
        if index["unique"]:
            settings.append("unique")
        settings.append(f"name: '{index['name']}'")
        columns_txt = ", ".join(_ident(col) for col in columns)
        blocks.append(f"    ({columns_txt}) [{', '.join(settings)}]")
    return blocks


def _primary_key_index(cols):
    pk_cols = sorted((col for col in cols if col["pk"]), key=lambda col: col["pk"])
    if len(pk_cols) <= 1:
        return None
    columns_txt = ", ".join(_ident(col["name"]) for col in pk_cols)
    return f"    ({columns_txt}) [pk]"


def gerar_dbml(db_path, project_name="Endemias"):
    """Retorna o schema SQLite em formato DBML."""
    path = Path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        linhas = [
            f"Project {_ident(project_name)} {{",
            f"  database_type: 'SQLite'",
            f"  Note: 'Gerado automaticamente em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'",
            "}",
            "",
        ]

        refs = []
        for table in _table_names(conn):
            linhas.append(f"Table {_ident(table)} {{")
            cols = _sqlite_rows(conn, f"PRAGMA table_info({_ident(table)})")
            pk_cols = [col["name"] for col in cols if col["pk"]]
            for col in cols:
                attrs = []
                if col["pk"] and len(pk_cols) == 1:
                    attrs.append("pk")
                if col["notnull"]:
                    attrs.append("not null")
                default = _default(col["dflt_value"])
                if default is not None:
                    attrs.append(f"default: {default}")
                attrs_txt = f" [{', '.join(attrs)}]" if attrs else ""
                tipo = col["type"] or "text"
                linhas.append(f"  {_ident(col['name'])} {tipo}{attrs_txt}")

            indexes = []
            pk_index = _primary_key_index(cols)
            if pk_index:
                indexes.append(pk_index)
            indexes.extend(_indexes_for_table(conn, table))
            if indexes:
                linhas.append("")
                linhas.append("  Indexes {")
                linhas.extend(indexes)
                linhas.append("  }")
            linhas.append("}")
            linhas.append("")

            for fk in _sqlite_rows(conn, f"PRAGMA foreign_key_list({_ident(table)})"):
                refs.append(
                    f"Ref: {_ident(table)}.{_ident(fk['from'])} > "
                    f"{_ident(fk['table'])}.{_ident(fk['to'])}"
                )

        if refs:
            linhas.extend(sorted(refs))
            linhas.append("")

        return "\n".join(linhas)
    finally:
        conn.close()
