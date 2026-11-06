# Identidade dos setores, logs e ajuda — 2.1.0

## Situação operacional

Preparação autorizada em 05/11/2026. Usuário executou o atalho elevado e
confirmou conclusão. Relato histórico da implantação **2.1.0**, release
`db3f1cbc624aa85b83cabc77122c7777c67683ea`, janela16h28. Relatório nativo
`C:\ProgramData\EndemiasWeb\ativacao-identidade210-resultado.json`
aplicado/concluído;96 tabelas/dados/arquivos preservados, sem DDL ou restauração
de banco. Mesma tarefa/identidade/ambiente, duas configurações Kobo, SQLite
congelado e agendamento devolvido. Não repetir atalho, ativadores antigos ou
recomposição histórica de BRI.

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
  Na instalação real a prova passou, conforme relatório nativo.

Suíte geral: 1.141 testes em 495,583 s, sem falhas e seis ignorados. Após os
ajustes finais de gravidade/perfil e metadados de versão/processo, os 14 testes
de logs passaram novamente (3,163 s). A regra de laboratório exclusivo foi
testada sem o skip provisório da frente isolada. Os avisos legados de conexões
SQLite de ensaio não fechadas continuam separados do resultado dos testes;
nenhuma correção desses avisos foi incluída neste lote. O artefato vazio `banco`
da suíte foi removido após conferir caminho, tamanho e ausência de tabelas.

SQLite congelado de produção conferido novamente, SHA-256 inalterado:
`964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
Origem preservada pelo atualizador: commit
`386bb447d7edbbaaee87c27068af2a49adb9a182`; código ativo na release acima.

Atalho final: `Atualizar VSATT - Identidade Logs e Ajuda 2.1.0.bat`, na Área de
Trabalho, com os commits exatos fixados após o fechamento. Já aplicado.

## Conferência após ativação

Quinze checagens em `.venv/publicacao-210.json`: portal, dois logins HTTPS e
locais5000/5004 retornam200/2.1.0, com cache privado/no-store e ID de requisição
válido; portal sem cookie. Ajuda e dashboard sem sessão retornam401 nos dois
domínios. Dois logos novos, logo de Endemias, CSS Ambiental/Portal e script da
ajuda publicados iguais byte a byte à fonte. Não houve login com contas reais
ou escrita operacional nesta conferência.

Prova nativa confirmou escrita/rotação, existência dos arquivos e ausência de
falhas nos escritores dos três aplicativos. A conta interativa não pôde ler
nem consultar atributos dos arquivos JSONL privados, conforme proteção ACL;
seu conteúdo não foi inspecionado novamente e permissões não foram alteradas.
O acesso operacional aos registros ocorre pela tela autenticada, segundo o
perfil; a matriz de permissões e exportações foi verificada na homologação.

Backups registrados antes da troca:

- SQL: `C:\ProgramData\EndemiasWeb\ativacao-identidade210-20261105-162820\antes_conta_limitada.dump`,
  7.549.800 bytes; catálogo validado pelo instalador;
  SHA-256 `6e0ca6674f0dd929208df765fb116f4822925f4e89e78aebd93814398e77e675`.
- Completo: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_162827.zip`,
  310.618.983 bytes;
  SHA-256 `b62852d5c4f941773b247e2528de4ab9b5b8ee0e7141fa186ad3efda55cf364f`.

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
