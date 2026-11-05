# Ajuda por área e acesso

A ajuda usa a área da aplicação aberta e as permissões atuais da conta. O
catálogo, a busca, as categorias e as sugestões da página passam pelo mesmo
filtro no servidor. Uma conta gestora que acessa os dois sistemas consulta a
ajuda de cada área no respectivo sistema.

| Acesso | Orientação disponível |
|---|---|
| Usuário e visualizador | Consulta, navegação, própria conta e formulários próprios permitidos |
| Operador | Consulta e operações liberadas nas rotinas da sua área |
| Admin | Gestão, importação e conferência manual, usuários, pessoal e auditoria |
| Superadmin | Gestão e administração técnica, conexão Kobo, backups e registros técnicos |
| Permissão de laboratório | Lançamentos e histórico conforme as regras do laboratório |

Conta exclusiva do laboratório recebe apenas esses tópicos e os da própria
conta. A integração deve manter `ajuda.api_ajuda` na lista de endpoints
permitidos do guard dessas contas; isso não libera outras páginas.

Os artigos distinguem consulta de alteração. Área Ambiental tem orientações
próprias para início, indicadores, relatórios, mapa, agenda, Esporotricose,
medicação, casos humanos, Amostras e a situação ainda inicial do Vigiágua.
Endemias tem orientações próprias para campo, laboratório, território, LIRAa,
ovitrampas, Conta Ovos/SisPNCD, BRI, recolhimentos e seus relatórios. Os assuntos
de conta, meteorologia e gestão comum respeitam o mesmo controle de acesso.

O painel começa com até três sugestões da página e seis outros títulos. Busca,
categoria e Mostrar os demais tópicos permitem explorar o restante autorizado.
As respostas não podem ser armazenadas em cache. Reabrir o painel, retornar à
página ou ao foco solicita novamente a ajuda; mudanças da conta, área ou
permissões descartam a seleção anterior. Requisições antigas são canceladas.

Os testes de ajuda verificam os cinco níveis nas duas áreas, o acesso por
capacidade, categorias e contextos, links GET reais e troca de escopo. Os ensaios
usam contas e dados fictícios, sem consultar integrações externas.
