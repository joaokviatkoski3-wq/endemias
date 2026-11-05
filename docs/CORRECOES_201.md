# Correções compatíveis 2.0.1

Pacote validado em 05/11/2026, na branch `codex/correcoes-201`, worktree
`C:\endemias-interface`. Produção permanece em 2.0.0 até a ativação controlada.

O conjunto melhora a consistência dos contratos Kobo, das edições, das listas,
dos filtros, da navegação de ajuda e das integrações entre rotinas dos setores.
Inclui paginação com contagem integral, exportação filtrada e detalhes de BRI
e Amostras de Animais, preservando a separação dos setores e dos perfis.

## Comportamento esperado

- BRI preserva carga decimal, destino e endereço. Amostras distingue animal
  motivador, capturado e espécie. Visitas preservam sequências, ciclo, Sanepar
  e horários dos contratos atuais, mantendo os formatos legados.
- Edição de Esporotricose preserva endereço e mantém equipe e vínculos coerentes.
  Buscas de animal ferido aparecem na Agenda Ambiental. Previsão insuficiente
  é identificada como incompleta.
- Casos humanos seguem o acompanhamento de data mais recente. Na mesma data,
  vale o último incluído. Lançamento retroativo só acrescenta histórico; não
  existe nova operação de edição de acompanhamento. Cadastro sem histórico
  mantém situação inicial editável; com histórico, a situação é somente leitura.
- Lotes de ovitrampas exigem leituras completas ao concluir, com zero explícito.
  Rascunhos podem ser parciais. Mapa integra API, laboratório concluído e legado
  sem duplicar o mesmo evento, preservando coletas de dias distintos conhecidos.
  Identidades de quarteirão e de PE seguem o território e o vínculo correto.
- As três listas operacionais têm total real, páginas de até 500 registros
  (100 por padrão) e CSV completo do mesmo filtro, incluindo a pesquisa.
  BRI e Amostras oferecem detalhes sem aumentar a largura das tabelas.
- Gestores de Endemias podem conferir correções de BRI/Recolhimentos já
  importados: período de envio obrigatório, até um ano/5.000 envios; prévia
  válida por 15 minutos; campos inicialmente desmarcados; aprovação individual.
  UUID identifica o registro. Conflito exige nova conferência. Valores não
  aprovados permanecem intactos, com vínculos, derivados e auditoria transacionais.
- Escopo nominal, filtros, ajuda setorial, relatórios e oficialização do RG
  receberam ajustes de consistência. Revisão e exclusão concorrentes não podem
  ultrapassar a oficialização.

As verificações usam dados fictícios e ambientes isolados. Não executar
importação real nem recompor registros históricos como parte da atualização
do código. As regras de reconciliação devem preservar edições da equipe e
exigir conferência antes de aplicar diferenças escolhidas.

O ativador `scripts/ativar_correcoes_201_windows.py` usa o procedimento já
homologado: confere a origem 2.0.0, gera backups, pausa importação agendada,
encerra as entradas antes de integrar os arquivos, valida sob a identidade
limitada e reinicia preservando configurações, contas e dados. Sem migração
de esquema. Falha retorna código/configuração; não restaura banco automaticamente.

O diagnóstico detalhado e a matriz de acompanhamento da revisão são locais,
conforme `docs/REVISAO_FUNCIONAL_200_20261105.md`. Este repositório é público.
Ativação ainda pendente da execução administrativa no Windows.

## Validação concluída

- Primeira regressão: 1.072 testes, seis ignorados, três fixtures antigas que
  oficializavam antes da aprovação precisaram ser adaptadas à ordem correta.
  Não se reduziu a garantia da aplicação para acomodá-las. A regressão final
  concluiu **1.102 testes em 421,973 s, sem falhas e com seis ignorados**, cobrindo
  também lotes/mapa, formulário humano e conferência manual. Após o ajuste final
  de precedência das datas no mapa, os **15 testes focados de entomologia** passaram.
  Logs locais: `.venv/regressao-201-final.log` e `.venv/entomologia-201-final.log`.
- PostgreSQL descartável em porta 55444: consultas, filtros, exportações,
  rollback RG, revisão/exclusão concorrentes, cronologia humana e conferência
  de campos/auditoria passaram. Cluster encerrado e credenciais de ensaio removidas.
- Chromium: listas, paginação, CSV, detalhes, texto literal, filtros e botões
  passaram nos tamanhos desktop/celular. Navegação dos dois setores, login CSRF,
  portal e sessões locais independentes também passaram.
- Provas complementares dos módulos usam apenas registros fictícios.
  Nenhuma resposta Kobo real foi consultada e nenhuma reconciliação foi aplicada.
- SQLite congelado da produção conserva SHA-256
  `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- Persistem avisos antigos de conexões SQLite de teste não fechadas e um erro de
  encerramento de listener fictício do Waitress no Windows; a suíte não registrou
  falhas. Testes são evidência de regressão, não certificação integral do sistema.
