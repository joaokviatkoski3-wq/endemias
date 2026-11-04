import contextlib
import csv
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import criar_banco
from app_core import auth, db, sessoes
from app_core.csv_seguranca import campo_csv


class SessoesSegurancaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name)/'ficticio.db')
        with patch.object(criar_banco, 'BANCO', self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        self.password = 'SenhaFicticiaSegura!'
        c = sqlite3.connect(self.path)
        c.execute('UPDATE usuarios SET senha_hash=? WHERE id_usuario=1', (auth.hash_senha(self.password),))
        c.commit(); c.close()
        self.app = app.create_app({'TESTING':True, 'DB_PATH':self.path, 'WTF_CSRF_ENABLED':False, 'REQUIRE_SESSION_TOKEN':True})

    def login(self):
        client = self.app.test_client()
        self.assertEqual(client.post('/login', data={'usuario':'admin','senha':self.password}).status_code,302)
        return client

    def test_logout_revoga_copia_cookie_sem_encerrar_outro_aparelho(self):
        first, other = self.login(), self.login()
        stolen = first.get_cookie('session').value
        self.assertEqual(first.get('/api/bri').status_code,200)
        self.assertEqual(first.post('/logout').status_code,302)
        attacker = self.app.test_client()
        attacker.set_cookie('session', stolen)
        self.assertEqual(attacker.get('/api/bri').status_code,302)
        self.assertEqual(other.get('/api/bri').status_code,200)
        self.assertEqual(attacker.post('/api/presenca').status_code,302)

    def test_cookie_antigo_sem_registro_nao_entra_em_producao(self):
        client = self.app.test_client()
        with self.app.app_context(), client.session_transaction() as s:
            s.update(uid=1, auth_token=auth.token_sessao(db.query_one(self.path,'SELECT senha_hash FROM usuarios WHERE id_usuario=1')['senha_hash']))
        self.assertEqual(client.get('/api/bri').status_code,302)

    def test_sessao_ausente_expirada_ou_revogada_nao_e_reativada(self):
        for operation in ('DELETE FROM usuarios_sessoes','UPDATE usuarios_sessoes SET expira_em=0','UPDATE usuarios_sessoes SET revogada_em=1'):
            with self.subTest(operation=operation):
                client=self.login()
                c=sqlite3.connect(self.path); c.execute(operation); c.commit(); c.close()
                self.assertEqual(client.get('/api/bri').status_code,302)

    def test_falha_ao_revogar_nao_anuncia_logout_concluido(self):
        client=self.login()
        with patch.object(sessoes,'revogar',side_effect=RuntimeError('banco indisponivel')):
            with self.assertRaises(RuntimeError):
                client.post('/logout')
        self.assertEqual(client.get('/api/bri').status_code,200)

    def test_csv_neutraliza_formulas_sem_transformar_coordenadas(self):
        for text in ('=1+1','+SUM(A1)','-1+2','@SUM(A1)','  =1+1','\t=1+1','\r=1+1','\n=1+1'):
            self.assertEqual(campo_csv(text),"'"+text)
            self.assertEqual(campo_csv(text,numerico=True),"'"+text)
        self.assertEqual(campo_csv(-25.1234,numerico=True),-25.1234)
        self.assertEqual(campo_csv('-49.1234',numerico=True),'-49.1234')
        self.assertEqual(campo_csv('Rua São João; 25'),'Rua São João; 25')

    def test_csv_humano_e_animal_protegem_textos_e_mantem_qgis(self):
        client=self.login()
        from blueprints import esporotricose
        for path,core,method,name in (
            ('/esporotricose/humanos/casos.csv',esporotricose.humanos_core,'listar_pacientes_csv','nome'),
            ('/esporotricose/doentes/casos.csv',esporotricose.esporotricose_core,'listar_doentes_csv','animal')):
            with self.subTest(path=path), patch.object(core,method,return_value=[{name:'=1+1','latitude':-25.1234,'longitude':-49.1234}]):
                response=client.get(path)
                self.assertEqual(response.status_code,200)
                row=next(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig')),delimiter=';'))
                self.assertEqual(row[name],"'=1+1")
                self.assertEqual(float(row['latitude']),-25.1234)
                self.assertEqual(float(row['longitude']),-49.1234)

    def test_novas_senhas_comuns_rejeitadas_sem_mudar_senha_existente(self):
        for password in ('1234567890','aaaaaaaaaaaa','abcabcabcabc','password123','senha123456'):
            self.assertFalse(auth.senha_valida(password))
        self.assertTrue(auth.senha_valida('Uma frase ficticia comprida!'))
