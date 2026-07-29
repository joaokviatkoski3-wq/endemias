"""Homologa cadastro, diarios e calendario de Ovitrampas no PostgreSQL."""

import argparse
import csv
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import ovitrampas  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "ovitrampas_armadilhas",
    "ovitrampas_armadilhas_historico",
    "ovitrampas_leituras",
    "ovitrampas_diarios",
    "ovitrampas_diario_armadilhas",
    "ovitrampas_calendario_grupos",
    "ovitrampas_calendario_eventos",
    "ovitrampas_calendario_agentes",
)


class _SharedConnection:
    def __init__(self, conn):
        self._conn = conn
        self.backend = conn.backend

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Testa o nucleo de Ovitrampas sem alterar as tabelas publicas."
        )
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    return parser


def _public_counts(conn):
    tables = [
        row[0]
        for row in conn.execute(
            """SELECT table_name
                 FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_type='BASE TABLE'
                ORDER BY table_name"""
        ).fetchall()
    ]
    return {
        table: conn.execute(
            f"SELECT COUNT(*) FROM public.{table}"
        ).fetchone()[0]
        for table in tables
    }


def _temporary_schema(conn):
    for table in TEMP_TABLES:
        conn.execute(
            f"""CREATE TEMPORARY TABLE {table}
                (LIKE public.{table} INCLUDING ALL)
                ON COMMIT PRESERVE ROWS"""
        )
    conn.commit()


def _write_csv(path, rows):
    fields = [
        "ID",
        "Rua",
        "Numero do logradouro",
        "Complemento",
        "Bairro",
        "Localizacao da ovitrampa",
        "Setor/Distrito da ovitrampa",
        "Responsavel",
        "Quarteirao",
        "Latitude",
        "Longitude",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _test_temporary_data(target):
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        with tempfile.TemporaryDirectory() as tmpdir:
            cadastro = Path(tmpdir) / "cadastro.csv"
            _write_csv(
                cadastro,
                [
                    {
                        "ID": "901",
                        "Rua": "Rua Teste",
                        "Numero do logradouro": "10",
                        "Complemento": "UBS Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Fundos",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Maria",
                        "Quarteirao": "12",
                        "Latitude": "-25.1",
                        "Longitude": "-49.2",
                    },
                    {
                        "ID": "902-A",
                        "Rua": "Rua Teste",
                        "Numero do logradouro": "20",
                        "Complemento": "Escola Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Entrada",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Jose",
                        "Quarteirao": "13",
                        "Latitude": "-25.2",
                        "Longitude": "-49.3",
                    },
                ],
            )
            result = ovitrampas.importar_armadilhas_csv(
                target, cadastro, motivo="Homologacao PostgreSQL", usuario="Teste"
            )
            if result["inseridos"] != 2:
                raise RuntimeError("O cadastro temporario nao inseriu duas armadilhas.")

            _write_csv(
                cadastro,
                [
                    {
                        "ID": "901",
                        "Rua": "Rua Teste Atualizada",
                        "Numero do logradouro": "10",
                        "Complemento": "UBS Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Fundos",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Maria",
                        "Quarteirao": "12",
                        "Latitude": "-25.1",
                        "Longitude": "-49.2",
                    }
                ],
            )
            result = ovitrampas.importar_armadilhas_csv(
                target, cadastro, motivo="Revisao PostgreSQL", usuario="Teste"
            )
            if result["atualizados"] != 1:
                raise RuntimeError("A atualizacao da armadilha temporaria falhou.")

        armadilhas = ovitrampas.listar_armadilhas(
            target, {"busca": "RUA TESTE"}, 10
        )
        if armadilhas["total"] != 2:
            raise RuntimeError("A busca de armadilhas sem diferenca de caixa falhou.")
        if armadilhas["registros"][1]["ovitrampa_id"] != "902-A":
            raise RuntimeError("A ordenacao de IDs alfanumericos divergiu.")

        historico = ovitrampas.historico_armadilha(target, "901")
        if not any(item["campo"] == "rua" for item in historico["alteracoes"]):
            raise RuntimeError("O historico da armadilha nao registrou a alteracao.")

        diario = ovitrampas.salvar_diario(
            target, {"nome": "Diario temporario", "ativo": True}
        )
        id_diario = diario["id_diario"]
        ovitrampas.vincular_armadilha_diario(
            target, {"id_diario": id_diario, "ovitrampa_id": "901"}
        )
        ovitrampas.vincular_armadilha_diario(
            target, {"id_diario": id_diario, "ovitrampa_id": "902-A"}
        )
        detalhe = ovitrampas.reordenar_armadilhas_diario(
            target, id_diario, ["902-A", "901"]
        )
        if [item["ovitrampa_id"] for item in detalhe["registros"]] != [
            "902-A",
            "901",
        ]:
            raise RuntimeError("A nova ordem do diario nao foi persistida.")

        grupo = ovitrampas.salvar_grupo(
            target,
            {
                "nome": "Grupo temporario",
                "localidades": "Tamboara",
                "cor": "#2563eb",
                "ativo": True,
            },
        )
        agente = conn.execute(
            "SELECT id_agente FROM public.agentes WHERE ativo=1 ORDER BY id_agente LIMIT 1"
        ).fetchone()
        agentes = [agente[0]] if agente else []
        evento = ovitrampas.salvar_evento_calendario(
            target,
            {
                "data": "2099-01-10",
                "movimento": "troca",
                "id_grupo": grupo["id_grupo"],
                "ciclo": "Temporario",
                "agentes": agentes,
            },
            usuario_nome="Teste",
        )
        if evento["data"] != "2099-01-10":
            raise RuntimeError("A data do evento temporario divergiu.")
        if agentes and len(evento["agentes"]) != 1:
            raise RuntimeError("O agente do calendario nao foi vinculado.")

        agenda = ovitrampas.eventos_agenda(
            target, "2099-01-01", "2099-01-31"
        )
        if len(agenda) != 1 or agenda[0]["movimento"] != "troca":
            raise RuntimeError("O evento nao apareceu na integracao da Agenda.")

        ovitrampas.excluir_evento_calendario(target, evento["id_evento"])
        ovitrampas.excluir_grupo(target, grupo["id_grupo"])
        ovitrampas.remover_armadilha_diario(target, id_diario, "901")

        after = _public_counts(conn)
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
        return len(before)
    finally:
        db_core.connect = original_connect
        conn.close()


def main():
    args = _parser().parse_args()
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        raise SystemExit(
            "Banco nao autorizado. Use --confirmar-banco com o mesmo nome."
        )
    target = db_core.DatabaseTarget("postgresql", args.database)
    total_publicas = _test_temporary_data(target)
    print(
        "OK: nucleo de Ovitrampas homologado no PostgreSQL; "
        f"{total_publicas} tabelas publicas preservadas."
    )


if __name__ == "__main__":
    main()
