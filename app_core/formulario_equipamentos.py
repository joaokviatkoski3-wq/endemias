"""Catálogo territorial de equipamentos públicos usado pelos formulários."""

import csv
import json
from pathlib import Path

from app_core.formulario_campo import chave

FONTE = Path(__file__).resolve().parents[1] / "dados_referencia" / "equipamentos_publicos.csv"
CATEGORIAS = {
    "escolas_municipais": "Escolas Municipais",
    "cmeis": "CMEIs",
    "unidades_de_saude": "Unidades de Saúde",
    "outros_equipamentos_publicos": "Outros equipamentos públicos",
}
SAUDE_APOIO = {"saudeecultura", "transporteeurgencia", "centraldeabastecimento", "endemias"}


def categoria(row):
    tipo = chave(row["tipo"])
    if tipo in {"escolamunicipal", "escolaruralmunicipal"}:
        return "escolas_municipais"
    if tipo == "cmei":
        return "cmeis"
    if tipo == "saude" and chave(row["subtipo"]) not in SAUDE_APOIO:
        return "unidades_de_saude"
    return "outros_equipamentos_publicos"


def registros(path=FONTE):
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["uid"] != "AT-024":
                yield (row["uid"], categoria(row), row["nome"], row["logradouro"],
                       row["numero"], row["bairro_loteamento"], float(row["latitude"]),
                       float(row["longitude"]), json.dumps(row, ensure_ascii=False))


def importar(conn):
    conn.executemany(
        """INSERT INTO equipamentos_publicos
           (uid,categoria,nome,logradouro,numero,bairro,latitude,longitude,fonte_json)
           VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (uid) DO NOTHING""",
        list(registros()),
    )


def ensure_sqlite(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS equipamentos_publicos (
        uid TEXT PRIMARY KEY,categoria TEXT NOT NULL,nome TEXT NOT NULL,
        logradouro TEXT,numero TEXT,bairro TEXT,latitude REAL NOT NULL,longitude REAL NOT NULL,
        fonte_json TEXT NOT NULL)""")
    if not conn.execute("SELECT 1 FROM equipamentos_publicos LIMIT 1").fetchone():
        importar(conn)
    for table, name in (("visitas", "protocolo_e_ouve"), ("visitas", "ovitrampas_bloqueio"),
                        ("bri_registros", "equipamento_uid"), ("recolhimentos", "logradouro"),
                        ("recolhimentos", "quarteirao"), ("recolhimentos", "numero")):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if columns and name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")
