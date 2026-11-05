# Identidade dos setores, logs e ajuda — 2.1.0

## Situação operacional

Preparação autorizada em 05/11/2026. Produção permanece em 2.0.2 até a execução
do novo atalho elevado e a confirmação do relatório nativo. Não repetir os
ativadores antigos nem a recomposição histórica de BRI.

## Escopo solicitado

- Endemias conserva a identidade azul escuro. Ambiental usa verde escuro e o
  logotipo fornecido; o portal VSATT usa a própria marca e os dois tons.
- A ajuda deve respeitar o setor atual e as permissões reais de cada conta,
  incluindo busca, artigos relacionados e acesso direto à API.
- A auditoria de negócio e os registros técnicos têm propósitos diferentes:
  a primeira descreve operações explicitamente auditadas; os segundos permitem
  diagnosticar atendimentos e falhas. Nenhum registro novo recompõe o passado.
- Senhas, cookies, tokens e corpos completos de formulários não devem integrar
  a nova trilha técnica. Ela não substitui a auditoria do Windows/PostgreSQL nem
  demonstra que uma pessoa leu cada dado exibido.

As decisões específicas de cobertura, exportação e retenção e os resultados
das verificações serão registrados ao concluir a integração.

## Implantação

O ativador `scripts/ativar_identidade_logs_ajuda_210_windows.py` reutiliza o fluxo
homologado de troca 2.0.2 → 2.1.0, sem migração de banco. Exige os commits exatos
da origem e da candidata limpos, tarefa e ambiente esperados, backup SQL e
completo antes da troca, breve pausa e prova pela identidade limitada.

Preserva contas, dados, anexos, duas configurações Kobo, arquivo SQLite
congelado, tarefa, portas, DNS e Cloudflare. O agendamento de importação é
devolvido ao estado anterior; não importa respostas como parte desta entrega.

As worktrees de estilo, logs e ajuda são distintas; a integração e homologação
acontecem em `C:\endemias-interface`, branch `codex/identidade-logs-ajuda`.
Todas as massas de teste são fictícias. Evidências detalhadas ficam em `.venv`,
fora do repositório público.
