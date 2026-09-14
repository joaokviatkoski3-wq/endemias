# Exportacao XLSX do Monitoramento de Ovitrampas

Atualizado em 14/09/2026.

## Estado implementado

Na versao `1.37.0`, a aba **Monitoramento** da pagina `/ovitrampas` ganhou o
botao **Exportar .xlsx**. A versao `1.38.0` acrescentou filtros multiplos em
cascata. O download usa os mesmos parametros enviados por **Aplicar filtros**:

- ano, semana inicial e semana final;
- data inicial e data final;
- ultimas semanas quando nenhum periodo explicito foi informado;
- uma ou varias localidades;
- uma ou varias ovitrampas exatas dentre as cadastradas nas localidades
  selecionadas;
- minimo de leituras, IPO, IDO e IMO e ordenacao do ranking.

Os filtros de periodo, localidades e IDs limitam as leituras e agregacoes. Os
limites do ranking nao apagam dados brutos: a aba **Armadilhas** informa se cada
linha atende ou nao a esses limites.

Na interface, o seletor de ovitrampas e atualizado quando as localidades mudam.
Ele mostra ID, localidade e endereco do cadastro local e permite pesquisar ou
selecionar todas as opcoes visiveis. Deixar um dos seletores sem marcacao
significa incluir todas as opcoes daquele nivel. As selecoes multiplas sao
enviadas como parametros repetidos `localidade` e `ovitrampa_id`, evitando
separadores ambiguos nos nomes e identificadores.

## Abas geradas

1. **Resumo**: filtros efetivamente aplicados, totais, IPO, IDO, IMO, cobertura
   dos cadastros e regras das fontes.
2. **Leituras**: uma linha por contagem do espelho GET do Conta Ovos, sem o
   limite de 80 registros usado em algumas tabelas da interface. Inclui dados da
   contagem, cadastro local, cadastro remoto e o lote de laboratorio associado.
3. **Armadilhas**: uma linha por ID encontrado no cadastro local, no espelho do
   cadastro remoto ou nas leituras. Inclui armadilhas sem leitura no periodo,
   com indicadores zerados, para permitir auditoria de cobertura.
4. **Semanas**: leituras, armadilhas lidas, positivas, ovos, IPO, IDO e IMO por
   semana.
5. **Localidades**: os mesmos indicadores agregados por localidade.
6. **Ocorrencias**: todos os lancamentos de ocorrencia do laboratorio que
   encontram a respectiva contagem por ovitrampa e data de coleta.

Todas as abas de dados possuem cabecalho fixo, autofiltro e valores tipados para
datas e numeros. Textos iniciados por caracteres de formula sao protegidos para
nao executar formulas ao abrir o arquivo no Excel.

## Fontes e limites

- leituras e resultados: `ovitrampas_ocorrencias_conta_ovos`;
- endereco, responsavel, telefone e situacao: `ovitrampas_armadilhas`;
- identificadores e coordenadas remotas:
  `contaovos_registro_ovitrampas`;
- laboratorista, diario e ocorrencia: `ovitrampas_laboratorio_lotes` e
  `ovitrampas_laboratorio_itens`.

A exportacao e um retrato dos espelhos locais no momento do download. Ela nao
consulta, altera nem envia dados ao Conta Ovos. Para obter dados remotos mais
recentes, o administrador deve executar antes a sincronizacao GET existente na
pagina Ovitrampas.

O endereco detalhado vem do cadastro local porque o endpoint publico usado no
espelho remoto nao fornece todos os campos cadastrais. Quando a mesma ovitrampa
possui mais de um lote de laboratorio na mesma data, a aba **Leituras** conserva
uma linha por contagem e associa o lote concluido/enviado mais recente; a aba
**Ocorrencias** preserva todos os lancamentos encontrados.
