"""Listas RG por localidade/quarteirão e leitura retrocompatível do XLSForm."""

import base64
import binascii
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app_core import db, liraa, normalizadores, registro_geografico as rg


LISTA = "endemias_logradouros_rg"
PREFIXO = "lg1_"


def _contexto(localidade, quarteirao):
    loc = rg._norm(normalizadores.normalizar_localidade(str(localidade)))
    q = format(Decimal(str(quarteirao).replace(",", ".")).normalize(), "f")
    return hashlib.sha256(f"{loc}:{q}".encode()).hexdigest()[:16]


def codigo(localidade, quarteirao, nome):
    valor = base64.urlsafe_b64encode(nome.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{PREFIXO}{_contexto(localidade, quarteirao)}_{valor}"


def nome_resposta(valor, outro, localidade, quarteirao):
    """Decodifica a escolha mantendo o nome do snapshot mesmo se o RG mudar."""
    valor = str(valor or "").strip()
    if valor == "outro":
        nome = str(outro or "").strip()
        if not nome:
            raise ValueError("Informe o nome do logradouro ao escolher Outro.")
        return nome
    if not valor.startswith(PREFIXO):
        return valor  # Formulários antigos continuam enviando texto livre.
    if len(valor) > 2048 or not re.fullmatch(r"lg1_[0-9a-f]{16}_[A-Za-z0-9_-]+", valor):
        raise ValueError("Escolha de logradouro inválida.")
    _, contexto, texto = valor.split("_", 2)
    if contexto != _contexto(localidade, quarteirao):
        raise ValueError("O logradouro escolhido não corresponde à localidade e ao quarteirão. Selecione novamente.")
    try:
        nome = base64.b64decode(texto + "=" * (-len(texto) % 4), altchars=b"-_", validate=True).decode("utf-8").strip()
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError("Escolha de logradouro inválida.") from None
    if not nome:
        raise ValueError("Logradouro selecionado está vazio.")
    return nome


def catalogo(target):
    """Somente nomes de ruas; não lê números, moradores ou dados de visitas."""
    conn = db.connect(target)
    try:
        rows = conn.execute("""SELECT l.nome AS localidade,i.quarteirao,TRIM(i.logradouro) AS logradouro,COUNT(*) AS usos
            FROM registro_geografico_imoveis i JOIN localidades l ON l.id_localidade=i.id_localidade
            WHERE TRIM(COALESCE(i.logradouro,''))<>''
            GROUP BY l.nome,i.quarteirao,TRIM(i.logradouro)""").fetchall()
    finally:
        conn.close()
    grupos = defaultdict(dict)
    for row in rows:
        nome = str(row["logradouro"]).strip()
        if not nome or rg._norm(nome) == "sem logradouro":
            continue
        if len(nome) > 300:
            raise liraa.LiraaError("Há logradouro no RG com mais de 300 caracteres. Revise o cadastro antes de gerar o formulário.")
        loc = normalizadores.normalizar_localidade(row["localidade"])
        try:
            q = format(Decimal(str(row["quarteirao"]).replace(",", ".")).normalize(), "f")
        except InvalidOperation:
            continue  # Quarteirões não numéricos não pertencem ao formulário LIRAa.
        chave = (loc, q)
        normalizado = rg._norm(nome)
        anterior = grupos[chave].get(normalizado)
        # Variações de caixa/acentos: usa a grafia mais frequente do próprio RG,
        # com desempate estável. Não edita nem renomeia o cadastro de origem.
        candidato = (int(row["usos"]), nome)
        if anterior is None or (-candidato[0], candidato[1]) < (-anterior[0], anterior[1]):
            grupos[chave][normalizado] = candidato
    return {key: sorted((nome for _, nome in rows.values()), key=lambda n: (rg._norm(n), n)) for key, rows in grupos.items()}


def aplicar(workbook, target):
    """Modifica somente Logradouro, seu complemento, a nova lista e a versão."""
    # Importação tardia: o importador também utiliza nome_resposta deste módulo.
    from app_core.liraa_kobo import _localidade

    survey, choices = workbook["survey"], workbook["choices"]
    sh = {c.value: c.column for c in survey[1] if c.value}
    ch = {c.value: c.column for c in choices[1] if c.value}
    for name in ("choice_filter", "relevant", "constraint", "constraint_message"):
        if name not in sh:
            sh[name] = survey.max_column + 1
            survey.cell(1, sh[name], name)
    if "quarteirao_rg" not in ch:
        ch["quarteirao_rg"] = choices.max_column + 1
        choices.cell(1, ch["quarteirao_rg"], "quarteirao_rg")
    names = {row[sh["name"] - 1].value: row[0].row for row in survey.iter_rows(min_row=2) if row[sh["name"] - 1].value}
    for name in ("Logradouro", "Localidade", "Quarteir_o"):
        if name not in names:
            raise liraa.LiraaError(f"Campo {name} não encontrado no formulário.")
    qlist = survey.cell(names["Quarteir_o"], sh["type"]).value.split()[-1]
    valores = list(choices.values)
    choice_rows = [dict(zip(valores[0], row)) for row in valores[1:]]
    ruas = catalogo(target)
    novas, sem_ruas, total_quarteiroes = [], 0, 0
    for row in choice_rows:
        if row.get("list_name") != qlist or row.get("name") == "outros":
            continue
        total_quarteiroes += 1
        loc_codigo = row["localidade"]
        # Os aliases técnicos do formulário são os mesmos usados no importador.
        loc = _localidade(loc_codigo)
        q = format(Decimal(str(row["name"])).normalize(), "f")
        nomes = ruas.get((loc, q), [])
        sem_ruas += not nomes
        novas.extend({"list_name": LISTA, "name": codigo(loc, q, nome), "label": nome,
                      "localidade": loc_codigo, "quarteirao_rg": q} for nome in nomes)
    for index in range(choices.max_row, 1, -1):
        if choices.cell(index, ch["list_name"]).value == LISTA:
            choices.delete_rows(index)
    novas.append({"list_name": LISTA, "name": "outro", "label": "Outro — digitar"})
    for row in novas:
        choices.append([row.get(choices.cell(1, col).value) for col in range(1, choices.max_column + 1)])
    qexpr = "${Quarteir_o}"
    relevante = "${Quarteir_o} != ''"
    if "Quarteir_o_outros" in names:
        qexpr = "if(${Quarteir_o} = 'outros', ${Quarteir_o_outros}, ${Quarteir_o})"
        relevante += " and (${Quarteir_o} != 'outros' or ${Quarteir_o_outros} != '')"
    updates = {"type": f"select_one {LISTA}", "required": "true", "appearance": "minimal", "default": "",
               "hint": "Escolha a rua cadastrada no RG ou Outro — digitar.", "relevant": relevante,
               "choice_filter": f"(localidade=${{Localidade}} and quarteirao_rg=string(number({qexpr}))) or name='outro'"}
    for key, value in updates.items():
        if key not in sh:
            sh[key] = survey.max_column + 1
            survey.cell(1, sh[key], key)
        survey.cell(names["Logradouro"], sh[key], value)
    if "Logradouro_outro" in names:
        survey.delete_rows(names["Logradouro_outro"])
    index = names["Logradouro"] + 1
    survey.insert_rows(index)
    novo = {"type": "text", "name": "Logradouro_outro", "label": "Nome do outro logradouro", "required": "true",
            "relevant": "${Logradouro} = 'outro'", "constraint": "string-length(normalize-space(.)) > 0 and string-length(.) <= 300",
            "constraint_message": "Digite o nome da rua, com até 300 caracteres."}
    for key, value in novo.items():
        survey.cell(index, sh[key], value)
    settings = workbook["settings"]
    head = {c.value: c.column for c in settings[1] if c.value}
    if "version" not in head:
        head["version"] = settings.max_column + 1
        settings.cell(1, head["version"], "version")
    settings.cell(2, head["version"], datetime.now().strftime("%Y%m%d%H%M%S"))
    return {"quarteiroes": total_quarteiroes, "sem_logradouros": sem_ruas, "opcoes_rg": len(novas) - 1}
