from datetime import datetime
import hashlib
import re
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


EXTENSOES_PERMITIDAS = {
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp",
}
ARQUIVOS_IGNORADOS = {
    "desktop.ini", "thumbs.db", "folder.jpg", "folder.jpeg", "folder.png", "icone.docx",
}
PASTAS_AGRUPADORAS = {"outros", "diversos", "avulsos"}
MAX_ARQUIVOS = 500
MAX_XML_DOCX = 8 * 1024 * 1024
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def normalizar(value):
    texto = unicodedata.normalize("NFD", str(value or ""))
    return "".join(
        char for char in texto if unicodedata.category(char) != "Mn"
    ).casefold()


def _texto_docx(path):
    try:
        with zipfile.ZipFile(path) as arquivo:
            info = arquivo.getinfo("word/document.xml")
            if info.file_size > MAX_XML_DOCX:
                return ""
            raiz = ET.fromstring(arquivo.read(info))
    except (KeyError, OSError, ET.ParseError, zipfile.BadZipFile):
        return ""
    textos = []
    for item in raiz.iter():
        if item.tag.endswith("}t") and item.text:
            textos.append(item.text)
        elif item.tag.endswith("}tab"):
            textos.append(" ")
        elif item.tag.endswith("}br"):
            textos.append("\n")
    return " ".join(" ".join(textos).split())


def _hash_arquivo(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while bloco := stream.read(1024 * 1024):
            digest.update(bloco)
    return digest.hexdigest()


def _data_valida(dia, mes, ano):
    try:
        return datetime(int(ano), int(mes), int(dia)).date().isoformat()
    except (TypeError, ValueError):
        return None


def _datas_texto(texto):
    encontradas = []
    texto_normalizado = normalizar(texto)
    for match in re.finditer(
        r"(?<!\d)(\d{1,2})[._/\-](\d{1,2})[._/\-](20\d{2})(?!\d)",
        texto_normalizado,
    ):
        data = _data_valida(*match.groups())
        if data:
            encontradas.append((match.start(), data, None))
    for match in re.finditer(
        r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)",
        texto_normalizado,
    ):
        data = _data_valida(*match.groups())
        if data:
            encontradas.append((match.start(), data, None))
    meses = "|".join(MESES)
    for match in re.finditer(
        rf"(?<!\d)(\d{{1,2}})(?:\s*(?:a|e|-)\s*(\d{{1,2}}))?"
        rf"\s+de\s+({meses})\s+de\s+(20\d{{2}})",
        texto_normalizado,
    ):
        dia_inicio, dia_fim, mes_nome, ano = match.groups()
        inicio = _data_valida(dia_inicio, MESES[mes_nome], ano)
        fim = _data_valida(dia_fim, MESES[mes_nome], ano) if dia_fim else None
        if inicio:
            encontradas.append((match.start(), inicio, fim))
    for match in re.finditer(
        rf"aos?\s+(\d{{1,2}})\s+dias?\s+do\s+mes\s+de\s+({meses})"
        rf"\s+de\s+(20\d{{2}})",
        texto_normalizado,
    ):
        dia, mes_nome, ano = match.groups()
        inicio = _data_valida(dia, MESES[mes_nome], ano)
        if inicio:
            encontradas.append((match.start(), inicio, None))
    return sorted(encontradas, key=lambda item: item[0])


def _sugerir_datas(rotulo, texto):
    fontes = _datas_texto(rotulo)
    datas_texto = _datas_texto(texto)
    datas = fontes or datas_texto
    if not datas:
        return None, None, []
    inicio, fim = datas[0][1], datas[0][2]
    if fontes and not fim:
        fim = next(
            (
                data_fim for _, data_inicio, data_fim in datas_texto
                if data_inicio == inicio and data_fim
            ),
            None,
        )
    unicas = []
    for _, data_inicio, data_fim in _datas_texto(f"{rotulo} {texto}"):
        for data in (data_inicio, data_fim):
            if data and data not in unicas:
                unicas.append(data)
    return inicio, fim, unicas[:12]


