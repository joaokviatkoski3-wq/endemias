# Portal no topo e etiquetas leves — 2.0.0-rc.3 ativa

Preparada e ativada em 05/11/2026, a pedido do usuário, release `2bf6171`.
Usuário executou o novo atalho; relatório/versão pública/local e prova da conta
limitada conferidos. Aprovou o visual da rc.2 e identificou travamento nas
etiquetas do mapa Ambiental, corrigido nesta candidata.

## Alterações

- Botão **Portal VSATT** ao lado da troca de setor, nos dois sistemas. Abre
  `https://vsatt.com.br` na mesma aba, inclusive quando a origem é LAN. Visível
  para todas as contas autenticadas; troca de setor continua só para quem tem
  autorização. Não transfere sessão nem concede acesso a outro setor.
- Em celular, os dois atalhos ficam juntos numa linha própria do cabeçalho,
  sem comprimir nome da página, conta, tema ou menu.
- Causa do travamento: a troca de checkbox reconstruía a camada inteira e
  criava um tooltip permanente por quarteirão. Ocultar por CSS em zoom baixo
  mantinha esses elementos e seus custos no navegador.
- Etiquetas agora usam **um canvas**, independente dos polígonos. Só desenha
  posições na área visível a partir do zoom 15, até 300 textos por tela, com
  prevenção de sobreposição. Ampliação revela mais detalhes. Navegação atualiza
  no fim do movimento; ativar/desativar não reconstrói os quarteirões.
- Âncoras reaproveitadas enquanto os filtros não mudam. Densidade de pixels
  limitada a 2; descarte de listeners/quadros ao remover o mapa. Um elemento
  canvas permanece após alternâncias, sem acumular DOM por etiqueta.
- Conteúdo importado é texto no canvas/popup, sem HTML; popup só é construído
  quando aberto. Filtros, cores, contagens, geometrias e bases preservados.
- Sem alteração de banco, usuários, senhas, lotação, configurações Kobo,
  dependências, Cloudflare ou firewall. Geo continua futuro.

## Conferências

- 38 testes focados de setores/instalador passaram; mais 31 de superadmin,
  sessões, identidade e compatibilidade de autenticação passaram.
- Chromium/CSRF/CSP: dois setores, desktop 1365×900/celular 390×844, botão
  canônico, filtros, popup e etiquetas. Capturas conferidas visualmente.
- Ensaio adicional compara JavaScript da rc.2 com a candidata usando 1.500
  polígonos fictícios e CPU 4x mais lenta, sem depender da internet; candidata
  também recebe 6.000 polígonos e testa zoom, movimento, alternância e resize.
  Passou: rc.2 9.834,6 ms bloqueando o clique/10.019,7 ms até dois quadros;
  candidata 1,4 ms/87,5 ms. rc.2 recriou a camada/1.500 tooltips; candidata
  preservou os polígonos, usou um canvas e desenhou 44 etiquetas legíveis.
  Com 6.000 polígonos: 1,2 ms/316,7 ms, sem reconstrução e um canvas.
  Tempos são deste ensaio, não garantia para toda máquina. Evidência em
  `.venv/mapa-performance-resultado.json`, captura em
  `.venv/mapa-performance-6w15i74w/etiquetas-canvas.png`.
- Chromium geral em `.venv/setores-browser-resultado.json`, capturas
  `.venv/browser-setores-m5of_bbi`. Python/JavaScript e `git diff --check`
  conferidos. Nenhum teste usou dados ou banco de produção; hash do SQLite
  congelado permanece `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- Não é necessário repetir PostgreSQL completo: não há consulta, DDL ou
  formato de dados novo. Prova do instalador confere leitura dos novos scripts
  na conta real do serviço antes de reiniciar o atendimento.
- Referência técnica usada: [API Leaflet 1.9.4](https://leafletjs.com/reference-1.9.4.html),
  sem atualizar a biblioteca instalada.

## Implantação

`scripts/ativar_mapa_portal_windows.py` seleciona rc.2 → rc.3 no mesmo instalador
de interface, que recebeu parâmetros explícitos de origem/destino/marcador.
O ativador antigo conserva seus valores padrão e recusa origem diferente.
Sucesso, retorno após falha e recusa de migração pendente foram simulados.

Novo atalho na Área de Trabalho: **Atualizar VSATT - Mapa leve e Portal.bat**,
com SHA completo
da candidata e HEAD esperado da produção. Faz backup antes da troca, pausa
as três entradas antes de integrar templates, compara as 96 tabelas/arquivos,
prova identidade limitada, preserva configurações e devolve o agendamento Kobo.
Falha retorna apenas código/configuração, sem restaurar banco.

Relatório previsto:
`C:\ProgramData\EndemiasWeb\ativacao-mapa-portal200rc3-resultado.json`.
Executado e conferido. Não repetir os atalhos já usados.

## Ativação confirmada

- Aplicado/concluido às 12h55, 96 tabelas/dados e arquivos preservados; nenhum
  DDL ou alteração de contas, Kobo, identidade/ambiente, Cloudflare ou firewall.
  Prova limitada passou em todos os checks, inclusive leitura do novo script.
  Agendamento Kobo devolvido ao estado original.
- Backups PostgreSQL e completo criados antes da troca; caminhos e hashes no
  estado curto. Hash do SQLite congelado inalterado.
- Portal/logins HTTPS e logins locais 5000/5004: 200/rc.3; APIs sem sessão: 401.
  Portal sem cookie de sessão; private/no-store/CF DYNAMIC. Novos scripts/CSS
  conferidos byte a byte pelo endereço público contra os arquivos oficiais.
  Evidência em `C:\endemias-interface\.venv\publicacao-mapa-portal200rc3.json`.
- Resta observar etiquetas no uso real após a correção; aprovação visual da
  rc.2 já informada. Não declarar 2.0 estável apenas pelo ensaio automatizado.
