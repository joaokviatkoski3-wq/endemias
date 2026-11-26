"""Avisos de boas-vindas e novidades exibidos nas areas web do VSATT."""

from app_core.version import APP_VERSION


RELEASES = {
    "2.16.0": {
        "titulo": "GeoVSATT começou a ganhar forma",
        "mudancas": [
            "O portal VSATT agora apresenta o novo acesso ao GeoVSATT.",
            "O mapa territorial inicial reúne quarteirões, localidades e logradouros já disponíveis.",
            "Endemias, Ambiental e GeoVSATT passam a mostrar avisos de boas-vindas e novidades.",
        ],
    },
}


def aviso_atual(setor=None):
    setor = setor or "endemias"
    geo = setor == "geo"
    release = RELEASES.get(APP_VERSION, {"titulo": "Novidades do VSATT", "mudancas": []})
    return {
        "versao": APP_VERSION,
        "area": setor,
        "titulo": "Bem-vindo ao GeoVSATT" if geo else release["titulo"],
        "resumo": (
            "Este é o novo espaço cartográfico da Vigilância em Saúde. Use o menu de camadas, "
            "a busca territorial e o clique nos quarteirões para explorar os dados disponíveis."
            if geo
            else "Veja o que mudou nesta versão. Este aviso voltará a aparecer quando houver uma nova atualização."
        ),
        "mudancas": list(release["mudancas"]),
    }
