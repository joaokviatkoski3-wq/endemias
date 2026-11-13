import json
import sqlite3
import tempfile
import unittest
from zlib import crc32
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app_core import db, kobo_api, liraa, liraa_kobo
from blueprints import liraa as liraa_routes


def envio(uuid, quarteirao="408.1", localidade="centro", data="2026-10-06", tubitos=True):
    return {
        "_uuid": uuid, "_id": crc32(uuid.encode()) or 1, "_submission_time": "2026-10-06T17:00:00Z",
        "Data": data, "Hora_inicio": "14:45:00", "Agentes": "jo_o pedro",
        "ACS": "ACS-006", "Dados_visita": {
            "Localidade": localidade, "Quarteir_o": quarteirao, "Imovel": "rco",
            "Logradouro": "Rua Teste", "Numero": 48, "Sequencia": "2",
            "Morador": "Morador teste", "Observa_es": ""},
        "group_jr1vc40": ([{"N_mero_do_tubito": 78, "C_digo_do_dep_sito": "B2",
                            "Dep_sito": "Banana"}] if tubitos else []),
    }


class LiraaKoboTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = str(Path(temporary.name) / "liraa.db")
        conn = db.connect(self.target)
        conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT NOT NULL)")
        conn.execute("INSERT INTO localidades VALUES (1,'Sede')")
        liraa._schema(conn)
        liraa_kobo.ensure_schema(conn)
        conn.execute("""INSERT INTO liraa_ciclos
            (id_ciclo,ano,nome,inicio,fim,observacoes,criado_em)
            VALUES (1,2026,'Teste','2026-10-01','2026-10-31','','2026-10-01')""")
        conn.execute("""INSERT INTO liraa_estratos
            (id_estrato,id_ciclo,numero,tipo,imoveis_confirmados,observacoes,criado_em,atualizado_em)
            VALUES (2,1,1,'normal',9000,'','2026-10-01','2026-10-01')""")
        conn.execute("""INSERT INTO liraa_estrato_quarteiroes
            (id_estrato,id_ciclo,id_localidade,quarteirao) VALUES (2,1,1,'408.1')""")
        selected = json.dumps([{"id_localidade": 1, "quarteirao": "408.1"}])
        conn.execute("""INSERT INTO liraa_sorteios
            (id_estrato,criado_em,semente,n,a,q,fracao,intervalo,inicio_casual,
             universo_hash,universo_json,selecionados_json)
            VALUES (2,'2026-10-01','1',1,1,1,0.2,1,0.1,'hash','[]',?)""", (selected,))
        conn.commit()
        conn.close()

    def test_acompanhamento_separa_turnos_e_calcula_saldo_por_estrato(self):
        from app_core import liraa_acompanhamento, liraa_modelo, liraa_operacional

        conn = db.connect(self.target)
        try:
            with conn:
                conn.execute("""INSERT INTO liraa_estratos
                    (id_estrato,id_ciclo,numero,tipo,imoveis_confirmados,observacoes,criado_em,atualizado_em)
                    VALUES (3,1,2,'normal',9000,'','2026-10-01','2026-10-01')""")
                conn.execute("""INSERT INTO liraa_estrato_quarteiroes
                    (id_estrato,id_ciclo,id_localidade,quarteirao)
                    VALUES (3,1,1,'0409'), (3,1,1,'0411'), (2,1,1,'0412')""")
                conn.execute("""INSERT INTO liraa_sorteios
                    (id_estrato,criado_em,semente,n,a,q,fracao,intervalo,inicio_casual,
                     universo_hash,universo_json,selecionados_json)
                    SELECT 3,criado_em,semente,2,a,q,fracao,intervalo,inicio_casual,
                           universo_hash,universo_json,?
                    FROM liraa_sorteios WHERE id_estrato=2""",
                    (json.dumps([{"id_localidade": 1, "quarteirao": "0409"}]),))
            plano_hash = liraa_operacional.plano_hash_conn(conn, 1)
        finally:
            conn.close()

        manha = envio("manha")
        manha["Hora_inicio"] = "8:45"
        tarde = envio("tarde", tubitos=False)
        tarde["Dados_visita"]["Imovel"] = "terreno_baldio"
        sem_hora = envio("fora", quarteirao="0410", tubitos=False)
        sem_hora["Hora_inicio"] = ""
        liraa_kobo.importar(self.target, 1, [manha, tarde, sem_hora])

        dados = liraa_acompanhamento.resumir(self.target, 1, "2026-10-06", "manha")
        self.assertEqual(dados["recorte"]["visitas"], 1)
        self.assertEqual(dados["recorte"]["pendentes"], 1)
        self.assertEqual(dados["acumulado"]["visitas"], 3)
        self.assertEqual(dados["acumulado"]["fora_plano"], 1)
        self.assertEqual(dict(dados["turnos_dia"]), {
            "Manhã": 1, "Tarde": 1, "Noite": 0, "Sem horário": 1,
        })
        self.assertEqual(dados["meta"], 3)
        self.assertEqual(dados["faltam"], 2)
        self.assertEqual(dados["quarteiroes_visitados"], 1)
        self.assertEqual(dados["quarteiroes_pendentes"][0]["quarteirao"], "0409")
        self.assertIn(("Terreno baldio", 0, 1), dados["tipos"])

        config = {"ciclo": 1, "plano_hash": plano_hash, "quarteiroes": [
            {"localidade": "Sede", "quarteirao": "0411"},
            {"localidade": "Sede", "quarteirao": "0412"},
        ]}
        extras = [envio("extra-estrato-2", "0411", tubitos=False),
                  envio("extra-estrato-1", "0412", tubitos=False)]
        with patch.object(liraa_modelo, "adicionais", return_value=config):
            self.assertEqual(liraa_kobo.importar(self.target, 1, extras), 2)
            com_extras = liraa_acompanhamento.resumir(self.target, 1, "2026-10-06")
        self.assertEqual(com_extras["meta"], 3)
        self.assertEqual(com_extras["adicionais"], 2)
        self.assertEqual([e["faltam"] for e in com_extras["estratos"]], [0, 1])
        self.assertEqual(com_extras["faltam"], 1)
        self.assertEqual(com_extras["percentual"], 66.7)
        self.assertEqual(com_extras["percentual_sorteadas"], 33.3)

    def test_ponto_virgula_e_zero_decimal_sao_o_mesmo_quarteirao(self):
        records = [envio("uuid-ponto", "408.1"), envio("uuid-virgula", "408,1"),
                   envio("uuid-zero", "408,10")]
        preview = liraa_kobo.previa(self.target, 1, records)
        self.assertEqual({x["quarteirao"] for x in preview}, {"408.1"})
        self.assertEqual({x["situacao_vinculo"] for x in preview}, {"sorteado"})
        self.assertEqual(liraa_kobo._quarteirao("408"), "0408")

    def test_zero_a_esquerda_no_cadastro_nao_impede_vinculo_decimal(self):
        conn = db.connect(self.target)
        conn.execute("UPDATE liraa_estrato_quarteiroes SET quarteirao='0408.1'")
        conn.execute("UPDATE liraa_sorteios SET selecionados_json=?", (
            json.dumps([{"id_localidade": 1, "quarteirao": "0408.1"}]),))
        conn.commit()
        conn.close()
        self.assertEqual(liraa_kobo.previa(self.target, 1, [envio("leading", "408,1")])[0]
                         ["situacao_vinculo"], "sorteado")

    def test_importacao_idempotente_tubitos_e_exclusao_impede_retorno(self):
        records = [envio("uuid-um"), envio("uuid-dois", tubitos=False)]
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 2)
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 0)
        visits = liraa_kobo.listar(self.target, 1)
        self.assertEqual(len(visits), 2)
        first = next(v for v in visits if v["kobo_uuid"] == "uuid-um")
        self.assertEqual(first["situacao_vinculo"], "sorteado")
        self.assertEqual(first["total_tubitos"], 1)
        self.assertEqual(liraa_kobo.tubitos(self.target, first["id_visita"])[0]["numero"], "78")
        liraa_kobo.excluir(self.target, first["id_visita"], "Teste")
        self.assertEqual(liraa_kobo.importar(self.target, 1, records), 0)
        self.assertEqual([v["kobo_uuid"] for v in liraa_kobo.listar(self.target)], ["uuid-dois"])
        conn = db.connect(self.target)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_visita_tubitos").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT motivo FROM liraa_visitas_excluidas").fetchone()[0], "Teste")
        conn.close()

    def test_edicao_kobo_com_mesmo_id_nao_duplica_visitas_ou_tubitos(self):
        from app_core import liraa_integracao

        original = envio("original")
        original["Dados_visita"]["Sequencia"] = "2,3"
        self.assertEqual(liraa_kobo.importar(self.target, 1, [original]), 2)
        editado = dict(envio("nova-versao"), _id=original["_id"], rootUuid="original")
        editado["Dados_visita"]["Sequencia"] = "2,3,4"
        novo = envio("outro-envio")
        previa = liraa_kobo.previa(self.target, 1, [editado, novo])
        self.assertEqual([v["situacao_importacao"] for v in previa], ["revisar edição", "nova"])
        self.assertEqual(liraa_kobo.importar(self.target, 1, [editado, novo]), 1)
        conn = db.connect(self.target)
        try:
            with conn:
                resultado = liraa_integracao.importar_lote(conn, [editado])
            self.assertEqual(resultado["edicoes_para_revisao"], 1)
            self.assertEqual(resultado["visitas_novas"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_visita_tubitos").fetchone()[0], 2)
        finally:
            conn.close()

    def test_edicao_de_envio_excluido_e_varias_versoes_no_lote_aguardam_revisao(self):
        original = envio("original")
        editado = dict(envio("editado"), _id=original["_id"], rootUuid="uuid:original")
        self.assertEqual(liraa_kobo.importar(self.target, 1, [original, editado]), 0)
        self.assertEqual(liraa_kobo.importar(self.target, 1, [original]), 1)
        liraa_kobo.excluir(self.target, liraa_kobo.listar(self.target, 1)[0]["id_visita"], "Ensaio")
        self.assertEqual(liraa_kobo.previa(self.target, 1, [editado])[0]["situacao_importacao"], "revisar edição")
        self.assertEqual(liraa_kobo.importar(self.target, 1, [editado]), 0)

    def test_identidade_inconsistente_isola_apenas_os_envios_afetados(self):
        from app_core import liraa_integracao

        primeiro = envio("uuid-em-conflito")
        segundo = dict(primeiro, _id=11)
        sem_uuid = dict(envio("sem-id"), _uuid="")
        novo = envio("valido")
        lote = [primeiro, segundo, sem_uuid, novo]
        resumo = kobo_api.summarize_submissions(lote, tipo="LIRAA", sample_size=2)
        self.assertEqual((resumo["total"], resumo["novos"], resumo["pendencias"]), (4, 1, 3))
        self.assertEqual([r["status"] for r in resumo["amostra"]], ["revisao", "revisao"])
        previa = liraa_kobo.previa(self.target, 1, lote)
        self.assertEqual([v["situacao_importacao"] for v in previa], ["conferir identidade"] * 3 + ["nova"])
        self.assertEqual(liraa_kobo.importar(self.target, 1, lote), 1)
        conn = db.connect(self.target)
        try:
            with conn:
                resultado = liraa_integracao.importar_lote(conn, lote)
            self.assertEqual(resultado["pendencias_identidade"], 3)
            self.assertEqual(resultado["visitas_novas"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_visita_tubitos").fetchone()[0], 1)
        finally:
            conn.close()

    def test_reenvio_identico_preserva_um_envio_e_todas_as_sequencias(self):
        from app_core import liraa_integracao

        original = envio("formulario-reenviado")
        original.update({
            "_id": 123, "_index": 1, "start": "2026-10-06T14:40:00-03:00",
            "end": "2026-10-06T14:49:00-03:00", "meta/instanceID": "uuid:formulario-reenviado",
        })
        original["Dados_visita"]["Sequencia"] = "1,2"
        repetido = dict(original, _id=126, _index=2, _submission_time="2026-10-06T17:54:00Z")
        lote = [repetido, original]
        self.assertEqual(liraa_kobo.consolidar_reenvios_kobo(lote), ([original], 1))
        with patch.object(kobo_api, "fetch_complete_submissions", return_value=lote):
            records, meta = liraa_integracao.buscar_kobo({}, self.target, uid="formulario")
            self.assertEqual((records, meta), ([original], {"count": 1, "reenvios_ignorados": 1}))
        self.assertEqual(len(liraa_kobo.previa(self.target, 1, lote)), 2)
        self.assertEqual(liraa_kobo.importar(self.target, 1, lote), 2)
        self.assertEqual(liraa_kobo.importar(self.target, 1, lote), 0)
        visits = liraa_kobo.listar(self.target, 1)
        self.assertEqual({v["sequencia"] for v in visits}, {"1", "2"})
        self.assertEqual({v["kobo_id"] for v in visits}, {123})
        self.assertEqual(sum(v["total_tubitos"] for v in visits), 1)

        divergente = dict(repetido, _id=129, Dados_visita=dict(repetido["Dados_visita"], Numero=100))
        self.assertEqual(liraa_kobo.consolidar_reenvios_kobo([original, repetido, divergente])[1], 0)
        self.assertEqual(
            [v["situacao_importacao"] for v in liraa_kobo.previa(self.target, 1, [original, divergente])],
            ["conferir identidade", "conferir identidade"],
        )

    def test_fora_sorteio_e_periodo_nao_recebem_vinculo_indevido(self):
        conn = db.connect(self.target)
        conn.execute("INSERT INTO liraa_estrato_quarteiroes VALUES (2,1,1,'0409')")
        conn.commit()
        conn.close()
        cases = [envio("fora-sorteio", "409"), envio("fora-estrato", "410"),
                 envio("fora-periodo", "408,1", data="2026-11-01")]
        preview = liraa_kobo.previa(self.target, 1, cases)
        self.assertEqual([r["situacao_vinculo"] for r in preview],
                         ["fora_do_sorteio", "fora_do_estrato", "fora_do_periodo"])
        self.assertIsNone(preview[-1]["id_estrato"])

    def test_capivara_rural_nao_recebe_vinculo(self):
        item = liraa_kobo._normalizar(envio("rural", "408.1", localidade="Capivara dos Manfron"))
        conn = db.connect(self.target)
        try:
            _, estrato, status = liraa_kobo._vincular(item, liraa_kobo._contexto(conn, 1))
        finally:
            conn.close()
        self.assertIsNone(estrato)
        self.assertEqual(status, "area_rural_fora_liraa")

    def test_lote_invalido_desfaz_tudo(self):
        with self.assertRaises(liraa_kobo.LiraaKoboError):
            liraa_kobo.importar(self.target, 1, [envio("valida"), envio("invalida", "A")])
        self.assertEqual(liraa_kobo.listar(self.target), [])

    def test_ciclo_e_estrato_com_visitas_nao_sao_excluidos(self):
        liraa_kobo.importar(self.target, 1, [envio("permanente")])
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.excluir_estrato(self.target, 2)
        with self.assertRaisesRegex(liraa.LiraaError, "possui visitas"):
            liraa.excluir_ciclo(self.target, 1)

    def test_vinculo_mostrado_reflete_sorteio_atual(self):
        liraa_kobo.importar(self.target, 1, [envio("atual")])
        self.assertEqual(liraa_kobo.listar(self.target)[0]["situacao_vinculo"], "sorteado")
        conn = db.connect(self.target)
        conn.execute("DELETE FROM liraa_sorteios WHERE id_estrato=2")
        conn.commit()
        conn.close()
        self.assertEqual(liraa_kobo.listar(self.target)[0]["situacao_vinculo"], "estrato_sem_sorteio")

    def test_configuracao_liraa_participa_do_importador_geral(self):
        self.assertIn("LIRAA", kobo_api.ALL_TYPES)
        cfg = kobo_api.default_config()
        self.assertIn("LIRAA", cfg["assets"])
        config_path = Path(self.target).with_suffix(".json")
        kobo_api.save_config(config_path, {"assets": {"LIRAA": "anXWARrB2YkHK5W9YTwDfU"}})
        self.assertEqual(kobo_api.load_config(config_path)["assets"]["LIRAA"],
                         "anXWARrB2YkHK5W9YTwDfU")
        kobo_api.save_config(config_path, {"assets": {"PVE": "pve-teste"}})
        self.assertEqual(kobo_api.load_config(config_path)["assets"]["LIRAA"],
                         "anXWARrB2YkHK5W9YTwDfU")

    def test_consulta_rejeita_resposta_truncada_e_periodo_invalido(self):
        app = Flask(__name__)
        config_path = Path(self.target).with_suffix(".json")
        app.config["KOBO_CONFIG_PATH"] = str(config_path)
        kobo_api.save_config(config_path, {"assets": {"LIRAA": "anXWARrB2YkHK5W9YTwDfU"}})
        with app.app_context():
            with patch.object(liraa_routes.kobo_api, "_get_json",
                              return_value={"results": [envio("um")], "count": 2, "next": None}):
                with self.assertRaisesRegex(kobo_api.KoboError, "retornou 1 de 2"):
                    liraa_routes._buscar_kobo("2026-10-01", "2026-10-06")
            with self.assertRaisesRegex(liraa_kobo.LiraaKoboError, "período"):
                liraa_routes._buscar_kobo("2026-10-07", "2026-10-06")

    def test_consulta_busca_paginas_com_o_mesmo_projeto_e_periodo(self):
        registros = [envio(f"envio-{i}") for i in range(1205)]
        consultas = []

        def kobo(cfg, path, params):
            consultas.append((path, params.copy()))
            if "start" not in params:
                return {
                    "results": registros[:1000], "count": "unknown",
                    "next": "https://outro.example/?start=1000",
                }
            return {"results": registros[1000:], "count": 1205, "next": None}

        with patch.object(kobo_api, "_get_json", side_effect=kobo):
            self.assertEqual(kobo_api.fetch_complete_submissions(
                {}, "formulario", start="2026-11-09", end="2026-11-11",
            ), registros)
        path, params = consultas[0]
        self.assertEqual(path, "/api/v2/assets/formulario/data/")
        self.assertIn("2026-11-09T00:00:00", params["query"])
        self.assertIn("2026-11-11T23:59:59", params["query"])
        self.assertEqual(params["limit"], 1000)
        self.assertEqual(consultas[1], (path, dict(params, start=1000)))

    def test_paginacao_distingue_uuid_repetido_de_repeticao_da_mesma_linha(self):
        a = {"_id": 101, "_uuid": "mesmo-uuid"}
        b = {"_id": 102, "_uuid": "mesmo-uuid"}
        c = {"_id": 103}
        p1 = {"results": [a], "count": 3, "next": "?start=1"}
        sobreposta = {"results": [dict(a, _uuid="versao-editada"), c], "count": 3, "next": None}
        p2 = {"results": [b, c], "count": 3, "next": None}
        with patch.object(kobo_api, "_get_json", side_effect=[p1, sobreposta, p1, p2]) as fetch:
            self.assertEqual(kobo_api.fetch_complete_submissions({}, "formulario"), [a, b, c])
            self.assertEqual(fetch.call_count, 4)
        with patch.object(kobo_api, "_get_json", side_effect=[p1, sobreposta] * 2):
            with self.assertRaisesRegex(kobo_api.KoboError, "mesma linha"):
                kobo_api.fetch_complete_submissions({}, "formulario")

    def test_sequencias_formatos_e_identificadores_variados(self):
        from app_core.liraa_sequencias import separar
        for value in ('1,2,3','1, 2, 3','1-2-3','1 - 2 - 3','1/2/3','1 / 2 / 3',
                      '1;2;3','1 ; 2 ; 3','1–2–3','1 | 2 | 3','1,2;3','1 e 2 e 3','1 2 3'):
            with self.subTest(value=value):self.assertEqual(separar(value)[0],['1','2','3'])
        for prefix in ('A','B','Z','AB'):
            self.assertEqual(separar(f'{prefix}1, {prefix}2, {prefix}3')[0],[prefix+'1',prefix+'2',prefix+'3'])
        self.assertEqual(separar('1, 2, 2')[0],['1','2'])
        self.assertTrue(separar('a1,A1,A2')[1])
        self.assertEqual(separar('3')[0],['3'])
        self.assertEqual(separar('N/A')[0],['N/A'])
        self.assertEqual(separar('S/N')[0],['S/N'])
        self.assertEqual(separar('1-3')[0],['1','3'])
        self.assertEqual(separar('A-1')[0],['A-1'])
        self.assertEqual(separar('A-1, B-2')[0],['A-1','B-2'])
        self.assertEqual(separar('A-1 - A-2')[0],['A-1','A-2'])
        with self.assertRaises(liraa_kobo.LiraaKoboError):separar('A-1-A-2')
        with self.assertRaises(liraa_kobo.LiraaKoboError):separar(','.join(map(str,range(51))))

    def test_expande_sem_duplicar_tubitos_tratamentos_e_identidade(self):
        record=envio('sequencias');record['Dados_visita']['Sequencia']='B1, B2, B3'
        record['tratamento_001']={'Quantidade_carga_gr':4}
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),3)
        visits=liraa_kobo.listar(self.target,1)
        self.assertEqual({v['sequencia'] for v in visits},{'B1','B2','B3'})
        self.assertEqual(sum(v['total_tubitos'] for v in visits),1)
        mother=next(v for v in visits if v['kobo_uuid']=='sequencias')
        self.assertEqual(mother['sequencia'],'B1')
        self.assertEqual(mother['total_tubitos'],1)
        self.assertEqual(sum(bool(json.loads(v['tratamento_json']).get('Quantidade_carga_gr')) for v in visits),1)
        ids={v['id_visita'] for v in visits}
        record['Dados_visita']['Sequencia']='B3 / B2 / B1'
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),0)
        self.assertEqual({v['id_visita'] for v in liraa_kobo.listar(self.target,1)},ids)
        child=next(v for v in visits if v['sequencia']=='B2')
        liraa_kobo.excluir(self.target,child['id_visita'],'Ensaio de exclusão')
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),0)
        self.assertEqual(len(liraa_kobo.listar(self.target,1)),2)

    def test_expansao_exclui_repetidas_e_preserva_exclusao_da_primeira(self):
        record=envio('repetidas');record['Dados_visita']['Sequencia']='1, 2, 2'
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),2)
        mother=next(v for v in liraa_kobo.listar(self.target,1) if v['kobo_uuid']=='repetidas')
        self.assertTrue(any('repetidas' in a for a in mother['avisos']))
        liraa_kobo.excluir(self.target,mother['id_visita'],'Ensaio')
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),0)
        self.assertEqual(len(liraa_kobo.listar(self.target,1)),1)

    def test_reimportacao_parcial_apos_excluir_grupo_inteiro_nao_ressuscita_unidades(self):
        record=envio('grupo-excluido');record['Dados_visita']['Sequencia']='1,2,3'
        liraa_kobo.importar(self.target,1,[record])
        for visit in liraa_kobo.listar(self.target,1):liraa_kobo.excluir(self.target,visit['id_visita'],'Ensaio')
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),0)
        liraa_kobo.permitir_reimportacao(self.target,'grupo-excluido','Ensaio')
        with self.assertRaises(liraa_kobo.LiraaKoboError):liraa_kobo.importar(self.target,1,[record])
        self.assertEqual(liraa_kobo.listar(self.target,1),[])

    def test_envio_legado_nao_e_expandido_silenciosamente(self):
        record=envio('legado');record['Dados_visita']['Sequencia']='1,2,3'
        from app_core import liraa_sequencias
        with patch.object(liraa_sequencias,'expandir',side_effect=lambda conn,item:[item]):
            self.assertEqual(liraa_kobo.importar(self.target,1,[record]),1)
        preview=liraa_kobo.previa(self.target,1,[record])
        self.assertEqual(len(preview),1)
        self.assertTrue(any('antigo' in a for a in preview[0]['avisos']))
        self.assertEqual(liraa_kobo.importar(self.target,1,[record]),0)
        self.assertEqual(len(liraa_kobo.listar(self.target,1)),1)

    def test_alteracao_de_conjunto_ou_limite_recusa_lote_sem_gravacao_parcial(self):
        record=envio('conjunto');record['Dados_visita']['Sequencia']='1,2'
        liraa_kobo.importar(self.target,1,[record])
        record['Dados_visita']['Sequencia']='1,2,3'
        with self.assertRaises(liraa_kobo.LiraaKoboError):
            liraa_kobo.importar(self.target,1,[envio('nao_gravar'),record])
        self.assertEqual(len(liraa_kobo.listar(self.target,1)),2)


if __name__ == "__main__":
    unittest.main()
