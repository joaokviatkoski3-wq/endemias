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
com teto explícito de 10.000 eventos e 16 MiB. Acima dele é necessário reduzir o período
ou outros filtros; a exportação não deve omitir silenciosamente os excedentes.

O superadmin pode selecionar **Requisições e diagnóstico** na mesma página
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
oferece reconstrução retroativa de atividades. A trilha técnica fica fora do
backup completo do código/anexos quando `LOG_PATH` está no runtime privado;
para conservar um recorte por mais tempo, exporte pela tela. A auditoria SQL
continua integrando os backups do banco.

Cobertura detalhada em `docs/AUDITORIA_E_LOGS.md`, identidade em
`docs/IDENTIDADE_VISUAL_SETORES.md` e critérios da ajuda em
`docs/AJUDA_POR_AREA_E_ACESSO.md`.

## Verificações concluídas na candidata

- Logos copiados sem edição, com SHA-256 igual aos originais; Endemias mantém
  `app.css` e a marca anteriores. Chromium: 25 combinações de identidade e
  quatro retestes de contraste; cinco níveis nos dois setores para ajuda,
  incluindo troca de conta e limpeza de conteúdo anterior.
- Integração Chromium com CSRF e CSP reais: páginas dos dois setores, ajuda,
  navegação, mapas, agenda, relatórios, indicadores e as duas exportações de logs;
  sem erros JavaScript ou rolagem horizontal no celular. A última rodada ajusta
  também a apresentação dos filtros novos.
- Cluster PostgreSQL descartável na porta 55444: 11 verificações, incluindo
  auditoria/exportação/ajuda nos dois setores e regressões operacionais;
  sem usar banco ou porta oficiais. Cluster encerrado e credenciais removidas.
- Escrita concorrente por três processos: 600 registros fictícios, sem perda,
  duplicação ou JSON incompleto. Mais 14 testes focados na versão final dos logs,
  cobrindo privacidade, perfil versus gravidade, retenção/corrupção, rotação,
  permissões, exportação maior que 500 e recusa de 10.002 eventos reais de ensaio.
- Prova nativa ampliada para leitura das marcas e criação/escrita/rotação e
  remoção de arquivos temporários na pasta operacional, pela conta limitada.
  Sua execução na instalação real permanece parte da ativação elevada.

Suíte geral: 1.141 testes em 495,583 s, sem falhas e seis ignorados. Após os
ajustes finais de gravidade/perfil e metadados de versão/processo, os 14 testes
de logs passaram novamente (3,163 s). A regra de laboratório exclusivo foi
testada sem o skip provisório da frente isolada. Os avisos legados de conexões
SQLite de ensaio não fechadas continuam separados do resultado dos testes;
nenhuma correção desses avisos foi incluída neste lote. O artefato vazio `banco`
da suíte foi removido após conferir caminho, tamanho e ausência de tabelas.

SQLite congelado de produção conferido novamente, SHA-256 inalterado:
`964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
Produção continua limpa no commit `386bb447d7edbbaaee87c27068af2a49adb9a182`.

Atalho final: `Atualizar VSATT - Identidade Logs e Ajuda 2.1.0.bat`, na Área de
Trabalho, com os commits exatos fixados após o fechamento. A versão 2.1.0 só
deve ser declarada ativa após `ativacao-identidade210-resultado.json` indicar
aplicado/concluído e a conferência dos três endereços e acessos locais.

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
