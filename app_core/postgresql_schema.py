"""Geracao deterministica do esquema PostgreSQL a partir do inventario SQLite."""

import hashlib
import re


TYPE_MAP = {
    "TEXT": "text",
    "INTEGER": "bigint",
    "REAL": "double precision",
    "DATE": "date",
    "TIME": "time without time zone",
    "VARCHAR(20)": "varchar(20)",
}


def normalize_identifier(value):
    return str(value).lower()


def quote_identifier(value):
    return '"' + normalize_identifier(value).replace('"', '""') + '"'


def database_object_name(prefix, *parts):
    raw = "_".join(
        [normalize_identifier(prefix)]
        + [normalize_identifier(part) for part in parts if str(part)]
    )
    raw = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    if len(raw) <= 63:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{raw[:52]}_{digest}"


def _keyword_parentheses(sql, keyword):
    """Extrai expressoes parentetizadas ignorando strings e comentarios SQL."""
    keyword = keyword.upper()
    results = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]
        if char == "'":
            index = _skip_quoted(sql, index, "'")
            continue
        if char == '"':
            index = _skip_quoted(sql, index, '"')
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue

        end_keyword = index + len(keyword)
        if (
            sql[index:end_keyword].upper() == keyword
            and (index == 0 or not (sql[index - 1].isalnum() or sql[index - 1] == "_"))
            and (
                end_keyword >= length
                or not (sql[end_keyword].isalnum() or sql[end_keyword] == "_")
            )
        ):
            cursor = end_keyword
            while cursor < length and sql[cursor].isspace():
                cursor += 1
            if cursor < length and sql[cursor] == "(":
                expression, cursor = _balanced_parentheses(sql, cursor)
                results.append(expression)
                index = cursor
                continue
        index += 1
    return results


def _skip_quoted(sql, start, quote):
    index = start + 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise ValueError("String SQL sem fechamento no esquema SQLite.")


def _balanced_parentheses(sql, start):
    depth = 0
    index = start
    expression_start = start + 1
    while index < len(sql):
        char = sql[index]
        if char == "'":
            index = _skip_quoted(sql, index, "'")
            continue
        if char == '"':
            index = _skip_quoted(sql, index, '"')
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = len(sql) if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            index = len(sql) if end < 0 else end + 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return sql[expression_start:index].strip(), index + 1
        index += 1
    raise ValueError("Parenteses SQL sem fechamento no esquema SQLite.")


def extract_check_expressions(create_sql):
    return _keyword_parentheses(create_sql or "", "CHECK")


def _where_expression(create_sql):
    sql = create_sql or ""
    index = 0
    while index < len(sql):
        if sql[index] == "'":
            index = _skip_quoted(sql, index, "'")
            continue
        if sql[index] == '"':
            index = _skip_quoted(sql, index, '"')
            continue
        end = index + 5
        if (
            sql[index:end].upper() == "WHERE"
            and (index == 0 or not (sql[index - 1].isalnum() or sql[index - 1] == "_"))
            and (end >= len(sql) or not (sql[end].isalnum() or sql[end] == "_"))
        ):
            return sql[end:].strip().rstrip(";").strip()
        index += 1
    return None


def _postgres_type(column):
    declared = (column.get("declared_type") or "").upper()
    if declared not in TYPE_MAP:
        raise ValueError(
            f"Tipo SQLite sem conversao PostgreSQL: {declared or '(vazio)'}"
        )
    return TYPE_MAP[declared]


def _primary_key_columns(table):
    return [
        column["name"]
        for column in sorted(
            table["columns"],
            key=lambda item: item["primary_key_position"] or 999,
        )
        if column["primary_key_position"]
    ]


def _identity_column(table):
    primary_key = _primary_key_columns(table)
    if (
        len(primary_key) == 1
        and "AUTOINCREMENT" in (table.get("create_sql") or "").upper()
    ):
        return primary_key[0]
    return None


