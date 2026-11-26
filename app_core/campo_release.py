"""Informações da versão para quem já preparou o aplicativo de campo."""

import re

from app_core.version import APP_VERSION


RESUMOS = {
    "2.20.0": [
        "O GeoVSATT ganhou composição de mapas para impressão, população por área e exportação de camadas autorizadas.",
    ],
    "2.19.0": [
        "O GeoVSATT ganhou filtros por camada, sugestões de endereço do RG e a opção Esri World Imagery.",
    ],
    "2.18.0": [
        "O GeoVSATT ganhou importação de camadas, busca explícita por CEP e satélite Sentinel-2.",
    ],
    "2.17.0": [
        "No portal GeoVSATT, busque endereços do RG e consulte CEPs.",
    ],
    "2.16.0": [
        "O portal VSATT agora apresenta o acesso ao novo GeoVSATT.",
        "Endemias, Ambiental e GeoVSATT passam a mostrar avisos de boas-vindas e novidades.",
    ],
    "2.14.2": [
        "Compatibilidade com o cadastro de avisos nas versões atuais do Chrome para Android.",
        "O sininho confirma o agendamento do teste e informa se o serviço aceitou o envio.",
    ],
    "2.14.1": [
        "O superadmin pode testar os avisos neste aparelho pelo sininho.",
        "O aviso de atualização fica centralizado e reúne as mudanças das versões que o aparelho pulou.",
    ],
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


def _numero(versao):
    if not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6}){2}", versao):
        return ()
    return tuple(map(int, versao.split(".")))


def historico(desde):
    instalada, atual = _numero(desde), _numero(APP_VERSION)
    return [
        {"versao": versao, "mudancas": RESUMOS[versao]}
        for versao in sorted(RESUMOS, key=_numero, reverse=True)
        if instalada < _numero(versao) <= atual
    ]
