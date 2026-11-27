"""Espelho local das abas anuais do Google Sheets usado pela vigilância."""

from collections import defaultdict
from datetime import datetime, timezone
import base64
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
from threading import Event, Thread
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA
from Cryptodome.Signature import pkcs1_15

from app_core import db, registro_geografico as rg
from app_core.geovsatt_enderecos import ensure_schema, ponto


ESCOPO = "https://www.googleapis.com/auth/spreadsheets.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ANO = re.compile(r"20[0-9]{2}")
COLUNAS = ("chave", "ano", "notificacao", "data_notificacao", "data_bloqueio", "origem",
           "unidade", "resultado", "endereco", "latitude", "longitude", "conflito")


def configurado(config):
    return bool(config.get("GEOVSATT_DENGUE_PLANILHA") and config.get("GEOVSATT_DENGUE_CREDENCIAL"))


def iniciar(config):
    """Executa uma leitura inicial e novas consultas a cada 15 minutos no Waitress."""
    if not configurado(config):
        return None
    parar = Event()
    target = db.configured_target(config)

    def rotina():
        while not parar.is_set():
            try:
                sincronizar(target, config)
            except ValueError as exc:
                logging.warning("GeoVSATT dengue: %s", exc)
            except Exception as exc:
                logging.error("GeoVSATT dengue: falha no espelho local (%s)", type(exc).__name__)
            parar.wait(15 * 60)

    Thread(target=rotina, name="geovsatt-dengue", daemon=True).start()
    return parar


def _b64(payload):
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _ler_json(req):
    try:
        with urlopen(req, timeout=25) as response:
            conteudo = response.read(12 * 1024**2 + 1)
        if len(conteudo) > 12 * 1024**2:
            raise ValueError("Resposta do Google Sheets acima do tamanho esperado.")
        dados = json.loads(conteudo)
        if not isinstance(dados, dict):
            raise ValueError("O Google Sheets retornou um formato inesperado.")
        return dados
    except HTTPError as exc:
        raise ValueError(f"O Google retornou HTTP {exc.code}. Confira o acesso de leitura da conta de serviço.") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError("Não foi possível ler a resposta do Google Sheets.") from None


def _token(credencial):
    try:
        conta = json.loads(Path(credencial).read_text(encoding="utf-8-sig"))
        chave = RSA.import_key(conta["private_key"])
        email = conta["client_email"]
        if conta["type"] != "service_account" or not isinstance(email, str):
            raise ValueError
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("A credencial privada da conta de serviço do Google está inválida.") from None
    agora = int(time.time())
    claims = {"iss": email, "scope": ESCOPO, "aud": TOKEN_URL, "iat": agora, "exp": agora + 3600}
    payload = _b64(b'{"alg":"RS256","typ":"JWT"}') + "." + _b64(json.dumps(claims).encode())
    assertion = payload + "." + _b64(pkcs1_15.new(chave).sign(SHA256.new(payload.encode())))
    resposta = _ler_json(Request(TOKEN_URL, data=urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion
    }).encode("ascii"), method="POST"))
    if not resposta.get("access_token"):
        raise ValueError("O Google não concedeu o acesso de leitura à planilha.")
    return resposta["access_token"]


def _abas(config):
    planilha = config["GEOVSATT_DENGUE_PLANILHA"].strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", planilha) or not configurado(config):
        raise ValueError("Configure o ID da planilha anual e o arquivo privado da conta de serviço.")
    token = _token(config["GEOVSATT_DENGUE_CREDENCIAL"])
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + planilha
    info = _ler_json(Request(url + "?" + urlencode({"fields": "sheets(properties(title))"}),
                             headers=headers))
    anos = sorted(s["properties"]["title"] for s in info.get("sheets", [])
                  if ANO.fullmatch(s["properties"]["title"]))
    if not {"2025", "2026"}.issubset(anos):
        raise ValueError("As abas gerais 2025 e 2026 devem estar disponíveis.")
    params = [("valueRenderOption", "FORMATTED_VALUE")]
    params.extend(("ranges", f"'{ano}'!A1:AZ") for ano in anos)
    dados = _ler_json(Request(url + "/values:batchGet?" + urlencode(params), headers=headers))
    faixas = dados.get("valueRanges", [])
    if len(faixas) != len(anos):
        raise ValueError("O Google retornou uma leitura incompleta das abas gerais.")
    return {ano: faixa.get("values", []) for ano, faixa in zip(anos, faixas)}


def _data(texto):
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def _notificacao(texto):
    texto = re.sub(r"[.,]0+$", "", texto)
    if re.fullmatch(r"[0-9]{1,30}", texto):
        return texto.lstrip("0") or None
    return None


