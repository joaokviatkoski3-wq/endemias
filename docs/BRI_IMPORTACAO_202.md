# BRI: importação e apresentação 2.0.2

Pacote validado em 05/11/2026, worktree `C:\endemias-interface`, branch
`codex/bri-formatos-historicos`. Produção ainda em 2.0.1 até a ativação.

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
em falha, sem restaurar banco automaticamente. Ativação administrativa pendente.
