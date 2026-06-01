from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple


LEVEL_ORDER = {
    "visualizador": 1,
    "operador": 2,
    "admin": 3,
}


@dataclass(frozen=True)
class AppModule:
    key: str
    title: str
    href: str
    endpoint: str
    icon: str
    nav_section: str
    short_title: Optional[str] = None
    sidebar_title: Optional[str] = None
    description: str = ""
    tags: Tuple[str, ...] = ()
    min_level: str = "visualizador"
    show_topbar: bool = True
    show_sidebar: bool = True
    show_home: bool = True
    badge: Optional[str] = None
    endpoints: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.endpoints:
            object.__setattr__(self, "endpoints", (self.endpoint,))
        if self.short_title is None:
            object.__setattr__(self, "short_title", self.title)
        if self.sidebar_title is None:
            object.__setattr__(self, "sidebar_title", self.title)


MODULES: Tuple[AppModule, ...] = (
    AppModule(
        key="home",
        title="Inicio",
        short_title="Inicio",
        href="/",
        endpoint="home.page",
        icon="casa.svg",
        nav_section="Principal",
        show_home=False,
        endpoints=("home", "home.page"),
    ),
    AppModule(
        key="dashboard",
        title="Dashboard Visitas",
        short_title="Dashboard",
        href="/dashboard",
        endpoint="consultas.dashboard",
        icon="grafico_barra.svg",
        nav_section="Analise",
        description="Indicadores, graficos e evolucao temporal das visitas de campo.",
        tags=("PE", "TB", "TBO", "PVE"),
        endpoints=("dashboard", "consultas.dashboard"),
    ),
    AppModule(
        key="visitas",
        title="Lista de Visitas",
        short_title="Visitas",
        href="/visitas",
        endpoint="consultas.visitas",
        icon="prancheta.svg",
        nav_section="Analise",
        description="Tabela completa de todas as visitas com filtros e busca.",
        tags=("Filtros", "Busca"),
        endpoints=("visitas", "consultas.visitas"),
    ),
    AppModule(
        key="laboratorio",
        title="Resultados Lab.",
        short_title="Laboratorio",
        href="/laboratorio",
        endpoint="consultas.laboratorio",
        icon="microscopio.svg",
        nav_section="Analise",
        description="Resultados de coletas de ovitrampas com analise por especie.",
        tags=("Aegypti", "Albopictus"),
        endpoints=("laboratorio", "consultas.laboratorio"),
    ),
    AppModule(
        key="conta_ovos_sispncd",
        title="Conta Ovos e SisPNCD",
        href="/conta-ovos-sispncd",
        endpoint="conta_ovos_sispncd.page",
        icon="fichario.svg",
        nav_section="Analise",
        description="Boletim TBO e consolidado SisPNCD com consultas sobre dados ja importados.",
        tags=("TBO", "Leitura"),
    ),
    AppModule(
        key="esporotricose",
        title="Esporotricose",
        href="/esporotricose",
        endpoint="esporotricose.page",
        icon="pets.svg",
        nav_section="Analise",
        description="Visitas domiciliares para coleta de dados sobre moradores e animais.",
        tags=("Kobo", "Animais"),
        endpoints=("esporotricose", "esporotricose.page"),
    ),
    AppModule(
        key="recolhimentos",
        title="Recolhimentos",
        href="/recolhimentos",
        endpoint="recolhimentos.page",
        icon="pneu.svg",
        nav_section="Analise",
        description="Controle de recolhimento de pneus, loucas sanitarias, TVs, parachoques e outros materiais.",
        tags=("Kobo", "Materiais"),
        endpoints=("recolhimentos", "recolhimentos.page"),
    ),
    AppModule(
        key="amostras_animais",
        title="Amostra de Animais",
        short_title="Amostras",
        href="/amostras-animais",
        endpoint="amostras_animais.page",
        icon="amostra_animal.svg",
        nav_section="Analise",
        description="Reclamacoes, investigacoes, capturas e acidentes envolvendo animais de interesse.",
        tags=("Kobo", "Animais"),
        endpoints=("amostras_animais", "amostras_animais.page"),
    ),
    AppModule(
        key="bri",
        title="BRI",
        href="/bri",
        endpoint="bri.page",
        icon="borrifador.svg",
        nav_section="Analise",
        description="Borrifamento Residual Intradomiciliar em ovitrampas, pontos estrategicos e outros locais.",
        tags=("Tratamento", "Kobo"),
        endpoints=("bri", "bri.page"),
    ),
    AppModule(
        key="relatorio_agente",
        title="Rel. por Agente",
        short_title="Agente",
        href="/relatorio-agente",
        endpoint="relatorio_agente.page",
        icon="usuario.svg",
        nav_section="Analise",
        description="Desempenho individual: visitas, positividade, produtividade.",
        tags=("Relatorio",),
        endpoints=("relatorio_agente", "relatorio_agente.page"),
    ),
    AppModule(
        key="notificacoes",
        title="Notificacoes",
        href="/notificacoes",
        endpoint="notificacoes.page",
        icon="sino.svg",
        nav_section="Gestao",
        description="Gestao de focos positivos, impressao e controle de entregas.",
        tags=("Gestao", "DOCX"),
        badge="notificacoes",
        endpoints=("notificacoes", "notificacoes.page"),
    ),
    AppModule(
        key="mapa",
        title="Mapa",
        href="/mapa",
        endpoint="mapa.page",
        icon="mapa.svg",
        nav_section="Gestao",
        description="Quarteiroes trabalhados, focos e cobertura por localidade no mapa.",
        tags=("Leaflet", "OpenStreetMap"),
        endpoints=("mapa", "mapa.page"),
    ),
    AppModule(
        key="pontos_estrategicos",
        title="Pontos Estrategicos",
        short_title="PEs",
        href="/pontos-estrategicos",
        endpoint="pontos_estrategicos.page",
        icon="marcador.svg",
        nav_section="Gestao",
        description="Cadastro mestre dos pontos estrategicos visitados quinzenalmente.",
        tags=("Cadastro", "PE"),
        endpoints=("pontos_estrategicos", "pontos_estrategicos.page"),
    ),
    AppModule(
        key="agenda",
        title="Agenda",
        href="/agenda",
        endpoint="agenda.page",
        icon="calendario.svg",
        nav_section="Gestao",
        description="Calendario de atividades, lembretes e eventos automaticos das visitas.",
        tags=("Calendario", "Lembretes"),
        badge="agenda",
        endpoints=("agenda", "agenda.page"),
    ),
    AppModule(
        key="sistema",
        title="Central do Sistema",
        short_title="Sistema",
        href="/admin/sistema",
        endpoint="admin.admin_sistema",
        icon="raio.svg",
        nav_section="Administracao",
        description="Saude operacional: banco, backups, importacoes, auditoria e atalhos.",
        tags=("Admin", "Status"),
        min_level="admin",
        endpoints=("admin_sistema", "admin.admin_sistema"),
    ),
    AppModule(
        key="processar",
        title="Processar Planilhas",
        short_title="Processar",
        href="/processar",
        endpoint="processar.processar_page",
        icon="pasta.svg",
        nav_section="Administracao",
        description="Upload e processamento das planilhas exportadas do KoboToolbox.",
        tags=("Admin", "ETL"),
        min_level="admin",
        endpoints=("processar_page", "processar.processar_page"),
    ),
    AppModule(
        key="usuarios",
        title="Gestao de Usuarios",
        short_title="Usuarios",
        sidebar_title="Gestao de Usuarios",
        href="/admin/usuarios",
        endpoint="admin.admin_usuarios",
        icon="usuarios.svg",
        nav_section="Administracao",
        description="Gestao de acessos, niveis de permissao e reset de senhas.",
        tags=("Admin", "Acessos"),
        min_level="admin",
        endpoints=("admin_usuarios", "admin.admin_usuarios"),
    ),
    AppModule(
        key="controle_pessoal",
        title="Controle de Pessoal",
        short_title="Pessoal",
        href="/admin/agentes",
        endpoint="controle_pessoal.page",
        icon="usuarios.svg",
        nav_section="Administracao",
        description="Cadastro operacional de agentes, situacao funcional e historico de trabalho.",
        tags=("Admin", "Agentes"),
        min_level="admin",
        endpoints=("controle_pessoal", "controle_pessoal.page"),
    ),
    AppModule(
        key="auditoria",
        title="Auditoria",
        href="/admin/auditoria",
        endpoint="admin.admin_auditoria",
        icon="cadeado.svg",
        nav_section="Administracao",
        description="Consulta de eventos administrativos, seguranca e operacoes sensiveis.",
        tags=("Admin", "Log"),
        min_level="admin",
        endpoints=("admin_auditoria", "admin.admin_auditoria"),
    ),
)


SECTION_ORDER = ("Principal", "Analise", "Gestao", "Administracao")


def can_access(module: AppModule, user) -> bool:
    level = (user or {}).get("nivel") if isinstance(user, dict) else None
    return LEVEL_ORDER.get(level or "visualizador", 0) >= LEVEL_ORDER.get(module.min_level, 999)


def visible_modules(user, area: Optional[str] = None) -> List[AppModule]:
    modules = [module for module in MODULES if can_access(module, user)]
    if area == "topbar":
        modules = [module for module in modules if module.show_topbar]
    elif area == "sidebar":
        modules = [module for module in modules if module.show_sidebar]
    elif area == "home":
        modules = [module for module in modules if module.show_home]
    return modules


def grouped_modules(modules: Iterable[AppModule]):
    result = []
    for section in SECTION_ORDER:
        items = [module for module in modules if module.nav_section == section]
        if items:
            result.append({"section": section, "items": items})
    return result
