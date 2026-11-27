"""Controle administrativo de créditos de folga e ocorrências de pessoal."""

from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app_core import db


ORIGENS = frozenset({
    "sabado", "domingo_feriado", "evento_campanha",
    "servico_extraordinario", "ajuste_administrativo", "outro",
})
CLASSIFICACOES = frozenset({"pendente", "justificada", "abonada", "injustificada"})
TIPOS = frozenset({"folga", "falta"})
MAX_ID = 2**63 - 1

try:
    FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:
    # Windows pode estar sem a base IANA. O expediente corrente é UTC−03.
    FUSO_LOCAL = timezone(timedelta(hours=-3))


class Conflito(ValueError):
    """O lançamento conflita com o saldo ou com o estado atual."""


class NaoEncontrado(ValueError):
    """Servidor, crédito ou ocorrência inexistente."""


def ensure_schema(conn):
    """Prepara o ambiente SQLite na transação de inicialização da aplicação."""
    if _postgresql(conn):
        return
    comandos = (
        """CREATE TABLE IF NOT EXISTS pessoal_folga_creditos (
            id_credito INTEGER PRIMARY KEY AUTOINCREMENT,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            data_aquisicao TEXT NOT NULL,
            validade TEXT NOT NULL CHECK (validade >= data_aquisicao),
            unidades INTEGER NOT NULL CHECK (unidades > 0),
            origem TEXT NOT NULL CHECK (origem IN ('sabado', 'domingo_feriado', 'evento_campanha',
                'servico_extraordinario', 'ajuste_administrativo', 'outro')),
            descricao TEXT NOT NULL,
            referencia TEXT,
            setor TEXT NOT NULL CHECK (setor IN ('endemias', 'ambiental')),
            criado_por INTEGER NOT NULL REFERENCES usuarios(id_usuario),
            criado_em TEXT NOT NULL,
            cancelado_por INTEGER REFERENCES usuarios(id_usuario),
            cancelado_em TEXT,
            motivo_cancelamento TEXT,
            UNIQUE (id_credito, id_agente)
        )""",
        """CREATE TABLE IF NOT EXISTS pessoal_ocorrencias (
            id_ocorrencia INTEGER PRIMARY KEY AUTOINCREMENT,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            data TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('folga', 'falta')),
            dia_inteiro INTEGER NOT NULL CHECK (dia_inteiro IN (0, 1)),
            hora_inicio TEXT,
            hora_fim TEXT,
            unidades INTEGER NOT NULL,
            status TEXT NOT NULL,
            classificacao TEXT,
            observacao TEXT,
            setor TEXT NOT NULL CHECK (setor IN ('endemias', 'ambiental')),
            criado_por INTEGER NOT NULL REFERENCES usuarios(id_usuario),
            criado_em TEXT NOT NULL,
            atualizado_por INTEGER REFERENCES usuarios(id_usuario),
            atualizado_em TEXT,
            motivo_classificacao TEXT,
            cancelado_por INTEGER REFERENCES usuarios(id_usuario),
            cancelado_em TEXT,
            motivo_cancelamento TEXT,
            CHECK ((dia_inteiro = 1 AND hora_inicio IS NULL AND hora_fim IS NULL)
                OR (dia_inteiro = 0 AND hora_inicio IS NOT NULL AND hora_fim IS NOT NULL AND hora_inicio < hora_fim)),
            CHECK ((tipo = 'folga' AND classificacao IS NULL AND unidades = dia_inteiro + 1
                    AND status IN ('agendada', 'utilizada', 'cancelada'))
                OR (tipo = 'falta' AND classificacao IS NOT NULL
                    AND classificacao IN ('pendente', 'justificada', 'abonada', 'injustificada')
                    AND unidades = 0 AND status IN ('registrada', 'cancelada'))),
            UNIQUE (id_ocorrencia, id_agente)
        )""",
        """CREATE TABLE IF NOT EXISTS pessoal_folga_consumos (
            id_credito INTEGER NOT NULL,
            id_ocorrencia INTEGER NOT NULL,
            id_agente INTEGER NOT NULL,
            unidades INTEGER NOT NULL CHECK (unidades IN (1, 2)),
            PRIMARY KEY (id_credito, id_ocorrencia),
            FOREIGN KEY (id_credito, id_agente) REFERENCES pessoal_folga_creditos(id_credito, id_agente),
            FOREIGN KEY (id_ocorrencia, id_agente) REFERENCES pessoal_ocorrencias(id_ocorrencia, id_agente)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_pessoal_creditos_validade ON pessoal_folga_creditos(id_agente, validade)",
        "CREATE INDEX IF NOT EXISTS idx_pessoal_ocorrencias_agente_data ON pessoal_ocorrencias(id_agente, data)",
        "CREATE INDEX IF NOT EXISTS idx_pessoal_ocorrencias_data ON pessoal_ocorrencias(data)",
        "CREATE INDEX IF NOT EXISTS idx_pessoal_consumos_ocorrencia ON pessoal_folga_consumos(id_ocorrencia)",
    )
    for comando in comandos:
        conn.execute(comando)


def _postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _agora():
    return datetime.now(FUSO_LOCAL)


def _carimbo(agora):
    return agora.isoformat(timespec="seconds")


def _inteiro(valor, rotulo, limite=MAX_ID):
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{1,19}", valor):
        valor = int(valor)
    if type(valor) is not int or not 1 <= valor <= limite:
        raise ValueError(f"{rotulo} inválido.")
    return valor


def _data(valor, rotulo):
    if type(valor) is date:
        return valor
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ValueError(f"{rotulo} inválida.")


def _hora(valor):
    if type(valor) is time:
        return valor
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{2}:[0-9]{2}", valor):
        try:
            return time.fromisoformat(valor)
        except ValueError:
            pass
    raise ValueError("Informe horários válidos de início e fim.")


def _escolha(valor, opcoes, rotulo):
    if not isinstance(valor, str) or valor not in opcoes:
        raise ValueError(f"{rotulo} inválida.")
    return valor


def _texto(valor, rotulo, limite, *, obrigatorio=False):
    if valor is None:
        valor = ""
    if not isinstance(valor, str) or "\x00" in valor:
        raise ValueError(f"Informe um texto válido para {rotulo}.")
    valor = valor.strip()
    if obrigatorio and not valor:
        raise ValueError(f"Informe {rotulo}.")
    if len(valor) > limite:
        raise ValueError(f"O campo {rotulo} deve ter até {limite} caracteres.")
    return valor or None


def _setor(setor):
    return _escolha(setor or "endemias", {"endemias", "ambiental"}, "Área")


def _iniciar_escrita(conn):
    # No SQLite, adquira a reserva de escrita antes de ler o saldo ou o horário.
    if not _postgresql(conn) and not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")


def _bloquear_servidor(conn, id_agente):
    _iniciar_escrita(conn)
    sql = "SELECT id_agente, ativo FROM agentes WHERE id_agente=?"
    if _postgresql(conn):
        sql += " FOR UPDATE"
    servidor = conn.execute(sql, (id_agente,)).fetchone()
    if not servidor:
        raise NaoEncontrado("Servidor não encontrado.")
    return servidor


def _exigir_ativo(servidor):
    if not servidor["ativo"]:
        raise Conflito("O servidor está inativo. O histórico permanece disponível para consulta e correção.")


def criar_credito(conn, dados, ator, setor):
    id_agente = _inteiro(dados.get("id_agente"), "Servidor")
    aquisicao = _data(dados.get("data_aquisicao"), "Data de aquisição")
    validade = _data(dados.get("validade"), "Data de validade")
    unidades = _inteiro(dados.get("unidades"), "Número de meios períodos", 2**31 - 1)
    origem = _escolha(dados.get("origem"), ORIGENS, "Origem")
    descricao = _texto(dados.get("descricao"), "a descrição da concessão", 1000, obrigatorio=True)
    referencia = _texto(dados.get("referencia"), "referência", 200)
    setor = _setor(setor)
    if validade < aquisicao:
        raise ValueError("A validade deve ser igual ou posterior à data de aquisição.")
    _exigir_ativo(_bloquear_servidor(conn, id_agente))
    agora = _agora()
    if aquisicao > agora.date():
        raise ValueError("A aquisição do crédito deve ter ocorrido até hoje.")
    return db.insert_and_get_id(
        conn,
        """INSERT INTO pessoal_folga_creditos
           (id_agente, data_aquisicao, validade, unidades, origem, descricao, referencia, setor, criado_por, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id_agente, aquisicao.isoformat(), validade.isoformat(), unidades,
         origem, descricao, referencia, setor, ator, _carimbo(agora)),
        "id_credito",
    )


