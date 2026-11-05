"""Previa local com massa ficticia; nunca usa credenciais, dados ou portas oficiais."""
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if ROOT == Path('C:/endemias'):
        raise ValueError('A demonstracao exige worktree isolada.')
    runtime = Path(tempfile.mkdtemp(prefix='demonstracao-', dir=ROOT/'.venv'))
    database = runtime/'ficticio.db'
    from scripts.preparar_massa_web_teste import preparar
    preparar(database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite', ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_SECRET_KEY_PATH=str(runtime/'secret.key'),
        ENDEMIAS_LOG_PATH=str(runtime/'demonstracao.log'), ENDEMIAS_ANEXOS_DIR=str(runtime/'anexos'),
        ENDEMIAS_UPLOAD_TEMP=str(runtime/'uploads'), ENDEMIAS_KOBO_CONFIG_PATH=str(runtime/'kobo_config.json'),
        ENDEMIAS_BACKUP_DIR=str(runtime/'backups'), ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime/'completos'),
        ENDEMIAS_AMBIENTE='teste', ENDEMIAS_ACESSO_EXTERNO='0', ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app import create_app
    from app_core import dominios
    from waitress import create_server
    applications = {}
    for sector in ('endemias','ambiental'):
        applications[sector] = create_app({'SETORES_ENABLED':True,'SETOR':sector,
            'SESSION_COOKIE_NAME':'demonstracao_'+sector, 'REQUIRE_SESSION_TOKEN':True,
            'TERMOS_USO_ENABLED':False, 'CSP_REPORT_ONLY':False})
    conn = sqlite3.connect(database)
    try:
        conn.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        conn.execute("UPDATE usuarios SET setor='ambiental' WHERE id_usuario=4")
        conn.commit()
    finally:
        conn.close()
    portal = dominios.portal_application('localhost', external=False)

    @portal.after_request
    def links_locais(response):
        if response.mimetype == 'text/html':
            body = response.get_data(as_text=True)
            body = body.replace('https://endemias.localhost','http://localhost:5012')
            body = body.replace('https://ambiental.localhost','http://localhost:5013')
            body = body.replace('Escolha o setor para entrar com sua conta.',
                'DEMONSTRAÇÃO LOCAL — dados fictícios. Escolha o setor para avaliar.')
            response.set_data(body)
        return response

    applications['portal'] = portal
    servers = []
    try:
        for index, application in enumerate(applications.values()):
            server = create_server(application,host='127.0.0.1',port=5012+index,threads=4,map={})
            servers.append(server)
            threading.Thread(target=server.run,daemon=True).start()
        print('Demonstracao pronta: http://localhost:5014 | somente loopback/dados ficticios.',flush=True)
        threading.Event().wait()
    finally:
        for server in servers:
            for channel in list(server._map.values()):channel.close()
            server.task_dispatcher.shutdown()


if __name__=='__main__':main()
