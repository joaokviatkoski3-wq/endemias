"""Cria massa ficticia suficiente para a regressao, sem copiar dados reais."""

import contextlib
import io
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import criar_banco
from app_core import auth, sqlite_maintenance, registro_geografico, esporotricose, bri, recolhimentos, amostras_animais


def preparar(path):
    path = Path(path).resolve()
    if ROOT == Path(r"C:\endemias") or ROOT not in path.parents or path.exists():
        raise ValueError("Exige arquivo novo dentro de worktree separada da producao.")
    with patch.object(criar_banco, "BANCO", str(path)), contextlib.redirect_stdout(io.StringIO()):
        criar_banco.main()
    sqlite_maintenance.ensure_schema_compatibility(str(path))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for module in (registro_geografico, esporotricose, bri, recolhimentos, amostras_animais):
        module.ensure_schema(conn)
    senha_hash = auth.hash_senha("SenhaSomenteDeTeste123!")
    conn.execute("UPDATE usuarios SET senha_hash=?", (senha_hash,))
    for i, nivel in enumerate(("visualizador", "operador", "usuario"), 2):
        conn.execute("INSERT INTO usuarios (id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES (?,?,?,?,?,?)",
                     (i, "ficticio" + str(i), "Usuario Ficticio " + str(i), senha_hash, nivel, "2026-06-01"))
    conn.execute("INSERT INTO agentes(id_agente,nome,nome_completo,cargo,ativo) VALUES(1,'Agente Ficticio','Agente de Ensaio Ficticio','Funcao de Ensaio',1)")
    conn.execute("INSERT INTO localidades(id_localidade,nome,cod_localidade) VALUES(1,'Localidade Ficticia',777)")
    conn.execute("INSERT INTO agentes(id_agente,nome,nome_completo,cargo,ativo) VALUES(2,'Outro Agente Ficticio','Outro Agente de Ensaio','Funcao de Ensaio',1)")
    common = dict(data="2026-06-01", hora_inicio="08:00", hora_fim="08:20", processado_em="2026-06-01T10:00:00", id_localidade=1, localidade="Localidade Ficticia", logradouro="Rua Ficticia", numero="10", quarteirao=1, visita="normal", tipo_imovel="R", agentes_texto="Agente Ficticio")
    for table, idcol, linktable in (
        ("visitas", "id_visita", "visita_agentes"),
        ("esporotricose_visitas", "id_visita", "esporotricose_visita_agentes"),
        ("bri_registros", "id_bri", "bri_agentes"),
        ("recolhimentos", "id_recolhimento", "recolhimento_agentes"),
        ("amostras_animais", "id_amostra", "amostra_animais_agentes"),
    ):
        values = {**common, idcol: "ficticio-" + table, "kobo_uuid": "uuid-ficticio-" + table, "tipo": "TB"}
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(" + table + ")")}
        values = {k: v for k, v in values.items() if k in cols}
        conn.execute("INSERT INTO " + table + " (" + ",".join(values) + ") VALUES (" + ",".join("?" for _ in values) + ")", list(values.values()))
        conn.execute("INSERT INTO " + linktable + " (" + idcol + ",id_agente) VALUES (?,1)", (values[idcol],))
    conn.execute("INSERT INTO focos_positivos(id_foco,id_visita,data,id_localidade,localidade,logradouro,numero,tipo_trabalho,gera_notificacao,status_notificacao) VALUES('foco-ficticio','ficticio-visitas','2026-06-01',1,'Localidade Ficticia','Rua Ficticia','10','TB',1,'pendente')")
    conn.execute("INSERT INTO registro_geografico_quarteiroes(id_quarteirao,id_localidade,localidade,quarteirao,criado_em,atualizado_em) VALUES(1,1,'Localidade Ficticia','0001','2026-06-01','2026-06-01')")
    conn.execute("""INSERT INTO registro_geografico_imoveis(id_quarteirao,ordem,id_localidade,localidade,quarteirao,logradouro,numero,lado,tipo,agentes_texto,busca_normalizada,chave_origem,criado_em,atualizado_em)
        VALUES(1,1,1,'Localidade Ficticia','0001','Rua Ficticia','10','1','R','Agente Ficticio','rua ficticia','imovel-ficticio','2026-06-01','2026-06-01')""")
    conn.execute("INSERT INTO registro_geografico_imovel_agentes(id_imovel,id_agente) VALUES(1,1)")
    conn.execute("UPDATE registro_geografico_imoveis SET condominio=4 WHERE id_imovel=1")
    conn.execute("INSERT INTO esporotricose_visitas(id_visita,kobo_uuid,data,processado_em,id_localidade) VALUES('outro-ficticio','uuid-outro-ficticio','2026-06-01','2026-06-01',1)")
    conn.execute("INSERT INTO esporotricose_visita_agentes(id_visita,id_agente) VALUES('outro-ficticio',2)")
    conn.commit()
    conn.close()
    print("Massa sintetica criada. Nenhum dado de producao foi consultado ou copiado.")


if __name__ == "__main__":
    preparar(sys.argv[1])
