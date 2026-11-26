"""Avisos de boas-vindas e novidades exibidos nas areas web do VSATT."""

from app_core.version import APP_VERSION


RELEASES = {
    "2.20.0": {
        "titulo": "Composição e exportação de mapas no GeoVSATT",
        "mudancas": [
            "Personalize o mapa, as camadas, a imagem-base e a legenda para imprimir ou salvar em PDF.",
            "Desenhe uma área para estimar sua população com as residências cadastradas no Registro Geográfico.",
            "As contas autorizadas pelo superadmin podem exportar camadas em CSV, GeoJSON e KML.",
        ],
    },
    "2.19.0": {
        "titulo": "Cartografia, filtros e vigilância no GeoVSATT",
        "mudancas": [
            "O mapa usa a nova malha de quarteirões, localidades em polígonos e o limite municipal na abertura.",
            "Busque endereços com sugestões do Registro Geográfico. Abra os detalhes clicando na feição.",
            "O menu oferece Esri World Imagery, filtros por camada e opções de estilo por categoria.",
            "Ovitrampas, pontos estratégicos e ações com coordenadas estão disponíveis para os perfis autorizados.",
        ],
    },
    "2.18.0": {
        "titulo": "Importação e novas camadas no GeoVSATT",
        "mudancas": [
            "Os atalhos de importação abrem formulários próprios para arquivos GeoJSON.",
            "A busca tem uma opção explícita de CEP, consultada na BrasilAPI.",
            "O menu oferece imagens de satélite e uma camada restrita de Esporotricose animal.",
        ],
    },
    "2.17.0": {
        "titulo": "Busca e medições no GeoVSATT",
        "mudancas": [
            "Pesquise endereços do RG e encontre a localidade e o quarteirão.",
            "Consulte um CEP, use o zoom de aproximação e meça distâncias e áreas no mapa.",
            "O superadmin encontra os atalhos de importação em Gerenciar camadas.",
        ],
    },
    "2.16.0": {
        "titulo": "GeoVSATT começou a ganhar forma",
        "mudancas": [
            "O portal VSATT agora apresenta o novo acesso ao GeoVSATT.",
            "O mapa territorial inicial reúne quarteirões, localidades e logradouros já disponíveis.",
            "O superadmin pode importar GeoJSON, publicar versões e definir o acesso a cada camada.",
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