def _horarios(dados):
    dia_inteiro = dados.get("dia_inteiro")
    if type(dia_inteiro) is not bool:
        raise ValueError("Informe se a ocorrência ocupa o dia inteiro.")
    if dia_inteiro:
        if dados.get("hora_inicio") or dados.get("hora_fim"):
            raise ValueError("Uma ocorrência de dia inteiro dispensa horários.")
        return dia_inteiro, None, None
    inicio, fim = _hora(dados.get("hora_inicio")), _hora(dados.get("hora_fim"))
    if inicio >= fim:
        raise ValueError("O horário de fim deve ser posterior ao de início, no mesmo dia.")
    return dia_inteiro, inicio.isoformat(timespec="minutes"), fim.isoformat(timespec="minutes")


def _validar_dia(conn, id_agente, dia, dia_inteiro, inicio, fim, unidades):
    existentes = conn.execute(
        """SELECT dia_inteiro, hora_inicio, hora_fim, unidades
             FROM pessoal_ocorrencias
            WHERE id_agente=? AND data=? AND status <> 'cancelada'""",
        (id_agente, dia),
    ).fetchall()
    for registro in existentes:
        if (dia_inteiro or registro["dia_inteiro"]
                or (_hora(inicio) < _hora(registro["hora_fim"]) and _hora(fim) > _hora(registro["hora_inicio"]))):
            raise Conflito("Já existe uma ocorrência para este servidor no período informado.")
    if unidades + sum(registro["unidades"] for registro in existentes) > 2:
        raise Conflito("O servidor já tem um dia de folga registrado nesta data.")


