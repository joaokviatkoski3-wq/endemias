"""Migracao/revogacao em PostgreSQL descartavel; nunca na porta oficial."""
import json
import os
from pathlib import Path
import sys
from datetime import timedelta

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    if (os.environ.get('ENDEMIAS_PG_HOST')!='127.0.0.1' or os.environ.get('ENDEMIAS_PG_PORT','5432')=='5432'
            or os.environ.get('ENDEMIAS_PG_DATABASE')!='endemias_teste'):
        raise ValueError('Exige banco descartavel endemias_teste fora da porta oficial.')
    from flask import Flask,session
    from app_core import db,auth,sessoes
    target=db.DatabaseTarget('postgresql','endemias_teste')
    conn=db.connect(target)
    try:
        assert conn.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
        conn.execute('CREATE TABLE usuarios(id_usuario BIGINT PRIMARY KEY,ativo BIGINT,senha_hash TEXT,nivel TEXT)')
        password=auth.hash_senha('SenhaInteiramenteFicticia!')
        conn.execute("INSERT INTO usuarios VALUES(1,1,?,'usuario')",(password,))
        conn.execute((ROOT/'migrations/postgresql/0034_sessoes_revogaveis.sql').read_text(encoding='utf-8'))
        conn.commit()
        application=Flask('ensaio-sessoes')
        application.secret_key='chave-inteiramente-ficticia-do-ensaio'
        application.config.update(REQUIRE_SESSION_TOKEN=True,PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
        user={'id_usuario':1,'senha_hash':password}
        def issue():
            with application.test_request_context():
                return {'uid':1,'auth_token':auth.token_sessao(password),'sessao_id':sessoes.criar(target,user)}
        def check(cookie):
            with application.test_request_context():
                session.update(cookie)
                return auth.usuario_atual(lambda sql,p=():db.query_one(target,sql,p))
        one,two=issue(),issue()
        assert check(one) and check(two)
        with application.test_request_context():
            session.update(one);sessoes.revogar(target)
        assert check(one) is None and check(two)
        conn.execute('UPDATE usuarios_sessoes SET expira_em=0');conn.commit()
        assert check(two) is None
        three=issue()
        assert check(three)
        conn.execute('UPDATE usuarios SET senha_hash=?',(auth.hash_senha('OutraSenhaFicticia!'),));conn.commit()
        assert check(three) is None
        print(json.dumps({'ok':True,'migracao0034':True,'revogacao_persistente':True,'aparelhos_independentes':True,'expiracao':True,'troca_senha_invalida':True}))
    finally:
        conn.close()


if __name__=='__main__':
    main()
