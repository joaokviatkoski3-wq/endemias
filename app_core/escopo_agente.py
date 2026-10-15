"""Escopo de dados do nivel de acesso restrito ``usuario``.

O nivel ``usuario`` (rotulo "Usuario" na interface) enxerga as mesmas paginas
de consulta do ``visualizador``, porem com a **identidade dos demais agentes
ocultada**: em qualquer campo que atribua a producao a servidores (colunas
"Agentes", "laboratorista", rankings, agenda, relatorios), apenas o proprio
agente vinculado a conta permanece identificado; os demais viram "—" e as
quebras nominais por colega (``por_agente``/``por_laboratorista``) sao
removidas por inteiro.

Enderecos, nomes de moradores e demais conteudos operacionais seguem visiveis.
A dimensao ACS (``visita_acs``/``acs_catalogo``) e tratada como separada de
"agentes de endemias" e NAO e redigida aqui.

A resolucao da identidade e ESTRITA: nunca ha fallback por nome. Sem vinculo
``usuarios.id_agente`` -> ``agentes``, o conjunto de nomes proprios fica vazio
e, portanto, TODOS os nomes de agentes sao redigidos (fail-closed).
"""

import re
import unicodedata

from app_core import db as db_core

NIVEL_RESTRITO = "usuario"
MASCARA = "—"

# Campos que transportam identidade de agente/servidor nas respostas.
CAMPOS_AGENTE = {
    "agente",
    "agentes",
    "agentes_texto",
    "agentes_nomes",
    "laboratorista",
    "laboratorista_nome",
    "agente_nome",
    "nome_agente",
    "agente_exibicao",
}

# Quebras nominais: listas em que cada linha e um colega. Sao removidas por
# inteiro (nao faz sentido manter uma linha anonima de produtividade alheia).
CHAVES_QUEBRA_NOMINAL = {"por_agente", "por_laboratorista"}

_SEPARADORES = re.compile(r"\s*[,;/]\s*")


def nivel_restrito(usuario):
    """True quando a conta usa o nivel de acesso restrito 'usuario'."""
    return bool(usuario) and (usuario or {}).get("nivel") == NIVEL_RESTRITO


def _chave(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t.casefold())


def agente_proprio(target, usuario):
    """Resolve o agente vinculado a conta, de forma estrita.

    Retorna um dict com ``id_agente``, ``nome``, ``nome_completo`` e ``chaves``
    (conjunto de nomes normalizados que identificam o proprio usuario), ou
    ``None`` quando nao ha vinculo valido/ativo.
    """
    if not usuario:
        return None
    id_agente = usuario.get("id_agente")
    if id_agente in (None, ""):
        return None
    try:
        id_agente = int(id_agente)
    except (TypeError, ValueError):
        return None
    if id_agente <= 0:
        return None

    conn = db_core.connect(target)
    try:
        row = conn.execute(
            """SELECT id_agente,
                      nome,
                      COALESCE(NULLIF(nome_completo,''), nome) AS nome_completo
                 FROM agentes
                WHERE id_agente=? AND COALESCE(ativo,1)=1""",
            (id_agente,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    nome = row["nome"]
    nome_completo = row["nome_completo"]
    chaves = {_chave(nome), _chave(nome_completo)}
    chaves.discard("")
    return {
        "id_agente": id_agente,
        "nome": nome,
        "nome_completo": nome_completo,
        "chaves": chaves,
    }


def _redigir_nomes(texto, chaves):
    texto = str(texto)
    if not texto.strip():
        return texto
    if _SEPARADORES.search(texto):
        partes = [p for p in _SEPARADORES.split(texto) if p.strip()]
        return ", ".join(p if _chave(p) in chaves else MASCARA for p in partes)
    return texto if _chave(texto) in chaves else MASCARA


def _redigir_campo_agente(valor, chaves):
    if valor is None:
        return None
    if isinstance(valor, dict):
        return redigir_agentes(valor, chaves)
    if isinstance(valor, (list, tuple)):
        return [
            _redigir_nomes(x, chaves) if isinstance(x, str) else redigir_agentes(x, chaves)
            for x in valor
        ]
    if isinstance(valor, str):
        return _redigir_nomes(valor, chaves)
    return valor


def filtrar_agentes(valores, chaves):
    """Restringe uma lista de opcoes de filtro ao proprio agente.

    ``valores`` pode ser uma lista de strings (nomes) ou de dicts com a chave
    ``nome``. Sem vinculo (``chaves`` vazio), retorna lista vazia: o usuario
    restrito nao ve os demais agentes nem nos seletores de filtro.
    """
    if not chaves:
        return []
    resultado = []
    for item in valores:
        nome = item.get("nome") if isinstance(item, dict) else item
        if nome is not None and _chave(nome) in chaves:
            resultado.append(item)
    return resultado


def redigir_agentes(dado, chaves):
    """Percorre dicts/listas e redige a identidade dos demais agentes.

    - Chaves em ``CAMPOS_AGENTE`` tem os nomes que nao pertencem ao proprio
      usuario substituidos por ``MASCARA``.
    - Chaves em ``CHAVES_QUEBRA_NOMINAL`` sao esvaziadas por inteiro.
    - Demais estruturas sao percorridas recursivamente, sem alteracao.
    """
    if isinstance(dado, dict):
        resultado = {}
        for chave, valor in dado.items():
            if chave in CHAVES_QUEBRA_NOMINAL:
                resultado[chave] = []
            elif chave in CAMPOS_AGENTE:
                resultado[chave] = _redigir_campo_agente(valor, chaves)
            else:
                resultado[chave] = redigir_agentes(valor, chaves)
        return resultado
    if isinstance(dado, list):
        return [redigir_agentes(item, chaves) for item in dado]
    return dado
