# Interface dos setores — 2.0.0-rc.2 ativa

Preparada e ativada em 05/11/2026, a pedido do usuário. Produção em
**2.0.0-rc.2**, release `2772226`. Usuário executou o atalho e informou conclusão;
relatório, versão pública/local e prova da conta limitada foram conferidos.
Não repetir os ativadores: este pacote não teve migração nem nova divisão de Kobo.

## Alterações solicitadas

1. Portal `vsatt.com.br`: identidade tipográfica VSATT, identificação do
   município, duas entradas e rodapé com versão/data. Sem brasão inventado,
   rastreamento, login central ou criação de sessão no portal.
2. Atalho no topo para o outro setor somente quando `pode_entrar` autoriza.
   Externo usa o domínio canônico; LAN preserva a mesma máquina, portas
   Endemias 5000/Ambiental 5004 e cookies independentes. Não concede permissão
   nem transfere sessão. Pode exigir login no destino.
3. Relatórios ambientais: período, área, localidade, agente, quarteirão,
   situação/tipo de imóvel/origem e filtros específicos de Esporotricose e
   Amostras. Seis agrupamentos; paginação de 50 linhas; CSV/XLSX/PDF contêm
   todas as linhas do mesmo recorte. XLSX com cabeçalho congelado e autofiltro.
4. Dashboard ambiental: indicadores, cinco gráficos, evolução mensal,
   localidades, situação das visitas, distribuição por área e tipos de animais.
   Filtros compartilhados com relatórios e ligação para o relatório do recorte.
5. Vigiágua: ícone local de gota d'água em navegação, início e página reservada.
   O módulo permanece em desenvolvimento.
6. Mapa ambiental: ruas/satélite Esri, referência de lugares no satélite,
   etiquetas a partir do zoom 15, preenchimento ajustável, escala, legenda,
   enquadramento e filtro de período/localidade/área/agente/quarteirão.
   Localidade filtra também a geometria; opção apenas com registros. Contagem
   de registros sem correspondência não duplica polígonos repetidos.
7. Agenda dos dois setores: botões anterior/próximo com setas CSS e texto,
   sem fonte embutida bloqueada pelo CSP. Mesma FullCalendar 6.1.11, agora
   local, com licença MIT e hashes; removida referência CSS inexistente.
8. Início Ambiental: nove atalhos operacionais, conforme permissões, sem
   formulário, gráficos ou relatório misturados à entrada.
9. Previsão na agenda: bloco não pode mais ser comprimido pelo calendário.
   Causa reproduzida antes da correção: altura de 2 pixels no desktop.

## Significado e limites dos dados

- Indicadores operacionais destas telas contam **visitas** de Esporotricose
  e Amostras. Não são um painel de diagnósticos/casos humanos.
- Animais cadastrados e com feridas contam cadastros de Esporotricose nas
  visitas selecionadas. Feridas não equivalem a diagnóstico. Selecionar uma
  espécie/feridas exige correspondência no mesmo animal, sem multiplicar a
  visita. Os indicadores de animais incluem os cadastros das visitas obtidas.
- Quantidade em Amostras é o campo preenchido no formulário, distinta do
  número de visitas. A informação pode estar ausente nos cadastros antigos.
- Sem datas, o recorte é todo o histórico disponível. Datas, área, agrupamento
  e quarteirão são validados. Filtros específicos selecionam apenas sua área;
  combinar filtros incompatíveis pode produzir resultado vazio.
- Relatório não exporta nome/endereço de moradores nem ranking de agentes.
  Nível `usuario` continua vendo apenas o próprio agente nos filtros; nome de
  colega enviado por URL é recusado também nas exportações.
- Campos importados são texto escapado; gráficos usam JSON seguro;
  popups/etiquetas usam `textContent`. CSV/XLSX neutralizam fórmulas em texto
  e mantêm contagens numéricas. CSP permanece sem `unsafe-eval`/fontes data:.
- Dados operacionais são exclusivamente ambientais; catálogos e território
  continuam compartilhados. Nada de Endemias é somado a estes indicadores.