def _alocar_creditos(conn, id_agente, dia, unidades):
    creditos = conn.execute(
        """SELECT c.id_credito, c.unidades - COALESCE(SUM(
                   CASE WHEN o.status <> 'cancelada' THEN m.unidades ELSE 0 END
               ), 0) AS restante
             FROM pessoal_folga_creditos c
        LEFT JOIN pessoal_folga_consumos m ON m.id_credito=c.id_credito
        LEFT JOIN pessoal_ocorrencias o ON o.id_ocorrencia=m.id_ocorrencia
            WHERE c.id_agente=? AND c.cancelado_em IS NULL AND c.data_aquisicao<=? AND c.validade>=?
         GROUP BY c.id_credito, c.unidades, c.validade, c.data_aquisicao
         ORDER BY c.validade, c.data_aquisicao, c.id_credito""",
        (id_agente, dia, dia),
    ).fetchall()
    restante = unidades
    alocacoes = []
    for credito in creditos:
        alocado = min(credito["restante"], restante)
        if alocado <= 0:
            continue
        alocacoes.append((credito["id_credito"], alocado))
        restante -= alocado
        if not restante:
            return alocacoes
    raise Conflito("Não há saldo de folga suficiente com validade na data escolhida.")


def criar_ocorrencia(conn, dados, ator, setor):
    id_agente = _inteiro(dados.get("id_agente"), "Servidor")
    tipo = _escolha(dados.get("tipo"), TIPOS, "Categoria")
    dia = _data(dados.get("data"), "Data da ocorrência")
    dia_inteiro, inicio, fim = _horarios(dados)
    observacao = _texto(dados.get("observacao"), "observação administrativa", 1000)
    setor = _setor(setor)
    classificacao = dados.get("classificacao")
    if tipo == "falta":
        if classificacao is None:
            classificacao = "pendente"
        classificacao = _escolha(classificacao, CLASSIFICACOES, "Classificação")
    elif classificacao is not None:
        raise ValueError("A classificação se aplica somente às faltas.")

    _exigir_ativo(_bloquear_servidor(conn, id_agente))
    agora = _agora()
    if tipo == "falta" and (dia > agora.date()
            or (dia == agora.date() and inicio and _hora(inicio) > agora.time())):
        raise ValueError("Registre a falta após o início do período de ausência.")
    if tipo == "folga" and dia < agora.date() and not observacao:
        raise ValueError("Informe o motivo do lançamento retroativo na observação administrativa.")
    unidades = int(dia_inteiro) + 1 if tipo == "folga" else 0
    status = "agendada" if tipo == "folga" else "registrada"
    data_iso = dia.isoformat()
    _validar_dia(conn, id_agente, data_iso, dia_inteiro, inicio, fim, unidades)
    alocacoes = _alocar_creditos(conn, id_agente, data_iso, unidades) if unidades else []
    id_ocorrencia = db.insert_and_get_id(
        conn,
        """INSERT INTO pessoal_ocorrencias
           (id_agente, data, tipo, dia_inteiro, hora_inicio, hora_fim, unidades, status,
            classificacao, observacao, setor, criado_por, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id_agente, data_iso, tipo, int(dia_inteiro), inicio, fim, unidades, status,
         classificacao, observacao, setor, ator, _carimbo(agora)),
        "id_ocorrencia",
    )
    if alocacoes:
        conn.executemany(
            """INSERT INTO pessoal_folga_consumos (id_credito, id_ocorrencia, id_agente, unidades)
               VALUES (?, ?, ?, ?)""",
            [(id_credito, id_ocorrencia, id_agente, alocadas) for id_credito, alocadas in alocacoes],
        )
    return id_ocorrencia


def _registro_para_editar(conn, tabela, chave, identificador, rotulo):
    _iniciar_escrita(conn)
    sql = f"SELECT * FROM {tabela} WHERE {chave}=?"
    registro = conn.execute(sql, (identificador,)).fetchone()
    if not registro:
        raise NaoEncontrado(f"{rotulo} não existe.")
    _bloquear_servidor(conn, registro["id_agente"])
    if _postgresql(conn):
        # A leitura anterior só identifica o servidor. Releia o estado com o lock.
        registro = conn.execute(sql, (identificador,)).fetchone()
    return registro


def _periodo_encerrado(registro, agora):
    dia = _data(registro["data"], "Data da ocorrência")
    if dia != agora.date():
        return dia < agora.date()
    return not registro["dia_inteiro"] and _hora(registro["hora_fim"]) <= agora.time()


def confirmar_folga(conn, id_ocorrencia, ator):
    id_ocorrencia = _inteiro(id_ocorrencia, "Identificador da ocorrência")
    registro = _registro_para_editar(conn, "pessoal_ocorrencias", "id_ocorrencia", id_ocorrencia, "A ocorrência")
    if registro["tipo"] != "folga" or registro["status"] != "agendada":
        raise Conflito("Somente uma folga agendada pode ser confirmada.")
    agora = _agora()
    if not _periodo_encerrado(registro, agora):
        raise Conflito("Confirme a utilização após o fim do período da folga.")
    conn.execute(
        """UPDATE pessoal_ocorrencias SET status='utilizada', atualizado_por=?, atualizado_em=?
            WHERE id_ocorrencia=?""",
        (ator, _carimbo(agora), id_ocorrencia),
    )
    return id_ocorrencia


def cancelar_ocorrencia(conn, id_ocorrencia, motivo, ator):
    id_ocorrencia = _inteiro(id_ocorrencia, "Identificador da ocorrência")
    motivo = _texto(motivo, "o motivo do cancelamento", 500, obrigatorio=True)
    registro = _registro_para_editar(conn, "pessoal_ocorrencias", "id_ocorrencia", id_ocorrencia, "A ocorrência")
    if registro["status"] == "cancelada":
        raise Conflito("Essa ocorrência já foi cancelada.")
    conn.execute(
        """UPDATE pessoal_ocorrencias SET status='cancelada', cancelado_por=?, cancelado_em=?, motivo_cancelamento=?
            WHERE id_ocorrencia=?""",
        (ator, _carimbo(_agora()), motivo, id_ocorrencia),
    )
    return id_ocorrencia


def cancelar_credito(conn, id_credito, motivo, ator):
    id_credito = _inteiro(id_credito, "Identificador do crédito")
    motivo = _texto(motivo, "o motivo do cancelamento", 500, obrigatorio=True)
    registro = _registro_para_editar(conn, "pessoal_folga_creditos", "id_credito", id_credito, "O crédito")
    if registro["cancelado_em"]:
        raise Conflito("Esse crédito já foi cancelado.")
    tem_consumo = conn.execute(
        """SELECT 1 FROM pessoal_folga_consumos m
             JOIN pessoal_ocorrencias o ON o.id_ocorrencia=m.id_ocorrencia
            WHERE m.id_credito=? AND o.status <> 'cancelada' LIMIT 1""",
        (id_credito,),
    ).fetchone()
    if tem_consumo:
        raise Conflito("O crédito tem folga reservada ou utilizada. Revise as ocorrências vinculadas.")
    conn.execute(
        """UPDATE pessoal_folga_creditos SET cancelado_por=?, cancelado_em=?, motivo_cancelamento=?
            WHERE id_credito=?""",
        (ator, _carimbo(_agora()), motivo, id_credito),
    )
    return id_credito


def classificar_falta(conn, id_ocorrencia, classificacao, motivo, ator):
    id_ocorrencia = _inteiro(id_ocorrencia, "Identificador da ocorrência")
    classificacao = _escolha(classificacao, CLASSIFICACOES, "Classificação")
    motivo = _texto(motivo, "o motivo da classificação", 500, obrigatorio=True)
    registro = _registro_para_editar(conn, "pessoal_ocorrencias", "id_ocorrencia", id_ocorrencia, "A ocorrência")
    if registro["tipo"] != "falta" or registro["status"] != "registrada":
        raise Conflito("Somente uma falta ativa pode ser classificada.")
    if registro["classificacao"] == classificacao:
        raise Conflito("A falta já tem essa classificação.")
    conn.execute(
        """UPDATE pessoal_ocorrencias SET classificacao=?, motivo_classificacao=?, atualizado_por=?, atualizado_em=?
            WHERE id_ocorrencia=?""",
        (classificacao, motivo, ator, _carimbo(_agora()), id_ocorrencia),
    )
    return id_ocorrencia


_OCORRENCIAS_SQL = """
    SELECT o.*, COALESCE(NULLIF(TRIM(a.nome_completo), ''), a.nome) AS nome
      FROM pessoal_ocorrencias o
      JOIN agentes a ON a.id_agente=o.id_agente
"""


def _serializar_ocorrencia(registro, agora):
    item = db.serialize_row(registro)
    item["dia_inteiro"] = bool(item["dia_inteiro"])
    for campo in ("hora_inicio", "hora_fim"):
        if item[campo] is not None:
            item[campo] = item[campo][:5]
    if item["status"] == "agendada" and _periodo_encerrado(registro, agora):
        item["status"] = "aguardando_confirmacao"
    return item


def listar_ocorrencias(conn, inicio, fim, id_agente=None, tipo=None):
    """Lista ocorrências em intervalo de data local, incluindo cancelamentos."""
    inicio = _data(inicio, "Data inicial")
    fim = _data(fim, "Data final")
    if inicio >= fim:
        raise ValueError("A data final deve ser posterior à inicial.")
    filtros = ["o.data>=?", "o.data<?"]
    params = [inicio.isoformat(), fim.isoformat()]
    if id_agente is not None:
        filtros.append("o.id_agente=?")
        params.append(_inteiro(id_agente, "Servidor"))
    if tipo is not None:
        filtros.append("o.tipo=?")
        params.append(_escolha(tipo, TIPOS, "Categoria"))
    sql = _OCORRENCIAS_SQL + " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY o.data, o.dia_inteiro DESC, o.hora_inicio, o.id_ocorrencia"
    agora = _agora()
    return [_serializar_ocorrencia(row, agora) for row in conn.execute(sql, params).fetchall()]


def _creditos_por_servidor(conn, id_agente=None):
    filtro = "WHERE c.id_agente=?" if id_agente is not None else ""
    params = (id_agente,) if id_agente is not None else ()
    return conn.execute(
        f"""SELECT c.*,
                   COALESCE(m.reservado, 0) AS reservado,
                   COALESCE(m.utilizado, 0) AS utilizado
              FROM pessoal_folga_creditos c
         LEFT JOIN (
                SELECT m.id_credito,
                       SUM(CASE WHEN o.status='agendada' THEN m.unidades ELSE 0 END) AS reservado,
                       SUM(CASE WHEN o.status='utilizada' THEN m.unidades ELSE 0 END) AS utilizado
                  FROM pessoal_folga_consumos m
                  JOIN pessoal_ocorrencias o ON o.id_ocorrencia=m.id_ocorrencia
                 GROUP BY m.id_credito
              ) m ON m.id_credito=c.id_credito
                   {filtro}
          ORDER BY c.validade, c.data_aquisicao, c.id_credito""",
        params,
    ).fetchall()


def _serializar_credito(registro, hoje):
    credito = db.serialize_row(registro)
    credito.update(disponivel=0, expirado=0, status="cancelado")
    if not credito["cancelado_em"]:
        restante = credito["unidades"] - credito["reservado"] - credito["utilizado"]
        if restante <= 0:
            credito["status"] = "esgotado"
        elif credito["validade"] < hoje.isoformat():
            credito.update(expirado=restante, status="expirado")
        else:
            credito.update(disponivel=restante, status="ativo")
    return credito


def _saldo_inicial(servidor):
    return {
        "id_agente": servidor["id_agente"],
        "nome": servidor["nome"],
        "ativo": bool(servidor["ativo"]),
        "concedido": 0,
        "disponivel": 0,
        "reservado": 0,
        "utilizado": 0,
        "expirado": 0,
        "a_vencer": 0,
        "proximo_vencimento": None,
    }


def _somar_credito(saldo, credito, limite):
    if credito["status"] == "cancelado":
        return
    saldo["concedido"] += credito["unidades"]
    for campo in ("disponivel", "reservado", "utilizado", "expirado"):
        saldo[campo] += credito[campo]
    if credito["disponivel"]:
        prazo = credito["validade"]
        proximo = saldo["proximo_vencimento"]
        saldo["proximo_vencimento"] = min(proximo, prazo) if proximo else prazo
        if prazo <= limite:
            saldo["a_vencer"] += credito["disponivel"]


def _saldos(conn, hoje, id_agente=None):
    filtro = "WHERE id_agente=?" if id_agente is not None else ""
    params = (id_agente,) if id_agente is not None else ()
    servidores = conn.execute(
        f"""SELECT id_agente, ativo, COALESCE(NULLIF(TRIM(nome_completo), ''), nome) AS nome
              FROM agentes {filtro}
          ORDER BY ativo DESC, LOWER(COALESCE(NULLIF(TRIM(nome_completo), ''), nome)), id_agente""",
        params,
    ).fetchall()
    saldos = {row["id_agente"]: _saldo_inicial(row) for row in servidores}
    limite = (hoje + timedelta(days=30)).isoformat()
    creditos = []
    for row in _creditos_por_servidor(conn, id_agente):
        credito = _serializar_credito(row, hoje)
        saldo = saldos.get(credito["id_agente"])
        if saldo:
            _somar_credito(saldo, credito, limite)
            creditos.append(credito)
    return list(saldos.values()), creditos


def listar_saldos(conn, id_agente=None):
    if id_agente is not None:
        id_agente = _inteiro(id_agente, "Servidor")
    return _saldos(conn, _agora().date(), id_agente)[0]


def extrato(conn, id_agente):
    id_agente = _inteiro(id_agente, "Servidor")
    agora = _agora()
    saldos, creditos = _saldos(conn, agora.date(), id_agente)
    if not saldos:
        raise NaoEncontrado("Servidor não encontrado.")
    ocorrencias = conn.execute(
        _OCORRENCIAS_SQL + " WHERE o.id_agente=? ORDER BY o.data DESC, o.id_ocorrencia DESC",
        (id_agente,),
    ).fetchall()
    consumos = conn.execute(
        """SELECT m.id_credito, m.id_ocorrencia, m.unidades,
                  CASE WHEN o.status='agendada' THEN 'reservado'
                       WHEN o.status='utilizada' THEN 'utilizado' ELSE 'cancelado' END AS status
             FROM pessoal_folga_consumos m
             JOIN pessoal_folga_creditos c ON c.id_credito=m.id_credito
             JOIN pessoal_ocorrencias o ON o.id_ocorrencia=m.id_ocorrencia
            WHERE m.id_agente=?
         ORDER BY o.data DESC, m.id_ocorrencia DESC, c.validade, c.data_aquisicao, c.id_credito""",
        (id_agente,),
    ).fetchall()
    return {
        "saldo": saldos[0],
        "creditos": creditos,
        "ocorrencias": [_serializar_ocorrencia(row, agora) for row in ocorrencias],
        "consumos": [dict(row) for row in consumos],
    }