def ler_registros(abas):
    grupos = defaultdict(list)
    for ano, linhas in abas.items():
        if not linhas or not ANO.fullmatch(ano):
            raise ValueError("A leitura de uma aba anual está incompleta.")
        campos = {rg._norm(campo): i for i, campo in enumerate(linhas[0]) if str(campo).strip()}
        numero = next((campo for campo in campos if re.fullmatch(r"n[oaº°.]?\s*(?:da )?notificacao", campo)), "")
        if not all(k in campos for k in ("data notificacao", "endereco", "resultado", numero)):
            raise ValueError(f"Cabeçalho da aba {ano} fora do formato esperado.")
        for linha in linhas[1:]:
            def campo(nome):
                indice = campos.get(nome, -1)
                valor = str(linha[indice]).strip() if 0 <= indice < len(linha) else ""
                return "" if valor in {"#REF!", "#N/A", "#VALUE!", "#ERROR!"} else valor

            nome, raw_id = campo("nome"), campo(numero)
            if not nome and not raw_id:
                continue
            notificacao = _notificacao(raw_id)
            endereco = campo("endereco")
            data = _data(campo("data notificacao"))
            # A latitude copiada de um par pode vir com a vírgula separadora.
            coords = ponto(campo("latitude").removesuffix(","), campo("longitude").removesuffix(","))
            preliminar = notificacao is None or data is None or data[:4] != ano
            chave = f"{ano}:{notificacao}" if notificacao else (
                f"{ano}:sem-numero:{sha256(repr((nome, endereco, data)).encode()).hexdigest()[:20]}")
            grupos[chave].append({
                "chave": chave, "ano": int(ano), "notificacao": notificacao or "",
                "data_notificacao": data, "data_bloqueio": _data(campo("data bloqueio")),
                "origem": campo("unidade notificadora"), "unidade": campo("unidade de referencia"),
                "resultado": campo("resultado"), "endereco": endereco, "coordenadas": coords,
                "nome": nome, "conflito": preliminar,
            })
    registros = []
    for linhas in grupos.values():
        mesclado = linhas[0].copy()
        conflito = any(linha["conflito"] for linha in linhas)
        for campo in ("data_notificacao", "data_bloqueio", "unidade", "origem", "resultado",
                      "endereco", "coordenadas", "nome"):
            valores = {rg._norm(valor) if isinstance(valor, str) else valor: valor
                       for linha in linhas if (valor := linha[campo])}
            if len(valores) > 1:
                conflito = True
                mesclado[campo] = None
            elif valores:
                mesclado[campo] = next(iter(valores.values()))
        lat, lon = mesclado.pop("coordenadas") or (None, None)
        mesclado.pop("nome")
        registros.append(mesclado | {"conflito": int(conflito), "latitude": lat, "longitude": lon})
    return registros


def sincronizar(target, config, *, carregar=_abas):
    iniciado = datetime.now(timezone.utc).isoformat()
    registros = ler_registros(carregar(config))
    anos = {row["ano"] for row in registros}
    if not registros or not {2025, 2026}.issubset(anos):
        raise ValueError("Uma aba geral ficou sem registros. O último espelho foi preservado.")
    conn = db.connect(target)
    try:
        if db.is_sqlite(target):
            conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        if not db.is_sqlite(target):
            conn.execute("LOCK TABLE geovsatt_dengue_sync IN EXCLUSIVE MODE")
        ultimo = conn.execute("SELECT * FROM geovsatt_dengue_sync WHERE id = 1").fetchone()
        if ultimo and ultimo["sincronizado_em"] >= iniciado:
            return {"total": ultimo["total"], "sincronizado_em": ultimo["sincronizado_em"]}
        ativos = {row["ano"] for row in conn.execute("SELECT DISTINCT ano FROM geovsatt_dengue WHERE ativo=1")}
        if ativos - anos:
            raise ValueError("Uma aba anual publicada está ausente. O último espelho foi preservado.")
        conn.execute("UPDATE geovsatt_dengue SET ativo=0 WHERE ativo=1")
        update = ", ".join(f"{coluna}=excluded.{coluna}" for coluna in COLUNAS if coluna != "chave")
        sql = f"""INSERT INTO geovsatt_dengue ({', '.join(COLUNAS)}, ativo)
                   VALUES ({', '.join('?' for _ in COLUNAS)}, 1)
                   ON CONFLICT (chave) DO UPDATE SET {update}, ativo=1"""
        conn.executemany(sql, [tuple(row[coluna] for coluna in COLUNAS) for row in registros])
        agora = datetime.now(timezone.utc).isoformat()
        conn.execute("""INSERT INTO geovsatt_dengue_sync (id, sincronizado_em,total) VALUES (1,?,?)
                        ON CONFLICT (id) DO UPDATE SET sincronizado_em=excluded.sincronizado_em,total=excluded.total""",
                     (agora, len(registros)))
        conn.commit()
        return {"total": len(registros), "sincronizado_em": agora}
    finally:
        conn.close()


def estado(target):
    conn = db.connect(target)
    try:
        if not db.table_exists(conn, "geovsatt_dengue_sync"):
            return None
        row = conn.execute("SELECT sincronizado_em,total FROM geovsatt_dengue_sync WHERE id=1").fetchone()
        return db.serialize_row(row) if row else None
    finally:
        conn.close()


def casos(target, chave=None):
    conn = db.connect(target)
    try:
        if not db.table_exists(conn, "geovsatt_dengue"):
            return []
        condicao, parametros = (" AND chave=?", (chave,)) if chave else ("", ())
        return [db.serialize_row(r) for r in conn.execute(
            f"SELECT * FROM geovsatt_dengue WHERE ativo=1{condicao} ORDER BY data_notificacao DESC, notificacao",
            parametros)]
    finally:
        conn.close()


def situacao(resultado):
    valor = rg._norm(resultado)
    if re.match(r"^(?:nao reagente|negativ|descartad|nao detectad)", valor):
        # Resultado laboratorial e classificação do caso são registrados
        # juntos na planilha. Preserve a descrição original no painel.
        return "Negativo ou descartado"
    if re.match(r"^(?:positiv|reagente|confirmad|detectad)", valor):
        return "Positivo ou confirmado"
    if not valor or re.match(r"^(?:suspeit|aguard|pend|inconcl|em investig)", valor):
        return "Suspeito ou em investigação"
    return "Resultado a revisar"
