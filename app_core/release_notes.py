"""Avisos de boas-vindas e novidades exibidos nas areas web do VSATT."""

from app_core.version import APP_VERSION


RELEASES = {
    "2.27.0": {
        "titulo": "GeoVSATT no campo e sem conexão",
        "mudancas": [
            "Os detalhes das feições abrem em um painel com rolagem. A legenda lateral acompanha as cores do mapa.",
            "O mapa de calor usa as feições da camada selecionada. A busca de lugares usa Nominatim quando configurado.",
            "Instale o GeoVSATT e prepare uma cópia offline com camadas, base de ruas e ortofotos selecionadas.",
            "Use busca, detalhes, medições, filtros, exportação e composições a partir da cópia no aparelho.",
        ],
    },
    "2.26.0": {
        "titulo": "Simbologia e etiquetas no GeoVSATT",
        "mudancas": [
            "Escolha cor única, categorias ou faixas numéricas no estilo de uma camada.",
            "Monte a etiqueta com dois campos, prefixo e sufixo, e ajuste os limites de zoom e o contorno.",
            "Confira uma amostra do símbolo, da etiqueta e da legenda antes de salvar.",
        ],
    },
    "2.25.0": {
        "titulo": "Ortofotos no GeoVSATT",
        "mudancas": [
            "O superadmin pode importar ortofotos MBTiles do QGIS, conferir a amostra e publicar uma versão.",
            "A ortofoto publicada aparece no seletor Mapa-base com fonte, data, condições de uso e opção de enquadrar.",
            "Use a ortofoto nas composições para impressão. O download completo exige autorização própria.",
        ],
    },
    "2.24.0": {
        "titulo": "Quarteirões trabalhados no GeoVSATT",
        "mudancas": [
            "Filtre as visitas do Endemias e do LIRAa por período, tipo de trabalho e localidade.",
            "Consulte os totais por tipo e situação ao clicar no quarteirão da malha ativa.",
            "Preserve o recorte nas composições e nas exportações autorizadas em CSV, GeoJSON e KML.",
        ],
    },
    "2.23.0": {
        "titulo": "Raios de bloqueio de esporotricose no GeoVSATT",
        "mudancas": [
            "Ative os raios de 150 m e consulte a situação e a data do bloqueio no cadastro animal.",
            "Veja os quarteirões alcançados, com área integral ou parcial no raio e contagem de casos sobrepostos.",
            "Abra o mapa de bloqueio do caso no Ambiental a partir do ponto ou do contorno do raio.",
        ],
    },
    "2.22.0": {
        "titulo": "Busca postal e mapa-base vetorial no GeoVSATT",
        "mudancas": [
            "Em Rua → CEP, consulte códigos postais dos logradouros de Almirante Tamandaré via ViaCEP.",
            "O Registro Geográfico sugere ruas e números enquanto você digita e abre os detalhes do quarteirão.",
            "A base OpenStreetMap · OpenFreeMap está disponível no mapa e nas composições para impressão.",
        ],
    },
    "2.21.0": {
        "titulo": "Equipamentos e composições salvas no GeoVSATT",
        "mudancas": [
            "O superadmin pode criar e editar equipamentos públicos e pontos de interesse na camada versionada.",
            "Salve composições com recorte, layout, títulos, camadas e filtros para reabrir na sua conta.",
            "Os filtros incluem comparações de datas e números, além de campos vazios ou preenchidos.",
        ],
    },
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
