"""Informações da versão para quem já preparou o aplicativo de campo."""

from app_core.version import APP_VERSION


RESUMOS = {
    "2.14.0": [
        "A conta do piloto pode autorizar e testar avisos de campo com o app fechado no Chrome para Android.",
    ],
    "2.13.1": [
        "Agora você pode apagar seus rascunhos de visita no formulário e na lista de rascunhos.",
    ],
    "2.13.0": [
        "Novo nome e logo do Endemias no aplicativo instalado.",
        "RG por localidade e quarteirão, com uma linha por imóvel e ruas disponíveis offline.",
        "Sininho com os resultados dos tubos coletados pela sua equipe.",
    ],
}


def atual():
    return {"versao": APP_VERSION, "mudancas": RESUMOS.get(APP_VERSION, [])}