def _unique_constraints(table):
    constraints = []
    seen = set()
    primary_key = tuple(_primary_key_columns(table))
    for index in table["indexes"]:
        columns = tuple(index["columns"])
        if (
            index["origin"] != "u"
            or not columns
            or columns == primary_key
            or columns in seen
        ):
            continue
        seen.add(columns)
        constraints.append(columns)
    return sorted(constraints)


def _explicit_indexes(table):
    protected = {tuple(_primary_key_columns(table))}
    protected.update(_unique_constraints(table))
    indexes = []
    signatures = set()
    for index in sorted(table["indexes"], key=lambda item: item["name"]):
        columns = tuple(index["columns"])
        if index["origin"] != "c" or not columns:
            continue
        if not index["partial"] and columns in protected:
            continue
        signature = (bool(index["unique"]), columns, _where_expression(index["create_sql"]))
        if signature in signatures:
            continue
        signatures.add(signature)
        indexes.append(
            {
                "name": database_object_name("", index["name"]),
                "unique": bool(index["unique"]),
                "columns": columns,
                "where": _where_expression(index["create_sql"]),
            }
        )
    return indexes


def _foreign_key_groups(table):
    groups = {}
    for foreign_key in table["foreign_keys"]:
        groups.setdefault(foreign_key["id"], []).append(foreign_key)
    return [
        sorted(group, key=lambda item: item["position"])
        for _, group in sorted(groups.items())
    ]


def expected_summary(inventory):
    tables = inventory["tables"]
    return {
        "tables": len(tables),
        "columns": sum(len(table["columns"]) for table in tables),
        "primary_keys": sum(bool(_primary_key_columns(table)) for table in tables),
        "unique_constraints": sum(
            len(_unique_constraints(table)) for table in tables
        ),
        "foreign_keys": sum(
            len(_foreign_key_groups(table)) for table in tables
        ),
        "check_constraints": sum(
            len(extract_check_expressions(table.get("create_sql")))
            for table in tables
        ),
        "identity_columns": sum(
            bool(_identity_column(table)) for table in tables
        ),
        "explicit_indexes": sum(
            len(_explicit_indexes(table)) for table in tables
        ),
    }


def expected_columns(inventory):
    result = {}
    for table in inventory["tables"]:
        primary_key = set(_primary_key_columns(table))
        for column in table["columns"]:
            result[
                (
                    normalize_identifier(table["name"]),
                    normalize_identifier(column["name"]),
                )
            ] = {
                "type": (
                    "character varying"
                    if (column.get("declared_type") or "").upper() == "VARCHAR(20)"
                    else _postgres_type(column)
                ),
                "max_length": (
                    20
                    if (column.get("declared_type") or "").upper() == "VARCHAR(20)"
                    else None
                ),
                "has_default": column["default"] is not None,
                "nullable": not (
                    column["not_null"] or column["name"] in primary_key
                ),
                "identity": column["name"] == _identity_column(table),
            }
    return result


def expected_constraint_names(inventory):
    result = {
        "p": set(),
        "u": set(),
        "f": set(),
        "c": set(),
    }
    for table in inventory["tables"]:
        if _primary_key_columns(table):
            result["p"].add(database_object_name("pk", table["name"]))
        for columns in _unique_constraints(table):
            result["u"].add(
                database_object_name("uq", table["name"], *columns)
            )
        for group in _foreign_key_groups(table):
            first = group[0]
            result["f"].add(
                database_object_name(
                    "fk",
                    table["name"],
                    *(item["source_column"] for item in group),
                    first["target_table"],
                )
            )
        for position, _ in enumerate(
            extract_check_expressions(table.get("create_sql")),
            start=1,
        ):
            result["c"].add(
                database_object_name("ck", table["name"], f"{position:02d}")
            )
    return result


