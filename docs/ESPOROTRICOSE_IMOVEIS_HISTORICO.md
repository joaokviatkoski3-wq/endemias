# Histórico de imóveis — Esporotricose

## Finalidade

Uma visita importada do Kobo continua sendo um registro próprio. Quando duas ou
mais visitas se referem ao mesmo imóvel, elas podem ser vinculadas a uma única
entidade de **imóvel acompanhado**, que reúne a linha do tempo de visitas,
tutores/telefones informados e animais cadastrados em cada visita.

Não há exclusão nem fusão de visitas, animais ou dados do Kobo.

## Chave de endereço

O vínculo automático exige todos estes dados:

- localidade resolvida no cadastro local;
- quarteirão;
- logradouro;
- número do imóvel.

Para comparação, acentos, maiúsculas/minúsculas e as abreviações `R.`/`Rua` e
`Av.`/`Avenida` não impedem a coincidência. Os valores originais permanecem
inalterados na visita.

Ao importar uma nova visita com endereço completo, o sistema cria ou reutiliza
o imóvel correspondente. Visitas históricas são vinculadas somente pela ação
administrativa **Vincular correspondências exatas**, sempre após uma prévia.

## Revisão humana

Em **Esporotricose > Visitas > Histórico por imóvel**, administradores podem:

1. gerar uma prévia sem gravar dados;
2. vincular os endereços completos e exatos;
3. analisar sugestões parecidas e confirmar manualmente quais visitas são do
   mesmo imóvel.

Sugestões nunca vinculam dados por conta própria. Uma visita já associada a
outro imóvel não é movida silenciosamente. O vínculo manual é auditado.

Nomes iguais de tutor ou animal são apenas apresentados no histórico: não
identificam automaticamente a mesma pessoa ou o mesmo animal.

## Estrutura e implantação

- `esporotricose_imoveis`: chave de endereço e metadados do imóvel acompanhado.
- `esporotricose_visita_imoveis`: relação de cada visita com um imóvel e origem
  do vínculo (`automatico` ou `manual`).

A migração PostgreSQL `0014_esporotricose_imoveis_historico.sql` deve ser
aplicada antes de reiniciar a produção. A migração não vincula registros nem
altera dados existentes; a primeira vinculação histórica é uma ação explícita
na interface.
