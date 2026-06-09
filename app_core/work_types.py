WORK_TYPES = (
    {
        "codigo": "TB",
        "label": "Tratamento de Bloqueio",
        "cor": "#3b82f6",
    },
    {
        "codigo": "TBO",
        "label": "Trat. Bloqueio Ovitrampas",
        "cor": "#10b981",
    },
    {
        "codigo": "PE",
        "label": "Ponto Estrat\u00e9gico",
        "cor": "#f59e0b",
    },
    {
        "codigo": "PVE",
        "label": "Pesquisa Vetorial Especial",
        "cor": "#8b5cf6",
    },
)

WORK_TYPE_COLORS = {item["codigo"]: item["cor"] for item in WORK_TYPES}
WORK_TYPE_LABELS = {item["codigo"]: item["label"] for item in WORK_TYPES}
WORK_TYPE_COLORS["LIRA"] = "#ef4444"
WORK_TYPE_LABELS["LIRA"] = "LIRA"
WORK_TYPE_CODES = tuple(item["codigo"] for item in WORK_TYPES)

ETL_WORK_TYPE_FIELDS = {
    "TB": {
        "gera_notificacao_padrao": 1,
        "hora_inicio_col": "Hora",
        "depositos_eliminados_col": "Depósitos eliminados",
        "tratamento_houve_col": "O imóvel foi Tratado com Larvicida?",
        "tratamentos": (
            {
                "tipo_col": "Tipo L1",
                "carga_col": "Quantidade carga (gr)",
                "qtd_depositos_col": "Quantidade depósitos tratados",
            },
        ),
    },
    "TBO": {
        "gera_notificacao_padrao": 1,
        "calcula_duracao": True,
        "tratamentos_em_depositos": True,
    },
    "PE": {
        "gera_notificacao_padrao": 0,
        "hora_inicio_col": "Digite a hora",
        "depositos_eliminados_col": "Total de Depósitos eliminados",
        "tratamento_houve_col": "Houve tratamento quimico?",
        "tratamentos": (
            {
                "tipo_col": "Tipo",
                "carga_col": "Quantidade carga",
                "qtd_depositos_col": "Quantidade depósitos tratados",
            },
        ),
    },
    "PVE": {
        "gera_notificacao_padrao": 1,
        "hora_inicio_col": "Hora",
        "depositos_eliminados_col": "Depósitos Eliminados",
        "tratamento_houve_col": "O imóvel foi Tratado com Larvicidaou BRI?",
        "tratamentos": (
            {
                "tipo_col": "Tipo L1",
                "carga_col": "Quantidade carga (gr)",
                "qtd_depositos_col": "Quantidade depósitos tratados",
            },
            {
                "tipo_col": "Tipo",
                "carga_col": "Quantidade carga",
                "qtd_depositos_col": None,
            },
        ),
    },
}

STATUS_OPTIONS = [
    "pendente",
    "impressa",
    "entregue",
    "morador n\u00e3o localizado",
    "dados inconsistentes",
    "arquivada",
]

STATUS_COLORS = {
    "pendente": "amarelo",
    "impressa": "azul",
    "entregue": "verde",
    "morador n\u00e3o localizado": "vermelho",
    "dados inconsistentes": "roxo",
    "arquivada": "cinza",
}

AGENDA_TYPE_COLORS = {
    "reuniao": "#1a4fba",
    "planejamento": "#7c3aed",
    "campo": "#10b981",
    "prazo": "#ef4444",
    "treinamento": "#8b5cf6",
    "tarefa": "#f59e0b",
    "ferias": "#06b6d4",
    "outro": "#64748b",
}

AGENDA_TYPE_LABELS = {
    "reuniao": "Reuni\u00e3o",
    "planejamento": "Planejamento",
    "campo": "Campo",
    "prazo": "Prazo",
    "treinamento": "Treinamento",
    "tarefa": "Tarefa",
    "ferias": "Férias",
    "outro": "Outro",
}

AGENDA_FORM_LABELS = {
    "reuniao": "Reuni\u00e3o",
    "planejamento": "Planejamento",
    "campo": "Campo / Atividade",
    "prazo": "Prazo / Entrega",
    "treinamento": "Treinamento",
    "tarefa": "Tarefa interna",
    "ferias": "Férias",
    "outro": "Outro",
}

AGENDA_TYPES = tuple(
    {
        "codigo": codigo,
        "label": AGENDA_TYPE_LABELS[codigo],
        "form_label": AGENDA_FORM_LABELS[codigo],
        "cor": cor,
    }
    for codigo, cor in AGENDA_TYPE_COLORS.items()
)


def configured_work_type_codes(config):
    tipos = config.get("tipos_trabalho", {})
    if not isinstance(tipos, dict):
        return set()
    return set(tipos.keys())


def validate_config_work_types(config):
    configured = configured_work_type_codes(config)
    known = set(WORK_TYPE_CODES)

    missing_in_ui = sorted(configured - known)
    missing_in_config = sorted(known - configured)

    errors = []
    if missing_in_ui:
        errors.append(
            "Tipos em config.json sem cadastro em app_core/work_types.py: "
            + ", ".join(missing_in_ui)
        )
    if missing_in_config:
        errors.append(
            "Tipos em app_core/work_types.py sem configuracao em config.json: "
            + ", ".join(missing_in_config)
        )
    return errors


def etl_fields_for(codigo):
    return ETL_WORK_TYPE_FIELDS.get(codigo, {})


def gera_notificacao_padrao(codigo):
    return int(etl_fields_for(codigo).get("gera_notificacao_padrao", 1))


def duration_work_type_codes():
    return tuple(
        codigo
        for codigo, fields in ETL_WORK_TYPE_FIELDS.items()
        if fields.get("calcula_duracao")
    )


def primary_duration_work_type_code():
    codigos = duration_work_type_codes()
    return codigos[0] if codigos else None