def expected_explicit_index_names(inventory):
    return {
        index["name"]
        for table in inventory["tables"]
        for index in _explicit_indexes(table)
    }


def generate_schema_sql(inventory):
    lines = [
        "-- Endemias - esquema PostgreSQL inicial",
        "-- Gerado deterministicamente a partir do inventario estrutural SQLite.",
        "-- Nao contem dados do sistema.",
        "",
    ]

    for table in sorted(inventory["tables"], key=lambda item: item["name"]):
        definitions = []
        identity_column = _identity_column(table)
        for column in sorted(table["columns"], key=lambda item: item["position"]):
            parts = [
                quote_identifier(column["name"]),
                _postgres_type(column),
            ]
            if column["name"] == identity_column:
                parts.append("GENERATED BY DEFAULT AS IDENTITY")
            if column["not_null"]:
                parts.append("NOT NULL")
            if column["default"] is not None:
                parts.append(f"DEFAULT {column['default']}")
            definitions.append("    " + " ".join(parts))

        primary_key = _primary_key_columns(table)
        if primary_key:
            name = database_object_name("pk", table["name"])
            columns = ", ".join(quote_identifier(item) for item in primary_key)
            definitions.append(
                f"    CONSTRAINT {quote_identifier(name)} PRIMARY KEY ({columns})"
            )

        for columns in _unique_constraints(table):
            name = database_object_name("uq", table["name"], *columns)
            quoted = ", ".join(quote_identifier(item) for item in columns)
            definitions.append(
                f"    CONSTRAINT {quote_identifier(name)} UNIQUE ({quoted})"
            )

        for position, expression in enumerate(
            extract_check_expressions(table.get("create_sql")),
            start=1,
        ):
            name = database_object_name("ck", table["name"], f"{position:02d}")
            definitions.append(
                f"    CONSTRAINT {quote_identifier(name)} CHECK ({expression})"
            )

        lines.append(f"CREATE TABLE {quote_identifier(table['name'])} (")
        lines.append(",\n".join(definitions))
        lines.append(");")
        lines.append("")

    lines.append("-- Chaves estrangeiras sao adicionadas depois de todas as tabelas.")
    for table in sorted(inventory["tables"], key=lambda item: item["name"]):
        for group in _foreign_key_groups(table):
            first = group[0]
            source_columns = [item["source_column"] for item in group]
            target_columns = [item["target_column"] for item in group]
            name = database_object_name(
                "fk",
                table["name"],
                *source_columns,
                first["target_table"],
            )
            source_sql = ", ".join(
                quote_identifier(item) for item in source_columns
            )
            target_sql = ", ".join(
                quote_identifier(item) for item in target_columns
            )
            statement = (
                f"ALTER TABLE {quote_identifier(table['name'])} "
                f"ADD CONSTRAINT {quote_identifier(name)} "
                f"FOREIGN KEY ({source_sql}) "
                f"REFERENCES {quote_identifier(first['target_table'])} "
                f"({target_sql})"
            )
            if first["on_update"] != "NO ACTION":
                statement += f" ON UPDATE {first['on_update']}"
            if first["on_delete"] != "NO ACTION":
                statement += f" ON DELETE {first['on_delete']}"
            lines.append(statement + ";")
    lines.append("")

    lines.append("-- Indices explicitos; redundancias com PK/UNIQUE foram removidas.")
    for table in sorted(inventory["tables"], key=lambda item: item["name"]):
        for index in _explicit_indexes(table):
            unique = "UNIQUE " if index["unique"] else ""
            columns = ", ".join(
                quote_identifier(item) for item in index["columns"]
            )
            statement = (
                f"CREATE {unique}INDEX {quote_identifier(index['name'])} "
                f"ON {quote_identifier(table['name'])} ({columns})"
            )
            if index["where"]:
                statement += f" WHERE {index['where']}"
            lines.append(statement + ";")
    lines.append("")
    return "\n".join(lines)
