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

## Onde consultar e exportar

Em cada setor, **Auditoria** continua disponível a admin e superadmin. A lista
deve exibir total, paginação e filtros; o XLSX deve respeitar o filtro completo,
com teto explícito de 10.000 eventos. Acima dele é necessário reduzir o período
ou outros filtros; a exportação não deve omitir silenciosamente os excedentes.

O superadmin pode selecionar **Registros técnicos** na mesma página
(`/admin/auditoria?origem=tecnico`). A área inicial é o setor atual; portal e
sistema são fontes adicionais explícitas, sem abrir o outro setor nesse domínio.

Arquivos JSONL ficam em `logs_privados/<área>` junto ao `LOG_PATH` operacional,
fora dos arquivos públicos. Limites padrão: 5 MiB por arquivo, cinco rotações,
até 30 MiB por área; consultas cobrem os últimos 30 dias ou o volume ainda
disponível, o que for menor. A auditoria de negócio no banco não recebe essa
limpeza automática. Presença e consultas de saúde repetidas são resumidas;
recusas e falhas continuam sendo registradas.

As importações automáticas mantêm o histórico e os registros da rotina já
existentes. Esta entrega não transforma scripts externos em acessos HTTP nem
oferece reconstrução retroativa de atividades. Detalhes e verificações finais
serão registrados ao concluir a integração.

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
