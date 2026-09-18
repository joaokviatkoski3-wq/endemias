"""Homologa histórico de imóveis de Esporotricose sem alterar dados públicos."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import esporotricose as esporo  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "localidades",
    "esporotricose_visitas",
    "esporotricose_animais",
    "esporotricose_imoveis",
    "esporotricose_visita_imoveis",
)


class SharedConnection:
    def __init__(self, conn):
        self._conn = conn
        self.backend = conn.backend

    def close(self):
        pass

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *args):
        return self._conn.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--database", default=SAFE_DATABASE)
    value.add_argument("--confirmar-banco")
    return value


def public_counts(conn):
    tables = [row[0] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
    )]
    return {name: conn.execute(f"SELECT COUNT(*) FROM public.{name}").fetchone()[0] for name in tables}


def main():
    args = parser().parse_args()
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        raise SystemExit("Banco não autorizado. Informe --confirmar-banco para outro banco.")
    target = db_core.DatabaseTarget("postgresql", args.database)
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        antes = public_counts(conn)
        conn.rollback()
        for table in TEMP_TABLES:
            conn.execute(f"CREATE TEMPORARY TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT PRESERVE ROWS")
        conn.commit()
        conn.execute("INSERT INTO localidades(id_localidade,nome,cod_localidade) VALUES (910101,'Localidade Teste Esporo','TEE')")
        visitas = [
            ("teste-esporo-1", "uuid-esporo-1", "2026-09-01", "Localidade Teste Esporo", 44, "Rua das Flores", "10", "Maria"),
            ("teste-esporo-2", "uuid-esporo-2", "2026-09-08", "Localidade Teste Esporo", 44, "R. das Flores", "10", "José"),
        ]
        conn.executemany(
            """INSERT INTO esporotricose_visitas
                   (id_visita,kobo_uuid,data,localidade,quarteirao,logradouro,numero,morador,visita,origem_estrutura,processado_em)
                 VALUES (?,?,?,?,?,?,?,?,?,'nova','2026-09-08T10:00:00')""",
            [(*row, "Normal") for row in visitas],
        )
        conn.executemany(
            "INSERT INTO esporotricose_animais(id_animal,id_visita,kobo_uuid,especie,nome,processado_em) VALUES (?,?,?,?,?,'2026-09-08T10:00:00')",
            [("teste-animal-1", "teste-esporo-1", "uuid-animal-1", "Gato", "Pipoca"), ("teste-animal-2", "teste-esporo-2", "uuid-animal-2", "Cão", "Luna")],
        )
        conn.commit()
        db_core.connect = lambda unused: SharedConnection(conn)
        previa = esporo.previsualizar_vinculos_imoveis(target)
        if previa["grupos_com_historico"] != 1:
            raise RuntimeError("A prévia não agrupou o endereço equivalente.")
        resultado = esporo.vincular_visitas_exatas(target)
        if resultado["vinculadas"] != 2:
            raise RuntimeError("As visitas exatas não foram vinculadas.")
        imoveis = esporo.listar_imoveis(target)
        if imoveis["total"] != 1 or imoveis["registros"][0]["animais"] != 2:
            raise RuntimeError("O resumo do imóvel no PostgreSQL divergiu.")
        detalhe = esporo.detalhe_imovel(target, imoveis["registros"][0]["id_imovel"])
        if len(detalhe["visitas"]) != 2 or len(detalhe["tutores"]) != 2:
            raise RuntimeError("O histórico de visitas ou tutores divergiu.")
        depois = public_counts(conn)
        if antes != depois:
            raise RuntimeError("Uma tabela pública foi alterada.")
        print(f"OK: histórico de imóveis homologado; {len(antes)} tabelas públicas preservadas.")
    finally:
        db_core.connect = original_connect
        conn.close()


if __name__ == "__main__":
    main()
