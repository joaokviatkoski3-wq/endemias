"""Falha quando SQL exclusivo do SQLite aparece fora do inventario revisado."""

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "pragma": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "executescript": re.compile(r"\.executescript\s*\("),
    "lastrowid": re.compile(r"\blastrowid\b"),
    "insert_or": re.compile(r"\bINSERT\s+OR\s+(?:IGNORE|REPLACE)\b", re.IGNORECASE),
    "group_concat": re.compile(r"\bGROUP_CONCAT\s*\(", re.IGNORECASE),
    "collate_nocase": re.compile(r"\bCOLLATE\s+NOCASE\b", re.IGNORECASE),
    "julianday": re.compile(r"\bjulianday\s*\(", re.IGNORECASE),
    "date_modifier": re.compile(r"\bdate\s*\(\s*['\"]now['\"]", re.IGNORECASE),
    "strftime_sql": re.compile(r"(?<!\.)\bstrftime\s*\(\s*['\"]%", re.IGNORECASE),
}

# Cada entrada foi conferida no fechamento funcional da camada dual. A
# classificacao detalhada e os motivos ficam em
# docs/POSTGRESQL_AUDITORIA_SQL_FINAL.md.
ALLOWED = {
    "criar_banco.py": {"pragma", "sqlite_master", "executescript"},
    "etl.py": {"group_concat"},
    "gerar_consolidado.py": {"group_concat"},
    "app_core/agentes.py": {"pragma", "sqlite_master", "lastrowid"},
    "app_core/amostras_animais.py": {"executescript"},
    "app_core/backup.py": {"pragma"},
    "app_core/boletim_mensal.py": {"executescript"},
    "app_core/bri.py": {"pragma", "executescript"},
    "app_core/dashboard.py": {"julianday", "strftime_sql"},
    "app_core/db.py": {"pragma", "sqlite_master", "executescript", "lastrowid"},
    "app_core/dbml.py": {"pragma", "sqlite_master"},
    "app_core/diagnostico.py": {"pragma", "sqlite_master", "date_modifier"},
    "app_core/esporotricose.py": {
        "pragma", "sqlite_master", "executescript", "lastrowid",
        "insert_or", "group_concat",
    },
    "app_core/laboratorio.py": {"group_concat"},
    "app_core/laboratorio_lancamentos.py": {"pragma", "sqlite_master"},
    "app_core/meteorologia.py": {"executescript", "insert_or", "strftime_sql"},
    "app_core/ovitrampas.py": {
        "pragma", "sqlite_master", "executescript", "insert_or", "group_concat",
    },
    "app_core/ovitrampas_laboratorio.py": {"pragma", "executescript", "julianday"},
    "app_core/pontos_estrategicos.py": {"pragma", "sqlite_master", "executescript", "julianday"},
    "app_core/postgresql_data_migration.py": {"pragma"},
    "app_core/recolhimentos.py": {"executescript", "lastrowid", "group_concat"},
    "app_core/registro_geografico.py": {"pragma", "executescript", "lastrowid", "insert_or", "group_concat"},
    "app_core/sqlite_inventory.py": {"pragma", "sqlite_master"},
    "app_core/sqlite_maintenance.py": {"pragma", "sqlite_master"},
    "app_core/usuarios.py": {"lastrowid"},
    "blueprints/acoes_setor.py": {"pragma", "sqlite_master", "executescript", "group_concat"},
    "blueprints/admin.py": {"pragma", "sqlite_master"},
    "blueprints/agenda.py": {"pragma", "sqlite_master", "executescript", "group_concat"},
    "blueprints/exportacoes.py": {"group_concat"},
    "blueprints/laboratorio_lancamentos.py": {"group_concat", "julianday"},
    "blueprints/notificacoes.py": {"group_concat"},
    "blueprints/relatorio_agente.py": {"group_concat", "julianday", "strftime_sql"},
}


def _files():
    for pasta in (ROOT / "app_core", ROOT / "blueprints"):
        yield from pasta.rglob("*.py")
    for nome in ("criar_banco.py", "etl.py", "gerar_consolidado.py"):
        yield ROOT / nome


def main():
    encontrados = []
    falhas = []
    for path in sorted(_files()):
        relative = path.relative_to(ROOT).as_posix()
        texto = path.read_text(encoding="utf-8")
        permitidos = ALLOWED.get(relative, set())
        for linha, conteudo in enumerate(texto.splitlines(), start=1):
            for categoria, pattern in PATTERNS.items():
                if not pattern.search(conteudo):
                    continue
                encontrados.append((relative, linha, categoria))
                if categoria not in permitidos:
                    falhas.append((relative, linha, categoria))

    arquivos_encontrados = {item[0] for item in encontrados}
    obsoletos = sorted(set(ALLOWED) - arquivos_encontrados)
    for relative, linha, categoria in encontrados:
        print(f"{relative}:{linha}: {categoria}")
    if falhas:
        print("\n[ERRO] Ocorrencias SQLite sem classificacao:", file=sys.stderr)
        for relative, linha, categoria in falhas:
            print(f"- {relative}:{linha}: {categoria}", file=sys.stderr)
        return 1
    if obsoletos:
        print("\n[ERRO] Entradas obsoletas no inventario:", file=sys.stderr)
        for relative in obsoletos:
            print(f"- {relative}", file=sys.stderr)
        return 1
    print(
        f"\n[OK] {len(encontrados)} ocorrencias em "
        f"{len(arquivos_encontrados)} arquivos estao classificadas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