def _limpar_rotulo(value):
    texto = Path(str(value or "")).name
    texto = re.sub(r"[_]+", " ", texto)
    texto = re.sub(r"(?<!\d)\d{1,2}[._/\-]\d{1,2}[._/\-]20\d{2}(?!\d)", " ", texto)
    texto = re.sub(r"(?<!\d)\d{1,2}\s+\d{1,2}\s+20\d{2}(?!\d)", " ", texto)
    texto = re.sub(r"(?<!\d)\d{8}(?!\d)", " ", texto)
    texto = re.sub(r"(?<!\d)20\d{2}(?!\d)", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" -_.")
    return texto


def _sugerir_tipo(rotulo, texto):
    titulo = normalizar(texto[:700])
    origem = normalizar(rotulo)
    if "ata da reuniao" in titulo or "planejamento da acao" in titulo:
        return "reuniao"
    if any(
        termo in titulo
        for termo in (
            "relatorio de vistoria",
            "relatorio de visita domiciliar",
            "foi realizado atendimento",
            "vistoria entomologica",
        )
    ):
        return "vistoria"
    if "mutirao" in origem or "mutirao" in titulo or "limpeza" in titulo:
        return "limpeza"
    if any(termo in titulo for termo in ("vistoria", "visita", "atendimento")):
        return "vistoria"
    if "reuniao" in origem or "reuniao" in titulo:
        return "reuniao"
    return "outro"


def _sugerir_localidades(rotulo, texto, localidades):
    def localizar(alvo):
        alvo = alvo.replace("_", " ")
        encontradas = []
        for localidade in localidades or ():
            termo = re.escape(normalizar(localidade))
            if termo and re.search(rf"(?<!\w){termo}(?!\w)", alvo):
                encontradas.append(str(localidade))
        return encontradas

    no_rotulo = localizar(normalizar(rotulo))
    return no_rotulo or localizar(normalizar(texto[:1200]))


def _sugerir_periodo(texto):
    horarios = re.findall(r"(?<!\d)([012]?\d)[:h](\d{2})(?!\d)", normalizar(texto[:3000]))
    if not horarios:
        return "nao_informado"
    hora = int(horarios[0][0])
    return "manha" if hora < 12 else "tarde"


def _grupo_sensivel(rotulo, texto):
    origem = normalizar(rotulo)
    conteudo = normalizar(texto[:6000])
    return bool(
        re.search(r"(?<!\w)(sr|sra|senhor|senhora)[.]?(?!\w)", origem)
        or any(
            termo in conteudo
            for termo in (
                "cpf:",
                "paciente",
                "ficha de notificacao",
                "entrada forcada",
                "situacao de violencia",
                "vulnerabilidade",
            )
        )
    )


def _titulo_e_caso(rotulo, tipo, sensivel):
    limpo = _limpar_rotulo(rotulo)
    caso = limpo if sensivel else None
    temas = {
        "limpeza": "Ação de limpeza e redução de riscos",
        "vistoria": "Vistoria e acompanhamento técnico",
        "reuniao": "Planejamento de ação intersetorial",
        "outro": "Registro histórico do setor",
    }
    return limpo or temas[tipo], caso, temas[tipo]


def _chave_grupo(root, path):
    partes = path.relative_to(root).parts
    if len(partes) == 1:
        return path.stem
    if normalizar(partes[0]) in PASTAS_AGRUPADORAS:
        return str(Path(partes[0]) / path.stem)
    return partes[0]


def _arquivos_validos(root):
    arquivos = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        nome = path.name.casefold()
        if (
            nome.startswith("~$")
            or nome in ARQUIVOS_IGNORADOS
            or path.suffix.casefold() not in EXTENSOES_PERMITIDAS
        ):
            continue
        arquivos.append(path)
        if len(arquivos) > MAX_ARQUIVOS:
            raise ValueError(
                f"A pasta possui mais de {MAX_ARQUIVOS} arquivos importáveis."
            )
    return sorted(arquivos, key=lambda item: normalizar(str(item.relative_to(root))))


