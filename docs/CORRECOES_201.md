# Correções compatíveis 2.0.1

Pacote em preparação em 05/11/2026, na branch `codex/correcoes-201`, worktree
`C:\endemias-interface`. Produção permanece em 2.0.0 até a ativação controlada.

O conjunto melhora a consistência dos contratos Kobo, das edições, das listas,
dos filtros, da navegação de ajuda e das integrações entre rotinas dos setores.
Inclui paginação com contagem integral, exportação filtrada e detalhes de BRI
e Amostras de Animais, preservando a separação dos setores e dos perfis.

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
Resultados finais de validação e de ativação serão registrados após execução.
