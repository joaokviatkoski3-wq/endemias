"""Cadastro oficial de logradouros e importacao segura de CSV.

O cadastro conserva cada ``id_logr`` da fonte municipal. Nomes repetidos sao
esperados: representam trechos diferentes de uma mesma rua e nao devem ser
fundidos durante a importacao.
"""

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from datetime import datetime

from app_core import db as db_core
from app_core import enderecos as enderecos_core
from app_core import geocodificacao


TABLE = "logradouros_oficiais"
ENDERECOS_TABLE = "enderecos_normalizados"
VINCULOS_TABLE = "visitas_enderecos_normalizados"
REQUIRED_COLUMNS = {"nome", "localidade", "id_logr"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SCORE_MINIMO_SUGESTAO = 72
MAX_SUGESTOES = 5
GEOCODIFICACAO_STATUS = {
    "pendente", "automatico", "aproximado", "nao_encontrado", "erro",
    "aguarda_manual", "manual",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _text(value):
    return " ".join(str(value or "").strip().split())


def normalizar_nome(value):
    """Chave de comparacao, sem alterar a grafia oficial exibida."""
    text = unicodedata.normalize("NFKD", _text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace(".", " ").replace("-", " ").split())


def normalizar_logradouro(value):
    """Chave comum usada na conciliacao, inclusive para abreviacoes."""
    return enderecos_core.normalizar_logradouro(value)


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _ativo_verdadeiro_sql(conn):
    """Expressao SQL compativel com a coluna ativa de cada backend."""
    return "ativo=TRUE" if _is_postgresql(conn) else "ativo=1"


def _ativo_verdadeiro_valor(conn):
    return True if _is_postgresql(conn) else 1


def ensure_schema(target):
    conn = db_core.connect(target)
    try:
        if _is_postgresql(conn):
            return
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id_logradouro TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                nome_normalizado TEXT NOT NULL,
                localidade TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                origem_hash TEXT NOT NULL,
                importado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logradouros_nome_normalizado
                ON {TABLE}(nome_normalizado);
            CREATE INDEX IF NOT EXISTS idx_logradouros_ativo_nome
                ON {TABLE}(ativo, nome);

            CREATE TABLE IF NOT EXISTS {ENDERECOS_TABLE} (
                id_endereco INTEGER PRIMARY KEY AUTOINCREMENT,
                chave_endereco TEXT NOT NULL UNIQUE,
                logradouro_normalizado TEXT NOT NULL,
                logradouro_oficial TEXT NOT NULL,
                numero_normalizado TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                confirmado_por TEXT,
                latitude REAL,
                longitude REAL,
                geocodificacao_status TEXT NOT NULL DEFAULT 'pendente',
                geocodificacao_fonte TEXT,
                geocodificacao_consulta TEXT,
                geocodificacao_resultado TEXT,
                geocodificacao_precisao TEXT,
                geocodificacao_detalhes_json TEXT,
                geocodificado_em TEXT,
                geocodificado_por TEXT
            );
            CREATE TABLE IF NOT EXISTS {VINCULOS_TABLE} (
                id_visita TEXT PRIMARY KEY,
                id_endereco INTEGER NOT NULL REFERENCES {ENDERECOS_TABLE}(id_endereco),
                logradouro_bruto TEXT,
                numero_bruto TEXT,
                confirmado_em TEXT NOT NULL,
                confirmado_por TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_visitas_enderecos_id_endereco
                ON {VINCULOS_TABLE}(id_endereco);
            """
        )
        novas_colunas = {
            "latitude": "REAL",
            "longitude": "REAL",
            "geocodificacao_status": "TEXT NOT NULL DEFAULT 'pendente'",
            "geocodificacao_fonte": "TEXT",
            "geocodificacao_consulta": "TEXT",
            "geocodificacao_resultado": "TEXT",
            "geocodificacao_precisao": "TEXT",
            "geocodificacao_detalhes_json": "TEXT",
            "geocodificado_em": "TEXT",
            "geocodificado_por": "TEXT",
        }
        for coluna, definicao in novas_colunas.items():
            if not db_core.column_exists(conn, ENDERECOS_TABLE, coluna):
                conn.execute(f"ALTER TABLE {ENDERECOS_TABLE} ADD COLUMN {coluna} {definicao}")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_enderecos_geocodificacao_status "
            f"ON {ENDERECOS_TABLE}(geocodificacao_status)"
        )
        conn.commit()
    finally:
        conn.close()


def _catalogo_por_nome(conn):
    ativo = _ativo_verdadeiro_sql(conn)
    catalogo = {}
    for row in conn.execute(
        f"SELECT id_logradouro, nome FROM {TABLE} WHERE {ativo} ORDER BY nome, id_logradouro"
    ):
        chave = normalizar_logradouro(row["nome"])
        if chave:
            item = catalogo.setdefault(chave, {"nomes": set(), "trechos": []})
            item["nomes"].add(row["nome"])
            item["trechos"].append(dict(row))
            item["nucleo"] = enderecos_core.nucleo_logradouro(row["nome"])
    return catalogo


def _aliases_confirmados(conn):
    aliases = {}
    rows = conn.execute(
        f"""SELECT ve.logradouro_bruto, e.logradouro_oficial
              FROM {VINCULOS_TABLE} ve
              JOIN {ENDERECOS_TABLE} e ON e.id_endereco=ve.id_endereco
             WHERE TRIM(COALESCE(ve.logradouro_bruto,''))<>''"""
    ).fetchall()
    for row in rows:
        chave = normalizar_logradouro(row["logradouro_bruto"])
        if chave:
            aliases.setdefault(chave, set()).add(row["logradouro_oficial"])
    return {chave: next(iter(nomes)) for chave, nomes in aliases.items() if len(nomes) == 1}


def _candidatos_logradouro(logradouro, catalogo, aliases):
    chave = normalizar_logradouro(logradouro)
    chave_alias = normalizar_logradouro(aliases.get(chave)) if aliases.get(chave) else None

    def resultado(chave_oficial, item, score, motivo):
        nomes = sorted(item["nomes"], key=str.casefold)
        return {
            "nome": nomes[0],
            "score": score,
            "motivo": motivo,
            "trechos": len(item["trechos"]),
            "chave_oficial": chave_oficial,
        }

    if chave in catalogo:
        return [resultado(chave, catalogo[chave], 100, "mesma grafia normalizada")]
    if chave_alias in catalogo:
        return [resultado(chave_alias, catalogo[chave_alias], 100, "correspondência já confirmada")]

    nucleo_busca = enderecos_core.nucleo_logradouro(logradouro)
    tokens_busca = set(nucleo_busca.split())
    candidatos = []
    for chave_oficial, item in catalogo.items():
        nucleo_oficial = item["nucleo"]
        if not nucleo_busca or not nucleo_oficial:
            continue
        tokens_oficiais = set(nucleo_oficial.split())
        tamanho_relativo = min(len(nucleo_busca), len(nucleo_oficial)) / max(
            len(nucleo_busca), len(nucleo_oficial), 1
        )
        possivel = (
            nucleo_busca == nucleo_oficial
            or nucleo_busca in nucleo_oficial
            or nucleo_oficial in nucleo_busca
            or bool(tokens_busca & tokens_oficiais)
            or (nucleo_busca[:3] == nucleo_oficial[:3] and tamanho_relativo >= 0.55)
        )
        if not possivel:
            continue
        nome = sorted(item["nomes"], key=str.casefold)[0]
        score, motivo = enderecos_core.similaridade_logradouro(logradouro, nome)
        if score < SCORE_MINIMO_SUGESTAO:
            continue
        candidatos.append(resultado(chave_oficial, item, score, motivo))
    candidatos.sort(key=lambda item: (-item["score"], item["nome"].casefold()))
    return candidatos[:MAX_SUGESTOES]


def _visitas_positivas_sem_vinculo(conn):
    return conn.execute(
        f"""
        SELECT v.id_visita, v.logradouro, v.numero, v.data, v.tipo,
               COALESCE(l.nome, v.localidade) AS localidade, v.quarteirao
          FROM visitas v
          LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
         LEFT JOIN {VINCULOS_TABLE} ve ON ve.id_visita=v.id_visita
         WHERE ve.id_visita IS NULL
           AND v.tipo<>'PE'
           AND EXISTS (
               SELECT 1
                 FROM coletas c
                 JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
                WHERE c.id_visita=v.id_visita
                  AND (COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0) +
                       COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)) > 0
           )
         ORDER BY v.data DESC, v.id_visita DESC
        """
    ).fetchall()


def _resumo_positivas_elegiveis(conn):
    row = conn.execute(
        f"""SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN ve.id_visita IS NOT NULL THEN 1 ELSE 0 END),0) AS vinculadas
              FROM visitas v
              LEFT JOIN {VINCULOS_TABLE} ve ON ve.id_visita=v.id_visita
             WHERE v.tipo<>'PE'
               AND EXISTS (
                   SELECT 1
                     FROM coletas c
                     JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
                    WHERE c.id_visita=v.id_visita
                      AND (COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0) +
                           COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)) > 0
               )"""
    ).fetchone()
    return {"total": row["total"] or 0, "vinculadas": row["vinculadas"] or 0}


def _montar_grupos_pendentes(conn):
    catalogo = _catalogo_por_nome(conn)
    aliases = _aliases_confirmados(conn)
    grupos = {}
    for row in _visitas_positivas_sem_vinculo(conn):
        logradouro = str(row["logradouro"] or "").strip()
        numero = str(row["numero"] or "").strip()
        chave_logradouro = normalizar_logradouro(logradouro)
        chave_numero = enderecos_core.normalizar_numero(numero)
        chave_comparacao = f"{chave_logradouro}\x1f{chave_numero}"
        if not chave_logradouro or not chave_numero:
            # Sem os dois componentes nao ha evidencia suficiente para agrupar
            # visitas distintas como se fossem o mesmo imovel.
            chave_comparacao += f"\x1f{row['id_visita']}"
        grupo = grupos.setdefault(
            chave_comparacao,
            {
                "chave": hashlib.sha256(chave_comparacao.encode("utf-8")).hexdigest(),
                "logradouro_normalizado": chave_logradouro,
                "numero_normalizado": chave_numero,
                "logradouros_informados": set(),
                "enderecos_informados": set(),
                "visitas": [],
                "localidades": set(),
                "quarteiroes": set(),
            },
        )
        exibicao = logradouro or "(logradouro não informado)"
        grupo["enderecos_informados"].add(f"{exibicao}{', ' + numero if numero else ''}")
        grupo["logradouros_informados"].add(logradouro)
        grupo["visitas"].append(str(row["id_visita"]))
        if row["localidade"]:
            grupo["localidades"].add(str(row["localidade"]))
        if row["quarteirao"] not in (None, ""):
            grupo["quarteiroes"].add(str(row["quarteirao"]))

    resultado = []
    for grupo in grupos.values():
        logradouro_referencia = sorted(grupo["logradouros_informados"], key=str.casefold)[0]
        candidatos = _candidatos_logradouro(logradouro_referencia, catalogo, aliases)
        if not grupo["logradouro_normalizado"]:
            situacao = "sem_logradouro"
        elif not grupo["numero_normalizado"]:
            situacao = "sem_numero"
        elif not candidatos:
            situacao = "nao_encontrado"
        elif candidatos[0]["score"] < 98:
            situacao = "sugestao_aproximada"
        else:
            situacao = "pronto_para_revisar"
        resultado.append(
            {
                "chave": grupo["chave"],
                "logradouro_normalizado": grupo["logradouro_normalizado"],
                "numero_normalizado": grupo["numero_normalizado"],
                "enderecos_informados": sorted(grupo["enderecos_informados"], key=str.casefold),
                "visitas": sorted(grupo["visitas"]),
                "quantidade_visitas": len(grupo["visitas"]),
                "localidades": sorted(grupo["localidades"], key=str.casefold),
                "quarteiroes": sorted(grupo["quarteiroes"]),
                "nome_oficial": candidatos[0]["nome"] if candidatos else None,
                "trechos_oficiais": candidatos[0]["trechos"] if candidatos else 0,
                "candidatos": candidatos,
                "situacao": situacao,
            }
        )
    resultado.sort(key=lambda item: (-item["quantidade_visitas"], item["enderecos_informados"][0].casefold()))
    return resultado, catalogo


def previa_visitas_positivas(target, pagina=1, por_pagina=100):
    """Agrupa todos os enderecos positivos pendentes e pagina a revisao."""
    ensure_schema(target)
    try:
        pagina = max(1, int(pagina or 1))
        por_pagina = max(1, min(int(por_pagina or 100), 300))
    except (TypeError, ValueError):
        pagina, por_pagina = 1, 100
    conn = db_core.connect(target)
    try:
        grupos, catalogo = _montar_grupos_pendentes(conn)
        cobertura = _resumo_positivas_elegiveis(conn)
        total_grupos = len(grupos)
        total_paginas = max(1, (total_grupos + por_pagina - 1) // por_pagina)
        pagina = min(pagina, total_paginas)
        inicio = (pagina - 1) * por_pagina
        incompletas = sum(
            item["quantidade_visitas"]
            for item in grupos
            if item["situacao"] in {"sem_logradouro", "sem_numero"}
        )
        return {
            "grupos": grupos[inicio:inicio + por_pagina],
            "total_grupos": total_grupos,
            "total_visitas": sum(item["quantidade_visitas"] for item in grupos),
            "enderecos_incompletos": incompletas,
            "total_elegiveis": cobertura["total"],
            "total_vinculadas": cobertura["vinculadas"],
            "catalogo_disponivel": bool(catalogo),
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": total_paginas,
            "nomes_oficiais": sorted(
                {nome for item in catalogo.values() for nome in item["nomes"]}, key=str.casefold
            ),
        }
    finally:
        conn.close()


def _obter_endereco(conn, nome_oficial, numero_normalizado, confirmado_por, agora):
    logradouro_normalizado = normalizar_logradouro(nome_oficial)
    chave_canonica = f"{logradouro_normalizado}\x1f{numero_normalizado}"
    chave_endereco = hashlib.sha256(chave_canonica.encode("utf-8")).hexdigest()
    existente = conn.execute(
        f"SELECT id_endereco FROM {ENDERECOS_TABLE} WHERE chave_endereco=?", (chave_endereco,)
    ).fetchone()
    if existente:
        id_endereco = existente["id_endereco"]
        conn.execute(
            f"UPDATE {ENDERECOS_TABLE} SET logradouro_oficial=?, atualizado_em=?, confirmado_por=? WHERE id_endereco=?",
            (nome_oficial, agora, confirmado_por, id_endereco),
        )
        return id_endereco
    return db_core.insert_and_get_id(
        conn,
        f"""INSERT INTO {ENDERECOS_TABLE}
               (chave_endereco,logradouro_normalizado,logradouro_oficial,numero_normalizado,
                criado_em,atualizado_em,confirmado_por)
            VALUES (?,?,?,?,?,?,?)""",
        (chave_endereco, logradouro_normalizado, nome_oficial, numero_normalizado, agora, agora, confirmado_por),
        "id_endereco",
    )


def confirmar_grupos_visitas_positivas(target, itens, confirmado_por=None):
    """Confirma varios grupos em uma unica transacao, depois de revalidar todos."""
    if not isinstance(itens, list) or not itens:
        raise ValueError("Selecione ao menos um grupo para confirmar.")
    if len(itens) > 300:
        raise ValueError("Confirme no máximo 300 grupos por vez.")
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        grupos, catalogo = _montar_grupos_pendentes(conn)
        por_chave = {grupo["chave"]: grupo for grupo in grupos}
        oficiais = {
            nome.casefold(): nome
            for item in catalogo.values()
            for nome in item["nomes"]
        }
        preparados = []
        chaves_recebidas = set()
        for item in itens:
            chave = str((item or {}).get("chave") or "")
            if not chave or chave in chaves_recebidas:
                raise ValueError("A seleção contém um grupo inválido ou repetido.")
            chaves_recebidas.add(chave)
            grupo = por_chave.get(chave)
            if not grupo:
                raise ValueError("Um dos grupos não está mais pendente; atualize a prévia.")
            nome_recebido = " ".join(str((item or {}).get("nome_oficial") or "").strip().split())
            nome_oficial = oficiais.get(nome_recebido.casefold())
            if not nome_oficial:
                raise ValueError(f"Escolha um logradouro oficial para {grupo['enderecos_informados'][0]}.")
            numero = enderecos_core.normalizar_numero((item or {}).get("numero"))
            if not numero:
                raise ValueError(f"Informe o número usado no vínculo de {grupo['enderecos_informados'][0]}.")
            preparados.append((grupo, nome_oficial, numero))

        agora = _now()
        enderecos_ids = set()
        visitas_vinculadas = 0
        confirmacoes = []
        for grupo, nome_oficial, numero in preparados:
            id_endereco = _obter_endereco(conn, nome_oficial, numero, confirmado_por, agora)
            enderecos_ids.add(id_endereco)
            rows = conn.execute(
                f"SELECT id_visita, logradouro, numero FROM visitas WHERE id_visita IN ({','.join('?' * len(grupo['visitas']))})",
                grupo["visitas"],
            ).fetchall()
            conn.executemany(
                f"""INSERT INTO {VINCULOS_TABLE}
                       (id_visita,id_endereco,logradouro_bruto,numero_bruto,confirmado_em,confirmado_por)
                    VALUES (?,?,?,?,?,?)""",
                [
                    (row["id_visita"], id_endereco, row["logradouro"], row["numero"], agora, confirmado_por)
                    for row in rows
                ],
            )
            visitas_vinculadas += len(rows)
            confirmacoes.append(
                {
                    "id_endereco": id_endereco,
                    "logradouro_oficial": nome_oficial,
                    "numero": numero,
                    "visitas": len(rows),
                }
            )
        conn.commit()
        return {
            "grupos_confirmados": len(preparados),
            "enderecos_afetados": len(enderecos_ids),
            "visitas_vinculadas": visitas_vinculadas,
            "confirmacoes": confirmacoes,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def confirmar_grupo_visitas_positivas(target, chave, nome_oficial, confirmado_por=None, numero=None):
    if numero is None:
        ensure_schema(target)
        conn = db_core.connect(target)
        try:
            grupos, _ = _montar_grupos_pendentes(conn)
            grupo = next((item for item in grupos if item["chave"] == str(chave or "")), None)
            numero = grupo["numero_normalizado"] if grupo else None
        finally:
            conn.close()
    return confirmar_grupos_visitas_positivas(
        target,
        [{"chave": chave, "nome_oficial": nome_oficial, "numero": numero}],
        confirmado_por,
    )


def _numero_consultavel(numero):
    chave = normalizar_nome(numero).replace("/", " ")
    invalidos = {"", "0", "sn", "s n", "sem numero", "nao informado"}
    return bool(re.search(r"\d", chave)) and chave not in invalidos


def _coordenadas_candidato(candidato):
    try:
        latitude = float(candidato.get("lat"))
        longitude = float(candidato.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def _avaliar_candidato(candidato, logradouro, numero):
    endereco = candidato.get("address") if isinstance(candidato, dict) else None
    if not isinstance(endereco, dict) or endereco.get("country_code", "").casefold() != "br":
        return None
    municipio = " ".join(
        str(endereco.get(campo) or "")
        for campo in ("city", "town", "municipality", "county")
    )
    if "almirante tamandare" not in normalizar_nome(municipio):
        return None
    rua = next(
        (endereco.get(campo) for campo in ("road", "pedestrian", "residential", "footway") if endereco.get(campo)),
        "",
    )
    if not rua:
        return None
    score_rua, _ = enderecos_core.similaridade_logradouro(logradouro, rua)
    if score_rua < SCORE_MINIMO_SUGESTAO:
        return None
    coordenadas = _coordenadas_candidato(candidato)
    if not coordenadas:
        return None
    numero_retornado = _text(endereco.get("house_number"))
    numero_exato = bool(numero_retornado) and normalizar_nome(numero_retornado) == normalizar_nome(numero)
    return {
        "candidato": candidato,
        "latitude": coordenadas[0],
        "longitude": coordenadas[1],
        "numero_exato": numero_exato,
        "score_rua": score_rua,
        "resultado": _text(candidato.get("display_name")),
    }


def _gravar_geocodificacao(target, id_endereco, **campos):
    permitidos = {
        "latitude", "longitude", "geocodificacao_status", "geocodificacao_fonte",
        "geocodificacao_consulta", "geocodificacao_resultado", "geocodificacao_precisao",
        "geocodificacao_detalhes_json", "geocodificado_em", "geocodificado_por",
    }
    if not campos or set(campos) - permitidos:
        raise ValueError("Campos de geocodificação inválidos.")
    status = campos.get("geocodificacao_status")
    if status and status not in GEOCODIFICACAO_STATUS:
        raise ValueError("Situação de geocodificação inválida.")
    conn = db_core.connect(target)
    try:
        atribuicoes = ", ".join(f"{campo}=?" for campo in campos)
        cursor = conn.execute(
            f"UPDATE {ENDERECOS_TABLE} SET {atribuicoes}, atualizado_em=? WHERE id_endereco=?",
            [*campos.values(), _now(), id_endereco],
        )
        if not cursor.rowcount:
            raise ValueError("Endereço normalizado não encontrado.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_pendentes_geocodificacao(target, limite=100):
    ensure_schema(target)
    try:
        limite = max(1, min(int(limite or 100), 200))
    except (TypeError, ValueError):
        limite = 100
    conn = db_core.connect(target)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM {ENDERECOS_TABLE} WHERE geocodificacao_status='pendente'"
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id_endereco, logradouro_oficial, numero_normalizado
                  FROM {ENDERECOS_TABLE}
                 WHERE geocodificacao_status='pendente'
                 ORDER BY id_endereco LIMIT ?""",
            (limite,),
        ).fetchall()
        return {"enderecos": [db_core.serialize_row(row) for row in rows], "total": total, "limite": limite}
    finally:
        conn.close()