- Imagens de fundo do mapa e atualização da previsão exigem internet.
  Quarteirões/dados locais e calendário ficam disponíveis na rede do setor.
  Geo continua fora deste escopo.

## Validação e implantação

- Massa fictícia em worktree `C:\endemias-interface`, branch
  `codex/aperfeicoar-interface-setores`. Não foi copiado banco de produção.
- 41 testes focados passaram: fronteiras/cookies, filtros, contagens sem
  duplicação, exportação, escape/fórmulas, atalho autorizado e simulação de
  implantação/retorno. Novas consultas também passaram em PostgreSQL 18
  descartável/SCRAM, porta 55444; cluster e credenciais foram removidos.
- Chromium com CSRF e CSP de bloqueio: desktop 1365×900 e celular 390×844;
  cinco gráficos carregados, navegação mensal, previsão com cinco dias nos
  dois setores, versão no portal, filtros de geometria/área e etiquetas.
  Capturas conferidas visualmente em `.venv/browser-setores-*`.
- Suíte geral: **1.024 testes OK, seis ignorados**, em 386,761 segundos.
  Log `.venv/regressao-interface.log`; avisos de recursos/encerramento em
  testes legados não causaram falhas. Resultado Chromium final em
  `.venv/setores-browser-resultado.json`, capturas `browser-setores-4ntbr7ba`;
  PostgreSQL em `.venv/setores-pg-resultado.json`. JavaScript/Python e
  `git diff --check` conferidos. Não interpretar ensaio como ativação.
- `scripts/ativar_interface_setores_windows.py` exige administrador Windows:
  confere origem/commits exatos/esquema sem pendências; pausa o agendamento
  Kobo durante a janela; faz backup PostgreSQL e completo; para as três
  entradas antes de integrar templates; compara dados/arquivos; executa
  prova na mesma identidade limitada e confirma logins/portal antes de devolver
  o agendamento. Muda só a versão na configuração protegida do servidor.
- Não há DDL, instalação de dependências, redefinição de senha, alteração de
  lotação, divisão do Kobo, alteração de bootstrap, firewall ou Cloudflare.
  Falha retorna código/configuração; nunca restaura dump nem apaga dados.
- Após execução, ler
  `C:\ProgramData\EndemiasWeb\ativacao-interface200rc2-resultado.json`, conferir
  os três endereços HTTPS, acesso autenticado e versão exibida. Ainda candidata
  da 2.0; não declarar estável apenas por testes automatizados.
- Atalho preparado na Área de Trabalho: **Atualizar VSATT - Interface 2.0
  RC2.bat**. Executar com botão direito → Executar como administrador e
  informar o resultado. A permissão é exigida pelo Windows para a tarefa e
  configuração protegidas. Código da candidata salvo em `0b46719`, enviado à
  branch remota; manifesto local com hashes exatos em
  `.venv/pacote-interface200rc2.json` (registro da preparação).

## Ativação conferida em 05/11/2026

- Relatório `ativacao-interface200rc2-resultado.json`: aplicado/concluido,
  96 tabelas/dados e arquivos preservados; nenhum DDL, conta/senha, configuração
  Kobo, firewall ou Cloudflare alterado. Mesma tarefa/identidade/ambiente;
  agendamento Kobo restaurado. Todos os checks da conta limitada passaram.
- Backup PostgreSQL de 7.545.887 bytes/catalogado e completo de 310.615.133
  bytes; caminhos e hashes no estado curto. SQLite congelado inalterado.
- Portal e dois logins HTTPS: 200/rc.2, private/no-store e CF DYNAMIC; portal
  sem sessão, links corretos; APIs anônimas negadas (401). Logins locais
  5000/5004: 200/rc.2. Evidência:
  `C:\endemias-interface\.venv\publicacao-interface200rc2.json`.
- O relato do usuário confirma a instalação. Conferência visual autenticada
  real das telas novas ainda não informada. Continua candidata da versão 2.0.
