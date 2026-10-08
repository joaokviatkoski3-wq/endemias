# Planilhas dos RGs selecionados

Implementado em 08/10/2026, versão de código `1.68.0`. Não exige migração.

## Uso

Em **Territorialização > Boletim de Registro de Reconhecimento Geográfico
Digital > Impressão e planilhas**, escolha uma localidade, marque um ou mais
quarteirões e clique em **Baixar planilha .xlsx**. Também é possível selecionar
todos os RGs da localidade. O botão **Abrir impressão** continua disponível para
impressão ou geração de PDF pelo navegador.

## Conteúdo

O arquivo `rgs_selecionados.xlsx` contém somente uma aba, **RGs**, com cabeçalho
na primeira linha e uma linha por registro do RG. Colunas:

- Localidade e quarteirão;
- Logradouro, número, sequência e lado;
- Tipo, condomínio (unidades) e observação;
- Data de atualização e agentes registrados **em cada imóvel**.

Todos os registros dos RGs escolhidos são incluídos, sem paginação, preservando
a ordem cadastrada, inclusive referências `REF`. Não há mapas, totais,
estimativas populacionais, IDs internos, metadados de importação ou abas extras.
Um RG sem imóveis aparece com localidade e quarteirão e os demais campos vazios.

Identificadores e textos permanecem como texto literal, inclusive `SN`, zeros à
esquerda e quarteirões decimais. Quantidades são numéricas; datas ISO válidas são
datas Excel exibidas como `dd/mm/aaaa`. Campos vazios permanecem vazios. Valores
com aparência de fórmula são texto e não executam fórmulas ao abrir o arquivo.
Cabeçalho congelado, colunas de identificação fixas e filtros facilitam a leitura.
Não há cores, logotipos, células mescladas ou decoração.

## Implementação e validação

- `GET /registro-geografico/exportar.xlsx?localidade=...&quarteirao=...`
  aceita vários parâmetros `quarteirao`, exige sessão ativa e mantém o mesmo
  acesso de leitura da impressão, inclusive visualizadores.
- A seleção é obrigatória; quarteirões desconhecidos ou de outra localidade
  rejeitam o pedido inteiro. Seleções repetidas não duplicam os registros.
- Reutiliza a consulta do RG usada pela impressão. Não edita registros,
  geometrias, contagens, regras de condomínio ou sorteios LIRAa.
- O download mostra erros na própria tela e reabilita o botão após falhas;
  uma sessão expirada não vira um arquivo HTML com extensão XLSX.
- Testes em `tests/test_registro_geografico_exportacao.py` e `.js` cobrem
  seleção simples/múltipla, tipos, conteúdo, RG vazio, autenticação, erros,
  sessão expirada e preservação das opções de impressão.

A exportação usa a biblioteca XLSX já instalada no sistema, sem adicionar
dependências ao servidor. Integrada na `master` no commit `c726f56` e ativada
após autorização e reinício em 08/10/2026 às 10h18 (America/Sao_Paulo).
`/login` confirmou HTTP 200 com `Endemias v1.68.0`. O estado de produção
fica registrado em `ESTADO_ATUAL_PROJETO.md`.

Validação em 08/10/2026: suíte completa com 794 testes (5 ignorados), seguida
de 19 testes focados finais e dos 7 arquivos de testes JavaScript. Inclui um
teste adicional com 650 imóveis para descartar truncamento pela paginação.
Arquivo sintético gerado pela função da aplicação reaberto e renderizado;
tipos, datas, zeros à esquerda e ausência de fórmulas verificados por reabertura.
Página autenticada e login renderizados com `Endemias v1.68.0` em Flask isolado.

Na implantação, uma consulta PostgreSQL somente leitura gerou em memória um
XLSX de 2 RGs, 232 linhas e 11 colunas; seleção, tipos e ausência de fórmulas
foram conferidos por reabertura. Não foi salvo arquivo com dados reais.
Contagens das 91 tabelas e 19 assinaturas territoriais/LIRAa permaneceram iguais
antes/depois da integração; nenhuma migração ou escrita de dados foi feita.
