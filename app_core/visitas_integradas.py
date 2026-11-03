"""Consultas operacionais comuns, sem copiar nem editar os registros LIRAa.

Uso explícito pelos módulos de consulta/relatórios. Somente SELECTs são
adaptados; gravações continuam sob responsabilidade dos serviços de origem.
As CTEs existem apenas durante a consulta, sem views/tabelas temporárias.
"""

from functools import lru_cache
import re

from app_core import db


PREFIXO = "liraa-v-"
TUBO_PREFIXO = "liraa-t-"
TABELAS = ("visitas", "coletas", "resultados_laboratorio", "visita_agentes", "visita_acs", "focos_positivos", "tratamentos")
_REFERENCIA = re.compile(r"('(?:''|[^'])*'|--[^\n]*|/\*.*?\*/)|\b(FROM|JOIN)\s+(\"?)(" + "|".join(TABELAS) + r")\b\3(?!\s*\.)", re.I | re.S)


def id_liraa(valor, prefixo=PREFIXO):
    texto = str(valor or "")
    if not texto.startswith(prefixo):
        return None
    numero = texto[len(prefixo):]
    if not numero.isascii() or not numero.isdigit() or int(numero) <= 0:
        raise ValueError("Identificador LIRAa inválido.")
    return int(numero)


@lru_cache(maxsize=1)
def catalogo_agentes():
    from app_core import agentes
    from openpyxl import load_workbook
    from app_core.liraa_modelo import APROVADO_XLSFORM
    book = load_workbook(APROVADO_XLSFORM, read_only=True)
    try:
        values = iter(book["survey"].values)
        head = next(values)
        survey = [dict(zip(head, r)) for r in values]
        lista = next(r["type"].split()[1] for r in survey if r.get("name") == "Agentes")
        values = iter(book["choices"].values)
        head = next(values)
        choices = [dict(zip(head, r)) for r in values]
        return tuple((str(r["name"]), agentes.normalizar_nome(r["label"])) for r in choices
                     if r.get("list_name") == lista and r.get("name") not in ("no-ace", "outros"))
    finally:
        book.close()


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


