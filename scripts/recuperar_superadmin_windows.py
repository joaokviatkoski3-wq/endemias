"""Recuperacao local do unico superadmin, sem rota web ou senha em argumentos."""

import argparse
import ctypes
from datetime import datetime
import getpass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def redefinir(connection, uid, usuario, password_hash):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (1840364333,))
        cursor.execute("UPDATE usuarios SET senha_hash=%s WHERE id_usuario=%s AND usuario=%s AND nivel='superadmin' AND ativo=1",
                       (password_hash, uid, usuario))
        if cursor.rowcount != 1:
            raise ValueError("Conta mudou durante a recuperacao.")
        cursor.execute("""INSERT INTO auditoria_eventos
            (acao,entidade,entidade_id,usuario_id,usuario_nome,ip,detalhes_json,criado_em)
            VALUES ('superadmin_recuperacao_local','usuarios',%s,NULL,'Operador Windows','local',%s,%s)""",
            (str(uid), json.dumps({"usuario": usuario, "metodo": "console_windows"}), datetime.now().isoformat()))
    connection.commit()


def main():
    parser = argparse.ArgumentParser(description="Recuperacao local do superadmin")
    parser.add_argument("--usuario", required=True)
    args = parser.parse_args()
    if ROOT != Path(r"C:\endemias") or not ctypes.windll.shell32.IsUserAnAdmin():
        print("Execute no computador oficial, como administrador do Windows.")
        return 1
    from scripts.ativar_acesso_externo_windows import connect
    from app_core import auth
    config = json.loads(Path(r"C:\ProgramData\EndemiasWeb\config.json").read_text(encoding="utf-8"))
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id_usuario,usuario FROM usuarios WHERE nivel='superadmin' AND ativo=1")
            rows = cursor.fetchall()
        connection.rollback()
        if len(rows) != 1 or rows[0][1] != args.usuario:
            raise ValueError("Conta informada nao corresponde ao unico superadmin ativo.")
        uid = rows[0][0]
        print("Recuperacao local da conta: " + args.usuario)
        if input("Para confirmar, digite RECUPERAR " + args.usuario + ": ") != "RECUPERAR " + args.usuario:
            print("Cancelado. Nenhuma senha alterada.")
            return 1
        password = getpass.getpass("Nova senha (nao sera exibida): ")
        confirmation = getpass.getpass("Confirme a nova senha: ")
        if password != confirmation or not auth.senha_valida(password) or len(password) > 1024:
            raise ValueError("As senhas devem coincidir e ter entre 10 e 1024 caracteres.")
        password_hash = auth.hash_senha(password)
        password = confirmation = None
        redefinir(connection, uid, args.usuario, password_hash)
        print("Senha redefinida. Os acessos anteriores foram invalidados. Entre normalmente pelo navegador.")
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print("Cancelado. Nenhuma senha alterada.")
        raise SystemExit(1)
    except Exception as error:
        print("Recuperacao nao concluida (" + type(error).__name__ + "). Confira a conta e execute localmente como administrador.")
        raise SystemExit(1)
