import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher

from app_core import db as db_core
from app_core import esporotricose as esporotricose_core


PACIENTES_TABLE = "esporotricose_pacientes_humanos"
ACOMPANHAMENTOS_TABLE = "esporotricose_pacientes_acompanhamentos"
ANEXOS_TABLE = "esporotricose_pacientes_anexos"
IMOVEIS_TABLE = "esporotricose_paciente_imoveis"
ANIMAIS_TABLE = "esporotricose_paciente_animais"
STATUS = ("Em tratamento", "Acabou tratamento", "Outros")


class ValidationError(Exception):
    pass


def ensure_schema(conn):
    esporotricose_core.ensure_schema(conn)
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS esporotricose_pacientes_humanos (
            id_paciente INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data_nascimento DATE,
            cartao_sus TEXT,
            nome_mae TEXT,
            telefone TEXT,
            data_notificacao DATE,
            status TEXT NOT NULL CHECK(status IN ('Em tratamento','Acabou tratamento','Outros')),
            status_outro TEXT,
            id_localidade INTEGER REFERENCES localidades(id_localidade),
            localidade TEXT,
            quarteirao TEXT,
            logradouro TEXT,
            numero TEXT,
            complemento TEXT,
            latitude REAL,
            longitude REAL,
            observacoes TEXT,
            criado_por TEXT,
            atualizado_por TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_esporo_pacientes_sus
            ON esporotricose_pacientes_humanos(cartao_sus)
            WHERE cartao_sus IS NOT NULL AND TRIM(cartao_sus) <> '';
        CREATE INDEX IF NOT EXISTS idx_esporo_pacientes_status
            ON esporotricose_pacientes_humanos(status);
        CREATE INDEX IF NOT EXISTS idx_esporo_pacientes_localidade
            ON esporotricose_pacientes_humanos(id_localidade, localidade);

        CREATE TABLE IF NOT EXISTS esporotricose_pacientes_acompanhamentos (
            id_acompanhamento INTEGER PRIMARY KEY AUTOINCREMENT,
            id_paciente INTEGER NOT NULL REFERENCES esporotricose_pacientes_humanos(id_paciente) ON DELETE CASCADE,
            data DATE NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Em tratamento','Acabou tratamento','Outros')),
            status_outro TEXT,
            observacoes TEXT,
            criado_por TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_esporo_pacientes_acompanhamentos
            ON esporotricose_pacientes_acompanhamentos(id_paciente, data);

        CREATE TABLE IF NOT EXISTS esporotricose_pacientes_anexos (
            id_anexo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_paciente INTEGER NOT NULL REFERENCES esporotricose_pacientes_humanos(id_paciente) ON DELETE CASCADE,
            nome_original TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            caminho_rel TEXT NOT NULL,
            mime_type TEXT,
            tamanho INTEGER NOT NULL,
            criado_por TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_esporo_pacientes_anexos
            ON esporotricose_pacientes_anexos(id_paciente);

        CREATE TABLE IF NOT EXISTS esporotricose_paciente_imoveis (
            id_paciente INTEGER NOT NULL REFERENCES esporotricose_pacientes_humanos(id_paciente) ON DELETE CASCADE,
            id_imovel INTEGER NOT NULL REFERENCES esporotricose_imoveis(id_imovel) ON DELETE CASCADE,
            vinculado_por TEXT,
            vinculado_em TEXT NOT NULL,
            PRIMARY KEY(id_paciente, id_imovel)
        );
        CREATE TABLE IF NOT EXISTS esporotricose_paciente_animais (
            id_paciente INTEGER NOT NULL REFERENCES esporotricose_pacientes_humanos(id_paciente) ON DELETE CASCADE,
            id_animal_doente INTEGER NOT NULL REFERENCES esporotricose_doentes_animais(id_animal_doente) ON DELETE CASCADE,
            vinculado_por TEXT,
            vinculado_em TEXT NOT NULL,
            PRIMARY KEY(id_paciente, id_animal_doente)
        );
        """
    )
    conn.commit()


def _texto(valor, limite=None):
    texto = str(valor or "").strip()
    if limite and len(texto) > limite:
        raise ValidationError(f"Campo com mais de {limite} caracteres.")
    return texto or None


def _data(valor, nome):
    valor = _texto(valor)
    if not valor:
        return None
    try:
        parsed = date.fromisoformat(valor)
    except ValueError as exc:
        raise ValidationError(f"{nome} inválida.") from exc
    if parsed > date.today():
        raise ValidationError(f"{nome} não pode estar no futuro.")
    return parsed.isoformat()


def _coordenada(valor, nome, minimo, maximo):
    valor = _texto(valor)
    if not valor:
        return None
    try:
        numero = float(valor.replace(",", "."))
    except ValueError as exc:
        raise ValidationError(f"{nome} inválida.") from exc
    if not minimo <= numero <= maximo:
        raise ValidationError(f"{nome} fora da faixa permitida.")
    return numero


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = re.sub(r"\b(r|rua)\.?\b", "rua", texto)
    texto = re.sub(r"\b(av|avenida)\.?\b", "avenida", texto)
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _id_localidade(conn, nome):
    if not nome:
        return None
    alvo = _normalizar(nome)
    for row in conn.execute("SELECT id_localidade, nome FROM localidades"):
        if _normalizar(row["nome"]) == alvo:
            return row["id_localidade"]
    return None


def _validar_payload(conn, dados, id_paciente=None):
    nome = _texto(dados.get("nome"), 180)
    if not nome:
        raise ValidationError("Informe o nome do paciente.")
    status = _texto(dados.get("status"), 40) or STATUS[0]
    if status not in STATUS:
        raise ValidationError("Status inválido.")
    status_outro = _texto(dados.get("status_outro"), 180)
    if status == "Outros" and not status_outro:
        raise ValidationError("Descreva o status em Outros.")
    if status != "Outros":
        status_outro = None
    cartao_sus = _texto(dados.get("cartao_sus"), 30)
    if cartao_sus:
        duplicado = conn.execute(
            f"SELECT id_paciente FROM {PACIENTES_TABLE} WHERE cartao_sus=? AND id_paciente<>?",
            (cartao_sus, int(id_paciente or 0)),
        ).fetchone()
        if duplicado:
            raise ValidationError("Já existe um paciente com este cartão SUS.")
    latitude = _coordenada(dados.get("latitude"), "Latitude", -90, 90)
    longitude = _coordenada(dados.get("longitude"), "Longitude", -180, 180)
    if (latitude is None) != (longitude is None):
        raise ValidationError("Informe latitude e longitude juntas.")
    localidade = _texto(dados.get("localidade"), 120)
    return {
        "nome": nome,
        "data_nascimento": _data(dados.get("data_nascimento"), "Data de nascimento"),
        "cartao_sus": cartao_sus,
        "nome_mae": _texto(dados.get("nome_mae"), 180),
        "telefone": _texto(dados.get("telefone"), 60),
        "data_notificacao": _data(dados.get("data_notificacao"), "Data de notificação"),
        "status": status,
        "status_outro": status_outro,
        "id_localidade": _id_localidade(conn, localidade),
        "localidade": localidade,
        "quarteirao": _texto(dados.get("quarteirao"), 40),
        "logradouro": _texto(dados.get("logradouro"), 220),
        "numero": _texto(dados.get("numero"), 40),
        "complemento": _texto(dados.get("complemento"), 120),
        "latitude": latitude,
        "longitude": longitude,
        "observacoes": _texto(dados.get("observacoes"), 5000),
    }


def salvar_paciente(target, dados, usuario):
    conn = db_core.connect(target)
    ensure_schema(conn)
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        id_paciente = dados.get("id_paciente")
        valores = _validar_payload(conn, dados, id_paciente)
        colunas = list(valores)
        if id_paciente:
            existe = conn.execute(
                f"SELECT 1 FROM {PACIENTES_TABLE} WHERE id_paciente=?", (id_paciente,)
            ).fetchone()
            if not existe:
                raise ValidationError("Paciente não encontrado.")
            conn.execute(
                f"UPDATE {PACIENTES_TABLE} SET "
                + ", ".join(f"{c}=?" for c in colunas)
                + ", atualizado_por=?, atualizado_em=? WHERE id_paciente=?",
                [*[valores[c] for c in colunas], usuario, agora, id_paciente],
            )
            resultado = int(id_paciente)
        else:
            resultado = db_core.insert_and_get_id(
                conn,
                f"INSERT INTO {PACIENTES_TABLE} ("
                + ", ".join(colunas)
                + ", criado_por, atualizado_por, criado_em, atualizado_em) VALUES ("
                + ", ".join("?" for _ in range(len(colunas) + 4))
                + ")",
                [*[valores[c] for c in colunas], usuario, usuario, agora, agora],
                "id_paciente",
            )
        conn.commit()
        return resultado
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _mascarar_sus(valor):
    valor = str(valor or "")
    if not valor:
        return ""
    return ("•" * max(0, len(valor) - 4)) + valor[-4:]


def listar_pacientes(target, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        where_base = ["1=1"]
        params_base = []
        if filtros.get("localidade"):
            where_base.append("LOWER(COALESCE(p.localidade,''))=LOWER(?)")
            params_base.append(filtros["localidade"])
        if filtros.get("busca"):
            busca = f"%{filtros['busca'].strip().lower()}%"
            where_base.append("(LOWER(p.nome) LIKE ? OR LOWER(COALESCE(p.nome_mae,'')) LIKE ? OR LOWER(COALESCE(p.logradouro,'')) LIKE ? OR LOWER(COALESCE(p.quarteirao,'')) LIKE ? OR LOWER(COALESCE(p.telefone,'')) LIKE ?)")
            params_base.extend([busca] * 5)
        where = list(where_base)
        params = list(params_base)
        if filtros.get("status"):
            where.append("p.status=?")
            params.append(filtros["status"])
        try:
            pagina = max(1, int(filtros.get("pagina") or 1))
            por_pagina = max(10, min(100, int(filtros.get("por_pagina") or 30)))
        except (TypeError, ValueError):
            pagina, por_pagina = 1, 30
        total = conn.execute(
            f"SELECT COUNT(*) FROM {PACIENTES_TABLE} p WHERE {' AND '.join(where)}", params
        ).fetchone()[0]
        paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(pagina, paginas)
        rows = [db_core.serialize_row(r) for r in conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM {ACOMPANHAMENTOS_TABLE} a WHERE a.id_paciente=p.id_paciente) AS acompanhamentos,
                       (SELECT COUNT(*) FROM {ANEXOS_TABLE} x WHERE x.id_paciente=p.id_paciente) AS anexos,
                       (SELECT COUNT(*) FROM {IMOVEIS_TABLE} i WHERE i.id_paciente=p.id_paciente) AS imoveis,
                       (SELECT COUNT(*) FROM {ANIMAIS_TABLE} an WHERE an.id_paciente=p.id_paciente) AS animais
                  FROM {PACIENTES_TABLE} p
                 WHERE {' AND '.join(where)}
                 ORDER BY CASE WHEN p.data_notificacao IS NULL THEN 1 ELSE 0 END,
                          p.data_notificacao DESC, p.criado_em DESC, p.nome
                 LIMIT ? OFFSET ?""",
            [*params, por_pagina, (pagina - 1) * por_pagina],
        )]
        for row in rows:
            row["cartao_sus"] = _mascarar_sus(row.get("cartao_sus"))
        totais = {status: conn.execute(
            f"SELECT COUNT(*) FROM {PACIENTES_TABLE} p WHERE {' AND '.join(where_base)} AND p.status=?",
            [*params_base, status],
        ).fetchone()[0] for status in STATUS}
        return {"registros": rows, "total": total, "pagina": pagina, "paginas": paginas, "por_pagina": por_pagina, "status_totais": totais}
    finally:
        conn.close()


def obter_paciente(target, id_paciente):
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        row = conn.execute(f"SELECT * FROM {PACIENTES_TABLE} WHERE id_paciente=?", (id_paciente,)).fetchone()
        if not row:
            return None
        paciente = db_core.serialize_row(row)
        paciente["acompanhamentos"] = [db_core.serialize_row(r) for r in conn.execute(
            f"SELECT * FROM {ACOMPANHAMENTOS_TABLE} WHERE id_paciente=? ORDER BY data DESC, id_acompanhamento DESC",
            (id_paciente,),
        )]
        paciente["anexos"] = [db_core.serialize_row(r) for r in conn.execute(
            f"SELECT * FROM {ANEXOS_TABLE} WHERE id_paciente=? ORDER BY criado_em DESC, id_anexo DESC",
            (id_paciente,),
        )]
        paciente["imoveis"] = [db_core.serialize_row(r) for r in conn.execute(
            f"""SELECT i.id_imovel, i.localidade, i.quarteirao,
                       MIN(v.logradouro) AS logradouro, MIN(v.numero) AS numero,
                       COUNT(DISTINCT vi.id_visita) AS visitas
                  FROM {IMOVEIS_TABLE} pi
                  JOIN esporotricose_imoveis i ON i.id_imovel=pi.id_imovel
             LEFT JOIN esporotricose_visita_imoveis vi ON vi.id_imovel=i.id_imovel
             LEFT JOIN esporotricose_visitas v ON v.id_visita=vi.id_visita
                 WHERE pi.id_paciente=?
                 GROUP BY i.id_imovel, i.localidade, i.quarteirao
                 ORDER BY i.localidade, i.quarteirao""", (id_paciente,)
        )]
        paciente["animais"] = [db_core.serialize_row(r) for r in conn.execute(
            f"""SELECT d.id_animal_doente, d.nome, d.especie, d.tutor, d.status, d.localidade, d.quarteirao, d.endereco
                  FROM {ANIMAIS_TABLE} pa
                  JOIN esporotricose_doentes_animais d ON d.id_animal_doente=pa.id_animal_doente
                 WHERE pa.id_paciente=? ORDER BY d.nome""", (id_paciente,)
        )]
        return paciente
    finally:
        conn.close()


def salvar_acompanhamento(target, id_paciente, dados, usuario):
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        if not conn.execute(f"SELECT 1 FROM {PACIENTES_TABLE} WHERE id_paciente=?", (id_paciente,)).fetchone():
            raise ValidationError("Paciente não encontrado.")
        status = _texto(dados.get("status"), 40)
        if status not in STATUS:
            raise ValidationError("Status inválido.")
        status_outro = _texto(dados.get("status_outro"), 180)
        if status == "Outros" and not status_outro:
            raise ValidationError("Descreva o status em Outros.")
        if status != "Outros":
            status_outro = None
        data_registro = _data(dados.get("data"), "Data")
        if not data_registro:
            raise ValidationError("Informe a data do acompanhamento.")
        agora = datetime.now().isoformat(timespec="seconds")
        id_acompanhamento = db_core.insert_and_get_id(
            conn,
            f"INSERT INTO {ACOMPANHAMENTOS_TABLE} (id_paciente,data,status,status_outro,observacoes,criado_por,criado_em) VALUES (?,?,?,?,?,?,?)",
            (id_paciente, data_registro, status, status_outro, _texto(dados.get("observacoes"), 5000), usuario, agora),
            "id_acompanhamento",
        )
        conn.execute(
            f"UPDATE {PACIENTES_TABLE} SET status=?, status_outro=?, atualizado_por=?, atualizado_em=? WHERE id_paciente=?",
            (status, status_outro, usuario, agora, id_paciente),
        )
        conn.commit()
        return id_acompanhamento
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def salvar_anexos(target, id_paciente, anexos, usuario):
    conn = db_core.connect(target)
    ensure_schema(conn)
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        if not conn.execute(f"SELECT 1 FROM {PACIENTES_TABLE} WHERE id_paciente=?", (id_paciente,)).fetchone():
            raise ValidationError("Paciente não encontrado.")
        ids = []
        for anexo in anexos:
            ids.append(db_core.insert_and_get_id(
                conn,
                f"INSERT INTO {ANEXOS_TABLE} (id_paciente,nome_original,nome_arquivo,caminho_rel,mime_type,tamanho,criado_por,criado_em) VALUES (?,?,?,?,?,?,?,?)",
                (id_paciente, anexo["nome_original"], anexo["nome_arquivo"], anexo["caminho_rel"], anexo.get("mime_type"), anexo["tamanho"], usuario, agora),
                "id_anexo",
            ))
        conn.commit()
        return ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obter_anexo(target, id_anexo):
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        row = conn.execute(f"SELECT * FROM {ANEXOS_TABLE} WHERE id_anexo=?", (id_anexo,)).fetchone()
        return db_core.serialize_row(row) if row else None
    finally:
        conn.close()


def excluir_anexo(target, id_anexo):
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        row = conn.execute(f"SELECT * FROM {ANEXOS_TABLE} WHERE id_anexo=?", (id_anexo,)).fetchone()
        if not row:
            raise ValidationError("Anexo não encontrado.")
        conn.execute(f"DELETE FROM {ANEXOS_TABLE} WHERE id_anexo=?", (id_anexo,))
        conn.commit()
        return db_core.serialize_row(row)
    finally:
        conn.close()


def sugestoes_vinculos(target, id_paciente):
    paciente = obter_paciente(target, id_paciente)
    if not paciente:
        raise ValidationError("Paciente não encontrado.")
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        local = _normalizar(paciente.get("localidade"))
        quadra = _normalizar(paciente.get("quarteirao"))
        rua = _normalizar(paciente.get("logradouro"))
        numero = _normalizar(paciente.get("numero"))
        imoveis = []
        for r in conn.execute(
            """SELECT i.id_imovel, i.localidade, i.quarteirao, i.logradouro_chave, i.numero_chave,
                      MIN(v.logradouro) AS logradouro, MIN(v.numero) AS numero,
                      COUNT(DISTINCT vi.id_visita) AS visitas
                 FROM esporotricose_imoveis i
            LEFT JOIN esporotricose_visita_imoveis vi ON vi.id_imovel=i.id_imovel
            LEFT JOIN esporotricose_visitas v ON v.id_visita=vi.id_visita
                GROUP BY i.id_imovel, i.localidade, i.quarteirao, i.logradouro_chave, i.numero_chave"""
        ):
            item = db_core.serialize_row(r)
            if local and _normalizar(item.get("localidade")) != local:
                continue
            pontos = 20
            motivos = ["mesma localidade"] if local else []
            if quadra and _normalizar(item.get("quarteirao")) == quadra:
                pontos += 20
                motivos.append("mesmo quarteirão")
            similar_rua = SequenceMatcher(None, rua, _normalizar(item.get("logradouro") or item.get("logradouro_chave"))).ratio() if rua else 0
            pontos += round(similar_rua * 35)
            if similar_rua >= 0.82:
                motivos.append("logradouro semelhante")
            if numero and _normalizar(item.get("numero") or item.get("numero_chave")) == numero:
                pontos += 25
                motivos.append("mesmo número")
            if pontos >= 55:
                item.update({"pontuacao": min(100, pontos), "motivos": motivos})
                imoveis.append(item)
        vinculados_imoveis = {r[0] for r in conn.execute(f"SELECT id_imovel FROM {IMOVEIS_TABLE} WHERE id_paciente=?", (id_paciente,))}
        imoveis = [i for i in imoveis if i["id_imovel"] not in vinculados_imoveis]

        endereco = _normalizar(" ".join(filter(None, [paciente.get("logradouro"), paciente.get("numero")])))
        animais = []
        for r in conn.execute("SELECT id_animal_doente,nome,especie,tutor,status,localidade,quarteirao,endereco FROM esporotricose_doentes_animais"):
            item = db_core.serialize_row(r)
            pontos = 0
            motivos = []
            if local and _normalizar(item.get("localidade")) == local:
                pontos += 25
                motivos.append("mesma localidade")
            if quadra and _normalizar(item.get("quarteirao")) == quadra:
                pontos += 20
                motivos.append("mesmo quarteirão")
            similar = SequenceMatcher(None, endereco, _normalizar(item.get("endereco"))).ratio() if endereco else 0
            pontos += round(similar * 55)
            if similar >= 0.75:
                motivos.append("endereço semelhante")
            if pontos >= 55:
                item.update({"pontuacao": min(100, pontos), "motivos": motivos})
                animais.append(item)
        vinculados_animais = {r[0] for r in conn.execute(f"SELECT id_animal_doente FROM {ANIMAIS_TABLE} WHERE id_paciente=?", (id_paciente,))}
        animais = [a for a in animais if a["id_animal_doente"] not in vinculados_animais]
        imoveis.sort(key=lambda x: (-x["pontuacao"], x.get("localidade") or ""))
        animais.sort(key=lambda x: (-x["pontuacao"], x.get("nome") or ""))
        return {"imoveis": imoveis[:30], "animais": animais[:30]}
    finally:
        conn.close()


def alterar_vinculo(target, id_paciente, tipo, id_alvo, usuario, vincular=True):
    if tipo not in {"imovel", "animal"}:
        raise ValidationError("Tipo de vínculo inválido.")
    tabela = IMOVEIS_TABLE if tipo == "imovel" else ANIMAIS_TABLE
    coluna = "id_imovel" if tipo == "imovel" else "id_animal_doente"
    alvo_tabela = "esporotricose_imoveis" if tipo == "imovel" else "esporotricose_doentes_animais"
    conn = db_core.connect(target)
    ensure_schema(conn)
    try:
        if not conn.execute(f"SELECT 1 FROM {PACIENTES_TABLE} WHERE id_paciente=?", (id_paciente,)).fetchone():
            raise ValidationError("Paciente não encontrado.")
        if not conn.execute(f"SELECT 1 FROM {alvo_tabela} WHERE {coluna}=?", (id_alvo,)).fetchone():
            raise ValidationError("Registro de vínculo não encontrado.")
        if vincular:
            if getattr(conn, "backend", "sqlite") == "postgresql":
                sql = f"INSERT INTO {tabela} (id_paciente,{coluna},vinculado_por,vinculado_em) VALUES (?,?,?,?) ON CONFLICT (id_paciente,{coluna}) DO NOTHING"
            else:
                sql = f"INSERT OR IGNORE INTO {tabela} (id_paciente,{coluna},vinculado_por,vinculado_em) VALUES (?,?,?,?)"
            conn.execute(sql, (id_paciente, id_alvo, usuario, datetime.now().isoformat(timespec="seconds")))
        else:
            conn.execute(f"DELETE FROM {tabela} WHERE id_paciente=? AND {coluna}=?", (id_paciente, id_alvo))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