class ConsultaIntegrada:
    def __init__(self, conn):
        self.raw = conn
        self.backend = getattr(conn, "backend", "sqlite")
        self._ctes = None

    def _preparar(self):
        from app_core import agentes
        if self._ctes is not None:
            return self._ctes
        self._ctes = {}
        if not db.table_exists(self.raw, "liraa_visitas"):
            return self._ctes
        if not self.raw.execute("SELECT 1 FROM liraa_visitas LIMIT 1").fetchone():
            return self._ctes
        schema = self.raw.execute("SELECT current_schema()").fetchone()[0] if self.backend == "postgresql" else "main"
        def tabela(name):
            return f'"{schema}"."{name}"'
        def columns(name):
            if self.backend == "postgresql":
                return [r[0] for r in self.raw.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=? ORDER BY ordinal_position", (schema, name))]
            return [r[1] for r in self.raw.execute(f'PRAGMA table_info("{name}")')]
        def union(name, mapping, origem, distinct=False):
            cols = columns(name)
            if not cols:
                return
            original = [f'o."{c}"' for c in cols]
            if name == "visitas" and "quarteirao" in cols:
                original[cols.index("quarteirao")] = 'CAST(o.quarteirao AS TEXT) AS quarteirao'
            selecao="SELECT DISTINCT " if distinct else "SELECT "
            self._ctes[name] = (f'_oper_{name} AS (SELECT {",".join(original)} FROM {tabela(name)} o UNION ALL '+selecao
                + ",".join(mapping.get(c, "NULL") + f' AS "{c}"' for c in cols) + " FROM " + origem + ")")
        data = "CAST(v.data_visita AS DATE)" if self.backend == "postgresql" else "v.data_visita"
        # A duração não é coletada pelo formulário. Não inventa hora final/status.
        hora = ("CASE WHEN TRIM(v.hora_inicio) ~ '^([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$' THEN CAST(TRIM(v.hora_inicio) AS TIME) END"
                if self.backend == "postgresql" else "v.hora_inicio")
        vid = f"'{PREFIXO}' || CAST(v.id_visita AS TEXT)"
        tid = f"'{TUBO_PREFIXO}' || CAST(t.id_tubito AS TEXT)"
        quarteirao = "CAST(CAST(v.quarteirao AS NUMERIC) AS TEXT)"
        union("visitas", dict(id_visita=vid, kobo_uuid="v.kobo_uuid", kobo_id="v.kobo_id", tipo="'LIRAA'",
            data=data, hora_inicio=hora, ciclo="v.id_ciclo", localidade="v.localidade_informada",
            logradouro="v.logradouro", numero="v.numero", quarteirao=quarteirao, sequencia="v.sequencia",
            morador="v.morador", tipo_imovel="v.tipo_imovel", observacoes="v.observacoes",
            submission_time="v.enviado_em", processado_em="v.criado_em", id_localidade="v.id_localidade",
            acs_nome="(v.tratamento_json::jsonb #>> '{_campo,acs_outros}')" if self.backend=='postgresql' else "json_extract(v.tratamento_json,'$._campo.acs_outros')"), "liraa_visitas v")
        if db.table_exists(self.raw, "liraa_visita_tubitos"):
            union("coletas", dict(id_coleta=tid, id_visita=vid, num_tubo="t.numero", codigo_deposito="t.codigo_deposito",
                tipo_deposito="t.deposito"), "liraa_visita_tubitos t JOIN liraa_visitas v ON v.id_visita=t.id_visita")
        if db.table_exists(self.raw, "liraa_leituras"):
            campos = {f"{e}_{f}": f"r.{e}_{f}" for e in ("aegypt", "albopictus", "outra") for f in ("larvas", "pupas")}
            id_agente = "(SELECT MIN(a.id_agente) FROM agentes a WHERE LOWER(a.nome)=LOWER(r.laboratorista))"
            if db.table_exists(self.raw,"usuarios") and db.column_exists(self.raw,"usuarios","id_agente"):
                id_agente = "COALESCE((SELECT u.id_agente FROM usuarios u WHERE u.id_usuario=r.id_usuario)," + id_agente + ")"
            nome_agente = "COALESCE((SELECT a.nome FROM agentes a WHERE a.id_agente=" + id_agente + "),r.laboratorista)"
            origem_leitura = "r.origem" if db.column_exists(self.raw,"liraa_leituras","origem") else "'sistema'"
            uuid_leitura = "r.kobo_uuid" if db.column_exists(self.raw,"liraa_leituras","kobo_uuid") else "NULL"
            union("resultados_laboratorio", dict(id_resultado="-r.id_tubito", id_coleta=tid, num_tubo="t.numero", data_coleta=data,
                data_leitura="CAST(r.data_leitura AS DATE)" if self.backend == "postgresql" else "r.data_leitura",
                laboratorista=nome_agente, id_laboratorista=id_agente, origem=origem_leitura, kobo_uuid=uuid_leitura,
                criado_em="r.atualizado_em", atualizado_em="r.atualizado_em", **campos),
                "liraa_leituras r JOIN liraa_visita_tubitos t ON t.id_tubito=r.id_tubito JOIN liraa_visitas v ON v.id_visita=t.id_visita")
        if db.column_exists(self.raw, "liraa_visitas", "tratamento_json"):
            def valor(campo):
                return f"(v.tratamento_json::jsonb ->> '{campo}')" if self.backend == "postgresql" else f"json_extract(v.tratamento_json,'$.{campo}')"
            def numero(campo):
                texto = f"CAST({valor(campo)} AS TEXT)"
                valido = (texto + " ~ '^[0-9]+([.][0-9]+)?$'") if self.backend == "postgresql" else (texto + " NOT GLOB '*[^0-9.]*' AND " + texto + " GLOB '[0-9]*'")
                return f"CASE WHEN {valido} THEN CAST({texto} AS NUMERIC) END"
            union("tratamentos", dict(id="-v.id_visita", id_visita=vid, tipo="'BTI'",
                quantidade_carga=numero("Quantidade_carga_gr"), qtd_depositos_tratados=numero("Quantidade_dep_sitos_tratados")),
                "liraa_visitas v WHERE LOWER(CAST(" + valor("foi_tratado") + " AS TEXT))='sim'")
        if db.table_exists(self.raw, "agentes"):
            nomes = {}
            for r in self.raw.execute("SELECT id_agente,nome FROM agentes ORDER BY id_agente"):
                normal=agentes.normalizar_nome(r["nome"])
                if normal not in nomes or r["nome"]==normal:
                    nomes[normal]=r["id_agente"]
            aliases = [(code, nomes[nome]) for code, nome in catalogo_agentes() if nome in nomes]
            if aliases:
                values = " UNION ALL ".join(f"SELECT {_literal(code)} AS codigo,{int(ident)} AS id_agente" for code,ident in aliases)
                union("visita_agentes", dict(id_visita=vid, id_agente="a.id_agente"),
                    f"liraa_visitas v JOIN ({values}) a ON (' ' || v.agentes_codigos || ' ') LIKE ('% ' || a.codigo || ' %')",distinct=True)
        if self.backend=='postgresql':
            origem_acs="liraa_visitas v CROSS JOIN LATERAL regexp_split_to_table(TRIM(v.acs_codigos),'[[:space:]]+') a(acs_codigo)"
            campo_acs="a.acs_codigo"
        else:
            texto="REPLACE(REPLACE(REPLACE(v.acs_codigos,char(9),' '),char(10),' '),char(13),' ')"
            texto=f"REPLACE(REPLACE({texto},char(92),char(92)||char(92)),char(34),char(92)||char(34))"
            origem_acs="liraa_visitas v JOIN json_each('[\"' || REPLACE("+texto+",' ','\",\"') || '\"]') a"
            campo_acs="a.value"
        union("visita_acs",dict(id_visita=vid,acs_codigo=campo_acs),
              origem_acs+f" WHERE {campo_acs} NOT IN ('','no-acs','outros')",distinct=True)
        if db.table_exists(self.raw, "focos_positivos") and db.column_exists(self.raw, "focos_positivos", "id_visita_liraa"):
            cols = columns("focos_positivos")
            campos = [f'f."{c}"' if c != "id_visita" else f"COALESCE(f.id_visita,'{PREFIXO}' || CAST(f.id_visita_liraa AS TEXT)) AS id_visita" for c in cols]
            if "quarteirao" in cols:
                qfonte="COALESCE(f.quarteirao_liraa,CAST(f.quarteirao AS TEXT))" if "quarteirao_liraa" in cols else "CAST(f.quarteirao AS TEXT)"
                campos[cols.index("quarteirao")] = f"CASE WHEN f.id_visita_liraa IS NOT NULL THEN CAST(CAST({qfonte} AS NUMERIC) AS TEXT) ELSE CAST(f.quarteirao AS TEXT) END AS quarteirao"
            self._ctes["focos_positivos"] = "_oper_focos_positivos AS (SELECT " + ",".join(campos) + " FROM " + tabela("focos_positivos") + " f)"
        return self._ctes

    def sql(self, statement):
        texto = statement.lstrip()
        if not re.match(r"(?:SELECT|WITH)\b", texto, re.I) or re.search(r"\b(?:INSERT|UPDATE|DELETE|FOR\s+UPDATE)\b", texto, re.I):
            return statement
        referencias = {m[4].lower() for m in _REFERENCIA.finditer(statement) if m[4]}
        if not referencias:
            return statement
        ctes = self._preparar()
        usadas = referencias & ctes.keys()
        if not usadas:
            return statement
        def substituir(match):
            if match[4] and match[4].lower() in usadas:
                return match[2] + " _oper_" + match[4].lower()
            return match[0]
        adaptado = _REFERENCIA.sub(substituir, statement)
        prefixo = "WITH " + ",".join(ctes[t] for t in TABELAS if t in usadas) + " "
        if re.match(r"\s*WITH\s+", adaptado, re.I):
            if re.match(r"\s*WITH\s+RECURSIVE\s+",adaptado,re.I):
                return "WITH RECURSIVE " + prefixo[5:].rstrip() + "," + re.sub(r"^\s*WITH\s+RECURSIVE\s+","",adaptado,count=1,flags=re.I)
            return prefixo.rstrip() + "," + re.sub(r"^\s*WITH\s+", "", adaptado, count=1, flags=re.I)
        return prefixo + adaptado

    def execute(self, statement, parameters=()):
        return self.raw.execute(self.sql(statement), parameters)

    def cursor(self):
        return CursorIntegrado(self, self.raw.cursor())

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, *args):
        return self.raw.__exit__(*args)


def integrar(conn):
    return conn if isinstance(conn, ConsultaIntegrada) else ConsultaIntegrada(conn)


def connect(target):
    return integrar(db.connect(target))


class CursorIntegrado:
    def __init__(self, conn, cursor):
        self.conn, self.raw = conn, cursor

    def execute(self, statement, parameters=()):
        self.raw.execute(self.conn.sql(statement), parameters)
        return self

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def __iter__(self):
        return iter(self.raw)


def query(target, sql, params=()):
    conn = connect(target)
    try:
        return [db.serialize_row(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def query_one(target, sql, params=()):
    rows = query(target, sql, params)
    return rows[0] if rows else None
