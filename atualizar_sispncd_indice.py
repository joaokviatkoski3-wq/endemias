import argparse
import json
import os

from app_core import sispncd_indice


def main():
    parser = argparse.ArgumentParser(description="Atualiza visitas.SISPNCD a partir de INDICE_SISPNCD.xlsx.")
    parser.add_argument("--indice", default="INDICE_SISPNCD.xlsx")
    parser.add_argument("--db", default="endemias.db")
    parser.add_argument("--aplicar", action="store_true", help="Aplica a atualizacao. Sem isso, faz apenas previa.")
    args = parser.parse_args()

    if not os.path.exists(args.indice):
        raise SystemExit(f"Indice nao encontrado: {args.indice}")
    if not os.path.exists(args.db):
        raise SystemExit(f"Banco nao encontrado: {args.db}")

    if args.aplicar:
        resultado = sispncd_indice.aplicar(args.db, args.indice)
    else:
        resultado = sispncd_indice.previsualizar(args.db, args.indice)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
