"""Captura fictícia: reenvios, concorrência e revisão não perdem dados."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from app_core import campo_protocolo as p, db, formularios as f


class CampoProtocoloTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.target = db.DatabaseTarget("sqlite", str(Path(tmp.name)/"campo.db"))
        conn = db.connect(self.target)
        f.ensure_schema(conn)
        conn.close()
        self.user = {"id_usuario": 10, "nome": "Agente fictício", "nivel": "usuario"}
        self.uid = str(uuid4())
        self.meta = {"versao": 1, "revisao": 1, "dispositivo": str(uuid4())}
        self.data = {"id_localidade": 1, "localidade": "Teste", "quarteirao": "001", "data_atualizacao": "2026-11-06", "agentes_ids": [10], "linhas": [{"logradouro": "Rua Teste", "numero": "1", "sequencia": None, "tipo": "R", "condominio": 0}]}

    def save(self, data=None, revision=1, **kwargs):
        return f.salvar(self.target, "rg_atualizacao", data or self.data, self.user, uuid_cliente=self.uid,
                        captura={**self.meta, "revisao": revision}, **kwargs)

    def test_repeticao_nao_duplica_nem_audita_de_novo(self):
        calls = []
        ident = self.save(auditar=lambda *args: calls.append(args[1]))
        self.assertEqual(self.save(auditar=lambda *args: calls.append(args[1])), ident)
        self.assertEqual(calls, [ident])
        self.assertEqual(len(f.listar(self.target)), 1)

    def test_antigo_e_mesma_revisao_diferente_nao_sobrescrevem(self):
        ident = self.save(revision=2)
        with self.assertRaises(p.ConflitoCampo): self.save()
        with self.assertRaises(p.ConflitoCampo): self.save({**self.data, "localidade": "Outra"}, revision=2)
        self.assertEqual(f.obter(self.target, ident)["payload"]["localidade"], "Teste")

    def test_outro_aparelho_e_cliente_legado_nao_sobrescrevem(self):
        self.save()
        self.meta["dispositivo"] = str(uuid4())
        with self.assertRaises(p.ConflitoCampo): self.save(revision=2)
        with self.assertRaises(p.ConflitoCampo):
            f.salvar(self.target, "rg_atualizacao", {}, self.user, uuid_cliente=self.uid)

    def test_recibo_perdido_depois_da_revisao_e_oficializacao(self):
        ident = self.save()
        f.revisar(self.target, ident, {**self.data, "localidade": "Conferida"}, "aprovado", self.user)
        self.assertEqual(self.save(), ident)
        with self.assertRaises(p.ConflitoCampo): self.save(revision=2)
        f.marcar_oficializado(self.target, ident, self.user)
        self.assertEqual(self.save(), ident)
        self.assertEqual(f.obter(self.target, ident)["payload"]["localidade"], "Conferida")

    def test_auditoria_e_dados_confirmam_juntos(self):
        def fail(*args): raise RuntimeError("Falha fictícia")
        with self.assertRaises(RuntimeError): self.save(auditar=fail)
        self.assertEqual(f.listar(self.target), [])
        ident=self.save()
        with self.assertRaises(RuntimeError): self.save({**self.data,'localidade':'Não confirmar'},revision=2,auditar=fail)
        self.assertEqual(f.obter(self.target,ident)['payload']['localidade'],'Teste')

    def test_concorrencia_mesmo_uuid_so_um_registro(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: self.save(), range(4)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(f.listar(self.target)), 1)

    def test_protocolo_malformado_e_metadado_reservado(self):
        for bad in ({**self.meta, "versao": True}, {**self.meta, "revisao": True}, {**self.meta, "revisao": 0}, {**self.meta, "dispositivo": "x"}, {**self.meta, "extra": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.preparar("rg_atualizacao", self.data, self.uid, "enviado", bad)
        with self.assertRaises(ValueError): self.save({**self.data, p.META: self.meta})
        with self.assertRaises(ValueError): self.save({**self.data, "enorme": "x"*(2*1024*1024)})

    def test_validacao_campo_publicado_diferente_do_rascunho(self):
        p.validar_rg(self.data, "enviado")
        p.validar_rg({**self.data, "linhas": [], "agentes_ids": [], "data_atualizacao": None}, "rascunho")
        for change in ({"id_localidade": True}, {"quarteirao": ""}, {"linhas": []}, {"data_atualizacao": "amanhã"}, {"linhas": [{**self.data["linhas"][0], "condominio": -1}]}, {"_editor": {"versao": 1, "lados": [None]}}):
            with self.subTest(change=change), self.assertRaises(ValueError): p.validar_rg({**self.data, **change}, "enviado")

    def test_revisao_preserva_recibo_remove_editor_antigo(self):
        ident = self.save({**self.data, "_editor": {"lados": []}})
        item = f.obter(self.target, ident)
        f.revisar(self.target, ident, item["payload"], "devolvido", self.user)
        reviewed = f.obter(self.target, ident)["payload"]
        self.assertNotIn("_editor", reviewed)
        self.assertEqual(reviewed[p.META], item["payload"][p.META])

    def test_tipos_nao_textuais_rejeitados_sem_erro_interno(self):
        for value in ([],{},True,1,None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                p.validar_rg({**self.data,'linhas':[{**self.data['linhas'][0],'tipo':value}]},'enviado')
