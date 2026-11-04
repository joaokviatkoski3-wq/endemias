"""Politica comum de autorizacao: gestao operacional e administracao tecnica."""

LEVEL_ORDER = {"visualizador": 1, "usuario": 1, "operador": 2, "admin": 3, "superadmin": 4}
CAPABILITIES = {
    "gestao": frozenset({"admin", "superadmin"}),
    "tecnica": frozenset({"superadmin"}),
}


def tem_nivel(usuario, minimo):
    return bool(usuario) and minimo in LEVEL_ORDER and LEVEL_ORDER.get(usuario.get("nivel"), 0) >= LEVEL_ORDER[minimo]


def permite(usuario, capacidade):
    return bool(usuario) and usuario.get("nivel") in CAPABILITIES.get(capacidade, ())


def gerencia(usuario):
    return permite(usuario, "gestao")


def pode_gerenciar_conta(ator, alvo):
    if not ator or not alvo or not ator.get("ativo", 1) or not gerencia(ator):
        return False
    if alvo.get("nivel") == "superadmin":
        return False
    return permite(ator, "tecnica") or LEVEL_ORDER.get(alvo.get("nivel"), 99) < LEVEL_ORDER["admin"]


def niveis_atribuiveis(ator):
    if permite(ator, "tecnica"):
        return ("admin", "operador", "visualizador", "usuario")
    return ("operador", "visualizador", "usuario") if gerencia(ator) else ()


def exige_tecnica(endpoint, caminho):
    return (caminho.startswith(("/admin/sistema", "/api/admin/sistema"))
            or endpoint in {"processar.kobo_config", "processar.kobo_testar", "liraa.configurar_kobo"})