def geocodificar_endereco(target, id_endereco, geocoder=None, forcar=False):
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        row = conn.execute(
            f"SELECT * FROM {ENDERECOS_TABLE} WHERE id_endereco=?", (id_endereco,)
        ).fetchone()
        if not row:
            raise ValueError("Endereço normalizado não encontrado.")
        endereco = db_core.serialize_row(row)
    finally:
        conn.close()
    if not forcar and endereco.get("geocodificacao_status") in {"automatico", "manual"}:
        return {"id_endereco": id_endereco, "status": endereco["geocodificacao_status"], "em_cache": True}

    logradouro = endereco["logradouro_oficial"]
    numero = endereco["numero_normalizado"]
    consulta = f"{logradouro}, {numero}, Almirante Tamandaré - PR"
    if not _numero_consultavel(numero):
        _gravar_geocodificacao(
            target, id_endereco, latitude=None, longitude=None,
            geocodificacao_status="aguarda_manual", geocodificacao_fonte=None,
            geocodificacao_consulta=consulta,
            geocodificacao_resultado="Número ausente ou inválido.",
            geocodificacao_precisao=None, geocodificacao_detalhes_json=None,
            geocodificado_em=_now(), geocodificado_por=None,
        )
        return {"id_endereco": id_endereco, "status": "aguarda_manual", "mensagem": "Endereço sem número válido."}

    buscar = geocoder or geocodificacao.buscar_nominatim
    try:
        candidatos = buscar(logradouro, numero)
    except geocodificacao.GeocodificacaoErro:
        _gravar_geocodificacao(
            target, id_endereco, geocodificacao_status="erro",
            geocodificacao_fonte="Nominatim / OpenStreetMap",
            geocodificacao_consulta=consulta, geocodificado_em=_now(),
        )
        raise

    avaliados = [item for item in (_avaliar_candidato(c, logradouro, numero) for c in candidatos) if item]
    # Um numero coincidente nao basta se o nome da via divergir demais. Nesse
    # caso o ponto ainda pode ajudar a revisao, mas nunca vira automatico.
    exatos = [
        item for item in avaliados
        if item["numero_exato"] and item["score_rua"] >= 90
    ]
    escolhido = max(exatos or avaliados, key=lambda item: item["score_rua"], default=None)
    if not escolhido:
        _gravar_geocodificacao(
            target, id_endereco, latitude=None, longitude=None,
            geocodificacao_status="nao_encontrado", geocodificacao_fonte="Nominatim / OpenStreetMap",
            geocodificacao_consulta=consulta, geocodificacao_resultado=None,
            geocodificacao_precisao=None,
            geocodificacao_detalhes_json=json.dumps(candidatos[:5], ensure_ascii=False),
            geocodificado_em=_now(), geocodificado_por=None,
        )
        return {"id_endereco": id_endereco, "status": "nao_encontrado", "mensagem": "Nenhum resultado compatível no município."}

    automatico = escolhido in exatos
    status = "automatico" if automatico else "aproximado"
    precisao = "numero_exato" if automatico else "logradouro_aproximado"
    _gravar_geocodificacao(
        target, id_endereco, latitude=escolhido["latitude"], longitude=escolhido["longitude"],
        geocodificacao_status=status, geocodificacao_fonte="Nominatim / OpenStreetMap",
        geocodificacao_consulta=consulta, geocodificacao_resultado=escolhido["resultado"],
        geocodificacao_precisao=precisao,
        geocodificacao_detalhes_json=json.dumps(escolhido["candidato"], ensure_ascii=False),
        geocodificado_em=_now(), geocodificado_por=None,
    )
    return {
        "id_endereco": id_endereco, "status": status,
        "latitude": escolhido["latitude"], "longitude": escolhido["longitude"],
        "resultado": escolhido["resultado"],
    }