def escanear(diretorio, localidades=()):
    diretorio_texto = str(diretorio or "").strip()
    if not diretorio_texto:
        raise ValueError("Informe a pasta do acervo histórico.")
    root = Path(diretorio_texto).expanduser()
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("A pasta informada não está disponível.") from exc
    if not root.is_dir():
        raise ValueError("O caminho informado não é uma pasta.")

    agrupados = {}
    for path in _arquivos_validos(root):
        agrupados.setdefault(_chave_grupo(root, path), []).append(path)

    grupos = []
    total_bytes = 0
    for chave, paths in agrupados.items():
        textos = [_texto_docx(path) for path in paths if path.suffix.casefold() == ".docx"]
        texto = " ".join(item for item in textos if item)
        rotulo_datas = " ".join(
            [chave, *(str(path.relative_to(root)) for path in paths)]
        )
        data, data_fim, datas_encontradas = _sugerir_datas(rotulo_datas, texto)
        tipo = _sugerir_tipo(rotulo_datas, texto)
        localizacoes = _sugerir_localidades(rotulo_datas, texto, localidades)
        sensivel = _grupo_sensivel(rotulo_datas, texto)
        titulo, caso, tema = _titulo_e_caso(chave, tipo, sensivel)
        arquivos = []
        fingerprint = hashlib.sha256()
        for path in paths:
            stat = path.stat()
            rel = str(path.relative_to(root)).replace("\\", "/")
            conteudo_hash = _hash_arquivo(path)
            fingerprint.update(rel.encode("utf-8", "surrogatepass"))
            fingerprint.update(conteudo_hash.encode("ascii"))
            total_bytes += stat.st_size
            arquivos.append({
                "nome": path.name,
                "caminho_rel": rel,
                "extensao": path.suffix.casefold(),
                "tamanho": stat.st_size,
                "alterado_em": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            })
        avisos = []
        if not data:
            avisos.append("Data não identificada automaticamente.")
        if len(localizacoes) > 1:
            avisos.append("Mais de uma localidade foi identificada.")
        if not texto and any(path.suffix.casefold() == ".docx" for path in paths):
            avisos.append("Um documento não possui texto extraível.")
        id_grupo = hashlib.sha256(chave.encode("utf-8", "surrogatepass")).hexdigest()[:20]
        grupos.append({
            "id_grupo": id_grupo,
            "chave": chave,
            "titulo": titulo,
            "fingerprint": fingerprint.hexdigest(),
            "arquivos": arquivos,
            "total_arquivos": len(arquivos),
            "total_bytes": sum(item["tamanho"] for item in arquivos),
            "datas_encontradas": datas_encontradas,
            "localidades_encontradas": localizacoes,
            "anexos_restritos_sugeridos": sensivel,
            "avisos": avisos,
            "sugestao": {
                "tipo": tipo,
                "situacao": "realizada",
                "data": data,
                "data_fim": data_fim,
                "periodo": _sugerir_periodo(texto),
                "caso": caso,
                "localidade": localizacoes[0] if len(localizacoes) == 1 else None,
                "local": None if sensivel else titulo,
                "endereco": None,
                "tema": tema,
                "contexto": "Registro localizado no acervo histórico do setor.",
                "resultados": None,
                "parceiros": None,
                "observacoes": "Dados sugeridos automaticamente; documento original preservado em anexo.",
                "agentes": [],
            },
        })
    grupos.sort(key=lambda item: (
        item["sugestao"]["data"] or "9999-12-31",
        normalizar(item["titulo"]),
    ))
    return {
        "diretorio": str(root),
        "grupos": grupos,
        "total_grupos": len(grupos),
        "total_arquivos": sum(item["total_arquivos"] for item in grupos),
        "total_bytes": total_bytes,
    }


def localizar_grupo(diretorio, id_grupo, localidades=()):
    inventario = escanear(diretorio, localidades)
    return next(
        (item for item in inventario["grupos"] if item["id_grupo"] == id_grupo),
        None,
    )


def caminho_origem(diretorio, caminho_rel):
    root = Path(diretorio).resolve(strict=True)
    path = (root / caminho_rel).resolve(strict=True)
    if root not in path.parents or not path.is_file():
        raise ValueError("Arquivo histórico fora da pasta autorizada.")
    return path
