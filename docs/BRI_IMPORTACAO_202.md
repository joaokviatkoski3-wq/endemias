# BRI: importação e apresentação 2.0.2

Pacote **ativo em produção** em 05/11/2026, preparado na worktree
`C:\endemias-interface`, branch `codex/bri-formatos-historicos`. Usuário executou
o atalho e confirmou conclusão; release `da8a2e5`, janela iniciada às15h35.

## Problema e comportamento

A API continua sendo a entrada principal. O sistema grava os envios já
importados sem sobrescrevê-los automaticamente. Assim, corrigir o adaptador
não recompõe campos perdidos em importações antigas. Após o novo relato do
usuário, o histórico apresentado foi conferido por UUID contra o Kobo e a
exportação fornecida, e recomposto pela conferência de campos da própria
interface. Houve auditoria transacional; os demais campos foram preservados.
**Não repetir essa recomposição.** O relatório com números e evidências reais
fica local em `.venv/bri-historico/recomposicao-20261105.json`, fora do Git.

Nesta correção:

- JSON da API e XLSX emergencial usam o mesmo tratamento de campos BRI.
  Exportações com nomes técnicos, rótulos e grupos preservam data declarada,
  UUID, destino e endereço do grupo ativo, sem aproveitar campos de outro destino.
- `Quantidade_de_carga` é principal; `Quantidade_carga` é adicional. Zero é
  preservado, e ausência não vira uma carga inventada. Agregados consideram a
  parcela disponível mesmo quando a outra está nula, em BRI, produção e SisPNCD.
- Números tipados inteiros são apresentados como inteiros; textos como `007`
  e `SN` são preservados. Legado sem UUID mantém a formação anterior de suas chaves.
- A coluna **Local / endereço** mostra o estabelecimento e a rua separadamente.
  Quando só o local está cadastrado, a tela informa que o logradouro está ausente.
  Não se transforma nome de escola/CMEI em uma rua fictícia. Nome do local também
  continua disponível em detalhes, pesquisa e CSV.

A API não foi substituída por planilhas. A planilha anexada serviu de evidência;
a gravação histórica usou a conferência API, por campos escolhidos. A importação
normal conserva o comportamento de não sobrescrever registros existentes.

## Verificação

- 129 testes focados concluídos sem falhas, em71,935s: contratos BRI/Kobo,
  importação automática, conciliação, listagens/exportações, relatórios, setores
  e simulação do ativador. Inclui JSON→XLSX interno→processamento→banco fictício.
- PostgreSQL descartável confirmou os agregados com adicional nulo e as
  demais consultas/exportações dos setores. Cluster parado e credenciais removidas.
- Chromium desktop/celular confirmou local sem rua, texto literal seguro,
  detalhes, pesquisa/paginação e CSV. Revisão independente só de código/testes
  não identificou outro defeito confirmado no adaptador.
- O parser atualizado leu a exportação real somente para conferência, sem
  gravar em banco, e preservou seu SHA-256. Não versionar o arquivo nem seus dados.
- A suíte geral de1.102 testes da preparação2.0.1 é a referência anterior;
  este pacote executou a regressão proporcional acima, sem repetir toda a suíte.

## Ativação

`scripts/ativar_bri_202_windows.py`: origem2.0.1, destino2.0.2, marcador
`ativacao-bri202`. Sem DDL ou recomposição de dados pelo ativador. Backup e
parada antes de integrar; prova na identidade limitada; preservação dos dados
já recompostos, contas, configurações e entradas; retorno de código/configuração
em falha, sem restaurar banco automaticamente. Ativação aplicada/concluída;
não repetir o atalho, preparado para uma origem e um commit exatos.

- Relatório `C:\ProgramData\EndemiasWeb\ativacao-bri202-resultado.json`:96 tabelas
  e dados/arquivos preservados, incluindo a recomposição anterior; mesma tarefa,
  identidade limitada, ambiente e configurações dos dois Kobo. Prova limitada OK,
  agendamento devolvido; sem DDL ou recomposição pelo ativador.
- Portal e dois logins HTTPS200/2.0.2; logins locais5000/5004 idem; APIs anônimas401.
  Script público igual à candidata. Evidência `.venv/publicacao-202.json`.
- Conferência real autenticada da tela após ativar confirmou locais sem rua
  identificados como tal e as cargas recompostas preservadas. O relatório com
  valores reais permanece privado; nenhuma cópia do banco foi usada em testes.
- Backup PostgreSQL7.549.893 bytes/catalogado, SHA-256
  `d2698a09314d1e65b0ffb410857aa875d2326547d42a0cc7bcdbc2b97531640b`.
  Arquivo `C:\ProgramData\EndemiasWeb\ativacao-bri202-20261105-153502\antes_conta_limitada.dump`.
- Backup completo310.619.065 bytes, SHA-256
  `edd074dd9e26915c369e91d1b83da246ed12c1cd095fdbb38f31b6ef65e716f5`.
  Arquivo `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_153508.zip`.
- SQLite congelado conserva SHA-256
  `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