def salvar_coordenadas_manuais(target, id_endereco, latitude, longitude, usuario=None):
    ensure_schema(target)
    if _text(latitude) == "" and _text(longitude) == "":
        _gravar_geocodificacao(
            target, id_endereco, latitude=None, longitude=None,
            geocodificacao_status="aguarda_manual", geocodificacao_fonte=None,
            geocodificacao_resultado="Coordenadas manuais removidas.",
            geocodificacao_precisao=None, geocodificacao_detalhes_json=None,
            geocodificado_em=_now(), geocodificado_por=_text(usuario) or None,
        )
        return {"id_endereco": id_endereco, "status": "aguarda_manual", "latitude": None, "longitude": None}
    if _text(latitude) == "" or _text(longitude) == "":
        raise ValueError("Informe latitude e longitude juntas.")
    try:
        lat = float(str(latitude).replace(",", "."))
        lon = float(str(longitude).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError("Latitude e longitude devem ser números válidos.") from exc
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude ou longitude fora do intervalo válido.")
    _gravar_geocodificacao(
        target, id_endereco, latitude=lat, longitude=lon,
        geocodificacao_status="manual", geocodificacao_fonte="Informado manualmente",
        geocodificacao_resultado="Coordenadas revisadas manualmente.",
        geocodificacao_precisao="manual", geocodificacao_detalhes_json=None,
        geocodificado_em=_now(), geocodificado_por=_text(usuario) or None,
    )
    return {"id_endereco": id_endereco, "status": "manual", "latitude": lat, "longitude": lon}


def listar_enderecos_vinculados(target, busca="", pagina=1, por_pagina=50):
    ensure_schema(target)
    try:
        pagina = max(1, int(pagina or 1))
        por_pagina = max(1, min(int(por_pagina or 50), 200))
    except (TypeError, ValueError):
        pagina, por_pagina = 1, 50
    termo = str(busca or "").strip().casefold()
    conn = db_core.connect(target)
    try:
        rows = conn.execute(
            f"""SELECT e.id_endereco, e.logradouro_oficial, e.numero_normalizado,
                       e.atualizado_em, e.confirmado_por, e.latitude, e.longitude,
                       e.geocodificacao_status, e.geocodificacao_precisao, ve.id_visita,
                       ve.logradouro_bruto, ve.numero_bruto, v.data, v.tipo,
                       COALESCE(l.nome,v.localidade) AS localidade
                  FROM {ENDERECOS_TABLE} e
                  JOIN {VINCULOS_TABLE} ve ON ve.id_endereco=e.id_endereco
                  JOIN visitas v ON v.id_visita=ve.id_visita
                  LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                 ORDER BY e.logradouro_oficial, e.numero_normalizado, v.data DESC"""
        ).fetchall()
        enderecos = {}
        for row in rows:
            item = enderecos.setdefault(
                row["id_endereco"],
                {
                    "id_endereco": row["id_endereco"],
                    "logradouro_oficial": row["logradouro_oficial"],
                    "numero_normalizado": row["numero_normalizado"],
                    "atualizado_em": row["atualizado_em"],
                    "confirmado_por": row["confirmado_por"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "geocodificacao_status": row["geocodificacao_status"],
                    "geocodificacao_precisao": row["geocodificacao_precisao"],
                    "visitas": 0,
                    "variacoes": set(),
                    "localidades": set(),
                    "data_inicial": None,
                    "data_final": None,
                },
            )
            item["visitas"] += 1
            bruto = f"{row['logradouro_bruto'] or '(sem logradouro)'}, {row['numero_bruto'] or '(sem número)'}"
            item["variacoes"].add(bruto)
            if row["localidade"]:
                item["localidades"].add(row["localidade"])
            data = str(row["data"] or "")
            item["data_inicial"] = min(filter(None, (item["data_inicial"], data)), default=None)
            item["data_final"] = max(filter(None, (item["data_final"], data)), default=None)
        lista = []
        for item in enderecos.values():
            item["variacoes"] = sorted(item["variacoes"], key=str.casefold)
            item["localidades"] = sorted(item["localidades"], key=str.casefold)
            texto = " ".join(
                [item["logradouro_oficial"], item["numero_normalizado"], *item["variacoes"], *item["localidades"]]
            ).casefold()
            if not termo or termo in texto:
                lista.append(item)
        lista.sort(key=lambda item: (item["logradouro_oficial"].casefold(), item["numero_normalizado"]))
        total = len(lista)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(pagina, total_paginas)
        inicio = (pagina - 1) * por_pagina
        return {"registros": lista[inicio:inicio + por_pagina], "total": total, "pagina": pagina, "total_paginas": total_paginas}
    finally:
        conn.close()


def detalhar_endereco_vinculado(target, id_endereco):
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        endereco = conn.execute(
            f"SELECT * FROM {ENDERECOS_TABLE} WHERE id_endereco=?", (id_endereco,)
        ).fetchone()
        if not endereco:
            raise ValueError("Endereço normalizado não encontrado.")
        visitas = conn.execute(
            f"""SELECT v.id_visita, v.data, v.tipo, COALESCE(l.nome,v.localidade) AS localidade,
                       v.quarteirao, v.logradouro, v.numero, v.morador, v.visita,
                       ve.logradouro_bruto, ve.numero_bruto, ve.confirmado_em, ve.confirmado_por
                  FROM {VINCULOS_TABLE} ve
                  JOIN visitas v ON v.id_visita=ve.id_visita
                  LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                 WHERE ve.id_endereco=?
                 ORDER BY v.data DESC, v.id_visita DESC""",
            (id_endereco,),
        ).fetchall()
        return {
            "endereco": db_core.serialize_row(endereco),
            "visitas": [db_core.serialize_row(row) for row in visitas],
        }
    finally:
        conn.close()


def desfazer_vinculo(target, id_endereco, id_visita):
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        row = conn.execute(
            f"SELECT 1 FROM {VINCULOS_TABLE} WHERE id_endereco=? AND id_visita=?",
            (id_endereco, id_visita),
        ).fetchone()
        if not row:
            raise ValueError("Vínculo não encontrado.")
        conn.execute(f"DELETE FROM {VINCULOS_TABLE} WHERE id_endereco=? AND id_visita=?", (id_endereco, id_visita))
        restantes = conn.execute(
            f"SELECT COUNT(*) FROM {VINCULOS_TABLE} WHERE id_endereco=?", (id_endereco,)
        ).fetchone()[0]
        if not restantes:
            conn.execute(f"DELETE FROM {ENDERECOS_TABLE} WHERE id_endereco=?", (id_endereco,))
        conn.commit()
        return {"id_endereco": id_endereco, "id_visita": id_visita, "endereco_removido": not bool(restantes)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _decode_csv(content):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o CSV enviado.")


def _parse_csv(content):
    if not content:
        raise ValueError("O arquivo CSV está vazio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("O CSV excede o limite de 5 MB.")
    text = _decode_csv(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = {str(name or "").strip().casefold() for name in reader.fieldnames or []}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError("CSV sem coluna(s) obrigatória(s): " + ", ".join(sorted(missing)))

    records = []
    ids = set()
    for number, raw in enumerate(reader, start=2):
        row = {str(key or "").strip().casefold(): value for key, value in raw.items()}
        identifier = _text(row.get("id_logr"))
        name = _text(row.get("nome"))
        locality = _text(row.get("localidade"))
        if not identifier or not name or not locality:
            raise ValueError(f"Linha {number}: id_logr, nome e localidade são obrigatórios.")
        if identifier in ids:
            raise ValueError(f"Linha {number}: id_logr repetido no arquivo ({identifier}).")
        ids.add(identifier)
        normalized = normalizar_nome(name)
        if not normalized:
            raise ValueError(f"Linha {number}: nome inválido.")
        fingerprint = hashlib.sha256(
            f"{identifier}\x1f{name}\x1f{locality}".encode("utf-8")
        ).hexdigest()
        records.append(
            {
                "id_logradouro": identifier,
                "nome": name,
                "nome_normalizado": normalized,
                "localidade": locality,
                "origem_hash": fingerprint,
            }
        )
    if not records:
        raise ValueError("O CSV não contém logradouros.")
    return records


def resumo(target):
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        ativo = _ativo_verdadeiro_sql(conn)
        row = conn.execute(
            f"""SELECT COUNT(*) AS trechos,
                       COUNT(DISTINCT nome_normalizado) AS nomes_normalizados,
                       COUNT(DISTINCT localidade) AS localidades,
                       MAX(importado_em) AS ultima_importacao
                  FROM {TABLE} WHERE {ativo}"""
        ).fetchone()
        resultado = db_core.serialize_row(row)
        resultado["enderecos_confirmados"] = conn.execute(
            f"SELECT COUNT(*) FROM {ENDERECOS_TABLE}"
        ).fetchone()[0]
        resultado["visitas_vinculadas"] = conn.execute(
            f"SELECT COUNT(*) FROM {VINCULOS_TABLE}"
        ).fetchone()[0]
        resultado["enderecos_com_coordenadas"] = conn.execute(
            f"SELECT COUNT(*) FROM {ENDERECOS_TABLE} WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchone()[0]
        resultado["coordenadas_para_revisar"] = conn.execute(
            f"""SELECT COUNT(*) FROM {ENDERECOS_TABLE}
                 WHERE geocodificacao_status IN ('aproximado','nao_encontrado','erro','aguarda_manual')"""
        ).fetchone()[0]
        resultado["geocodificacao_pendente"] = conn.execute(
            f"SELECT COUNT(*) FROM {ENDERECOS_TABLE} WHERE geocodificacao_status='pendente'"
        ).fetchone()[0]
        return resultado
    finally:
        conn.close()


def listar(target, busca="", limite=300):
    ensure_schema(target)
    try:
        limite = max(1, min(int(limite or 300), 1000))
    except (TypeError, ValueError):
        limite = 300
    search = _text(busca)
    normalized_search = normalizar_nome(search)
    conn = db_core.connect(target)
    try:
        where, params = f"WHERE {_ativo_verdadeiro_sql(conn)}", []
        if search:
            where += " AND (nome_normalizado LIKE ? OR LOWER(localidade) LIKE LOWER(?))"
            params.extend([f"%{normalized_search}%", f"%{search}%"])
        rows = conn.execute(
            f"""SELECT id_logradouro, nome, localidade, atualizado_em
                  FROM {TABLE} {where}
                 ORDER BY nome, localidade, id_logradouro LIMIT ?""",
            params + [limite],
        ).fetchall()
        return {"registros": [db_core.serialize_row(row) for row in rows], "limite": limite}
    finally:
        conn.close()


def importar_csv(target, content):
    records = _parse_csv(content)
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        existing = {
            row["id_logradouro"]: row["origem_hash"]
            for row in conn.execute(f"SELECT id_logradouro, origem_hash FROM {TABLE}")
        }
        now = _now()
        ativo = _ativo_verdadeiro_valor(conn)
        inserted = updated = unchanged = 0
        for record in records:
            previous = existing.get(record["id_logradouro"])
            values = (
                record["id_logradouro"], record["nome"], record["nome_normalizado"],
                record["localidade"], ativo, record["origem_hash"], now, now,
            )
            if previous is None:
                conn.execute(
                    f"""INSERT INTO {TABLE}
                           (id_logradouro,nome,nome_normalizado,localidade,ativo,
                            origem_hash,importado_em,atualizado_em)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    values,
                )
                inserted += 1
            elif previous != record["origem_hash"]:
                conn.execute(
                    f"""UPDATE {TABLE}
                           SET nome=?, nome_normalizado=?, localidade=?, ativo=?,
                               origem_hash=?, atualizado_em=?
                         WHERE id_logradouro=?""",
                    (
                        record["nome"], record["nome_normalizado"], record["localidade"],
                        ativo, record["origem_hash"], now, record["id_logradouro"],
                    ),
                )
                updated += 1
            else:
                unchanged += 1
        conn.commit()
        return {
            "linhas": len(records), "inseridos": inserted,
            "atualizados": updated, "sem_alteracao": unchanged,
            "observacao": "IDs ausentes do arquivo foram preservados; nenhuma linha é excluída automaticamente.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
