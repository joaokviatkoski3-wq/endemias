# Camada dual SQLite e PostgreSQL

## Estado em 29/07/2026

A aplicacao possui agora uma primeira camada de conexao capaz de consultar
SQLite ou PostgreSQL sem alterar a assinatura usada pelo codigo existente.

O SQLite continua sendo o banco padrao e o `iniciar.bat` nao foi alterado.
O modo PostgreSQL ainda e experimental e nao deve ser usado como servidor
operacional.

## O que foi implementado

- destino de banco explicito e imutavel, contendo tipo e local;
- selecao por `DB_BACKEND`, mantendo `sqlite` como padrao;
- conexao PostgreSQL por meio da configuracao libpq e do `pgpass.conf`;
- adaptadores para `conn.execute`, `cursor.execute`, `fetchone`, `fetchall`,
  `fetchmany`, `executemany`, transacoes e context managers;
- linhas PostgreSQL acessiveis tanto por indice quanto pelo nome da coluna;
- conversao segura dos placeholders `?` atuais para `%s`;
- preservacao de `?` existentes dentro de textos, identificadores e
  comentarios SQL;
- helpers comuns, autenticacao de leitura e dados globais da interface usando
  o destino configurado;
- persistencia das tentativas de login e eventos de auditoria;
- filtros portaveis por data no historico de auditoria;
- manutencao dessas tabelas em tempo de execucao restrita ao SQLite, pois no
  PostgreSQL elas sao controladas pelas migracoes;
- inicializacoes exclusivas do SQLite executadas apenas quando o destino e
  SQLite.

Operacoes antigas que recebem apenas um caminho de arquivo continuam abrindo
SQLite. Isso preserva o comportamento atual e os testes existentes.

## Validacao real

O comando abaixo executa somente leituras em `endemias_teste`:

```powershell
python scripts\testar_app_postgresql.py --database endemias_teste
```

Resultado validado:

| Verificacao | Resultado |
| --- | ---: |
| Tabelas publicas encontradas | `60` |
| Consulta com parametros | `OK` |
| Linhas retornadas por nome | `OK` |
| Tela de login Flask | `HTTP 200` |

O teste usa a propria factory Flask, os helpers compartilhados e o adaptador
PostgreSQL. Nenhuma linha e inserida, atualizada ou removida.

As escritas de autenticacao e auditoria sao validadas com:

```powershell
python scripts\testar_auth_postgresql.py --database endemias_teste
```

Esse teste cria tabelas temporarias com os mesmos contratos das tabelas
publicas, valida:

- gravacao, leitura, contagem e limpeza das tentativas de login;
- gravacao do evento de auditoria;
- serializacao e leitura dos detalhes JSON;
- filtros de acao e intervalo de datas;
- preservacao das contagens das tabelas publicas.

As tabelas temporarias existem apenas na conexao do teste e sao descartadas
automaticamente ao final.

## Controle de Pessoal

O primeiro modulo funcional completo migrado foi o **Controle de Pessoal**.
Estao compativeis com os dois bancos:

- listagem e filtros por situacao;
- busca por nome, nome completo, matricula e CPF;
- busca sem diferenca entre letras maiusculas e minusculas;
- cadastro com recuperacao segura do novo ID;
- consulta individual e edicao dos campos permitidos;
- normalizacao e criacao de servidores vindos das importacoes;
- CPF, data de nascimento e nome completo;
- historico consolidado das frentes de trabalho;
- renderizacao da pagina administrativa.

No PostgreSQL, a tabela `agentes` e administrada exclusivamente pelas
migracoes. O SQLite preserva a manutencao de compatibilidade usada pelos bancos
antigos.

O teste controlado e executado com:

```powershell
python scripts\testar_servidores_postgresql.py --database endemias_teste
```

Resultado da homologacao:

| Verificacao | Resultado |
| --- | ---: |
| CRUD em tabela temporaria | `OK` |
| Busca sem diferenca de caixa | `OK` |
| Eventos lidos no historico real | `2.868` |
| Origens presentes no historico | `8` |
| Pagina Controle de Pessoal | `HTTP 200` |
| Tabela publica `agentes` | Preservada |

O teste de pagina usa um administrador existente somente para estabelecer a
sessao. Nenhuma senha e lida e nenhum dado publico e alterado.

## Gestao de Usuarios

A pagina **Gestao de Usuarios** e seu nucleo de regras foram migrados. Estao
validados:

- listagem das contas;
- criacao com identidade retornada pelo banco;
- normalizacao do login;
- hash de senha;
- niveis de acesso;
- permissoes de laboratorio e acesso exclusivo;
- bloqueio da desativacao da propria conta;
- redefinicao de senha;
- renderizacao da pagina administrativa.

O ensaio usa uma tabela `usuarios` temporaria:

```powershell
python scripts\testar_usuarios_postgresql.py --database endemias_teste
```

Resultado: CRUD, permissoes, protecao da conta, senha e pagina Flask validados.
A tabela publica `usuarios` permaneceu inalterada.

## Historico de Importacoes

O registro tecnico das importacoes tambem foi convertido:

- `INSERT OR REPLACE` foi substituido por `ON CONFLICT`;
- usuario e data de criacao originais sao preservados no reprocessamento;
- arquivos e estado da nova tentativa sao atualizados;
- campos de resultado anterior sao limpos antes do novo processamento;
- a ordenacao usa diretamente as datas ISO, sem `datetime()` do SQLite;
- a criacao de tabela em tempo de execucao fica restrita ao SQLite.

O teste isolado e:

```powershell
python scripts\testar_importacoes_postgresql.py --database endemias_teste
```

Ele valida registro, reprocessamento, atualizacao, JSON e listagem em uma
tabela temporaria.

## Importacao Kobo

A pagina **Importacao Kobo** e o ETL principal foram homologados nos dois
bancos. A cobertura inclui:

- uso do destino de banco configurado nas previas, pendencias, processamento
  e historico;
- criacao de localidades com `RETURNING` no PostgreSQL;
- agregacao portavel dos agentes e ordenacao por datas nativas;
- insercoes idempotentes de depositos, tratamentos, coletas e resultados;
- comparacao uniforme de datas e horarios em reimportacoes;
- simulacao e confirmacao protegidas por uma unica transacao;
- rollback integral do lote quando uma operacao PostgreSQL falha;
- importacao isolada de resultados de larvas, criacao de focos e encerramento
  da pendencia do tubo;
- backup pre-importacao preservado no SQLite e protecao transacional no
  PostgreSQL;
- renderizacao da pagina e leitura da configuracao Kobo.

O ensaio controlado e:

```powershell
python scripts\testar_importacao_kobo_postgresql.py --database endemias_teste
```

Ele cria copias temporarias das tabelas operacionais, gera uma planilha Kobo
sintetica, executa dry-run, confirmacao e reimportacao e processa um resultado
laboratorial. Ao final, compara as tabelas publicas para garantir que nenhum
dado real foi alterado.

## Agenda, Pagina Inicial e Meteorologia

O conjunto formado pela **Agenda**, **Pagina Inicial** e **Meteorologia** foi
homologado nos dois bancos. A cobertura inclui:

- eventos manuais, recorrencias, edicao, exclusao, impressao e lembretes;
- eventos automaticos de visitas, BRI, Esporotricose, recolhimentos, amostras,
  acoes do setor, aniversarios e Ovitrampas;
- agregacao portavel de localidades e agentes;
- tratamento uniforme das colunas `DATE` retornadas pelo PostgreSQL;
- sincronizacao idempotente dos dados INMET e Open-Meteo;
- gravacao das estacoes, resumos, condicao atual e previsoes horarias;
- configuracao dos limites de chuva, vento, frio e calor;
- classificacao do risco meteorologico no horario de trabalho;
- cards, atividade recente, Agenda, clima e blocos administrativos da Pagina
  Inicial;
- recuperacao de identidades por `RETURNING` no PostgreSQL;
- manutencao de esquema em tempo de execucao restrita ao SQLite.

O ensaio controlado e:

```powershell
python scripts\testar_agenda_home_postgresql.py --database endemias_teste
```

O script sincroniza dados meteorologicos sinteticos duas vezes, exercita o
CRUD da Agenda pelas APIs reais, abre as tres paginas em modo PostgreSQL e
compara as tabelas publicas antes e depois. Todas as escritas acontecem em
tabelas temporarias.

## Recolhimentos e Amostras de Animais

Os modulos **Recolhimentos de Materiais** e **Amostras de Animais** foram
homologados nos dois bancos. A conversao inclui:

- conexoes abertas pelo destino configurado da aplicacao;
- consultas de resumo, listagem e opcoes de filtro;
- busca textual sem diferenca entre maiusculas e minusculas;
- agregacao dos agentes com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL;
- insercao idempotente com `ON CONFLICT DO NOTHING`;
- criacao de localidades com `RETURNING` no PostgreSQL;
- agrupamento mensal compativel com colunas `DATE`;
- serializacao uniforme de datas e horarios nas APIs;
- criacao e manutencao de esquema em tempo de execucao restritas ao SQLite.

O ensaio controlado e executado com:

```powershell
python scripts\testar_campo_operacional_postgresql.py --database endemias_teste
```

O teste usa tabelas temporarias para validar insercao, deduplicacao, agentes,
filtros e resumos. Tambem renderiza as duas paginas e consulta suas quatro APIs
contra os dados publicos em modo somente leitura. As tabelas publicas
permanecem inalteradas.

## BRI e Pontos Estrategicos

Os modulos **BRI** e **Pontos Estrategicos** foram convertidos no mesmo lote
para preservar o vinculo entre tratamentos, visitas e o cadastro mestre de PE.
Estao homologados:

- cadastro, edicao, consulta e alteracao de situacao dos PEs;
- geracao e resolucao dos aliases de logradouro;
- vinculacao retroativa de visitas PE por alias;
- insercao e deduplicacao dos registros BRI;
- vinculacao direta do BRI ao PE correspondente;
- filtros e buscas sem diferenca entre maiusculas e minusculas;
- resumos de visitas, BRI e focos por PE;
- calculo de atraso com datas nativas dos dois bancos;
- serializacao uniforme de datas e horarios;
- paginas e APIs dos dois modulos.

O ensaio controlado e:

```powershell
python scripts\testar_bri_pe_postgresql.py --database endemias_teste
```

O script cria copias temporarias das oito tabelas envolvidas, valida todo o
fluxo integrado e depois consulta as paginas reais em modo somente leitura.
As contagens das tabelas publicas sao comparadas antes e depois do ensaio.

## Visitas de Arboviroses

A pagina **Visitas de Arboviroses** teve seu nucleo de consulta e edicao
convertido para a camada dual. Estao homologados:

- opcoes de filtro e busca textual sem diferenca entre maiusculas e
  minusculas;
- ordenacao, paginacao e resumo dos registros filtrados;
- agregacao de agentes e numeros de tubos;
- situacao laboratorial das coletas;
- detalhe completo de depositos, tratamentos, coletas e focos;
- edicao da visita, localidade, agentes, depositos, tratamentos e coletas;
- sincronizacao do numero do tubo com resultados e focos;
- protecao e rollback ao tentar remover uma coleta que ja possui resultado;
- serializacao uniforme de datas e horarios nas APIs;
- auditoria da edicao pela rota Flask.

O ensaio controlado e:

```powershell
python scripts\testar_visitas_postgresql.py --database endemias_teste
```

O script valida leitura e escrita em nove tabelas temporarias e consulta a
pagina, a listagem e o detalhe reais em modo somente leitura. As contagens das
tabelas publicas sao verificadas antes e depois. O **Dashboard Integrado** e a
consulta geral de **Resultados Laboratoriais** foram tratados no lote
seguinte, descrito abaixo.

## Dashboard Integrado e Resultados Laboratoriais

O **Dashboard Integrado**, a API de **Producao Operacional** e a consulta geral
de **Resultados Laboratoriais** foram homologados nos dois bancos. O lote
inclui:

- indicadores vetoriais, evolucao semanal e mensal;
- distribuicoes por tipo, localidade, situacao, servidor e tipo de imovel;
- depositos inspecionados, eliminados e tratados;
- duracao das visitas TBO nos dialetos de data e hora de cada banco;
- resumos de Esporotricose, Pontos Estrategicos e Producao Operacional;
- leituras e calendario de Ovitrampas no painel integrado;
- comparativo mensal entre vetores, Esporotricose e Ovitrampas;
- filtros, paginacao, totais, especies e series da consulta laboratorial;
- agregacao de servidores com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL;
- serializacao uniforme de datas, horarios e valores decimais.

O refatoramento tambem corrigiu a multiplicacao silenciosa de visitas,
depositos e resultados quando um registro possuia mais de um servidor
vinculado.

O ensaio controlado e:

```powershell
python scripts\testar_dashboard_laboratorio_postgresql.py `
  --database endemias_teste
```

Ele valida um cenario temporario com dois servidores, consulta o Dashboard
integrado e as APIs reais em modo somente leitura e compara as contagens das
`60` tabelas publicas antes e depois.

## Visitas de Esporotricose

O bloco operacional importado do Kobo na pagina **Esporotricose** foi
homologado nos dois bancos. Estao compativeis:

- resumo das visitas e dos animais encontrados;
- filtros por periodo, localidade, situacao, servidor e busca textual;
- busca textual por datas e numeros de quarteirao;
- listagem detalhada das visitas e dos animais;
- agregacao de servidores sem multiplicar os animais da visita;
- edicao dos dados da visita e do animal;
- resumos por localidade e series do painel;
- registro de multiplas buscas de animais feridos;
- exibicao das buscas nos detalhes do animal e integracao com a Agenda;
- serializacao uniforme de datas e horarios nas APIs.

O ensaio controlado e:

```powershell
python scripts\testar_esporotricose_visitas_postgresql.py `
  --database endemias_teste
```

O script valida leitura e escrita em sete tabelas temporarias, consulta a
pagina e as APIs reais somente em leitura e compara todas as contagens
publicas antes e depois.

## Cadastro Clinico de Esporotricose

O cadastro manual de animais doentes tambem foi homologado nos dois bancos.
O recorte inclui:

- cadastro, consulta, edicao e exclusao de animais doentes;
- vinculo opcional com animais encontrados nas visitas do Kobo;
- filtros, resumos, indicadores e exportacao CSV;
- status, data de notificacao, CPF e dados operacionais;
- cadastro, edicao e exclusao de receitas e entregas;
- posologia, capsulas entregues, faltantes, excedentes e proxima entrega;
- baixa no Zoomed e total de capsulas baixadas;
- estoque manual e saidas automaticas geradas pelas entregas;
- edicao das observacoes das saidas automaticas;
- metadados, consulta e exclusao dos anexos;
- recuperacao de identidades com `lastrowid` no SQLite e `RETURNING` no
  PostgreSQL;
- serializacao uniforme de datas e valores numericos.

Os PDFs e suas miniaturas continuam armazenados na pasta de anexos. O banco
guarda apenas os metadados e vinculos, como ja ocorria no SQLite.

O ensaio controlado e:

```powershell
python scripts\testar_esporotricose_clinica_postgresql.py `
  --database endemias_teste
```

O script exercita o fluxo completo em nove tabelas temporarias, consulta as
paginas e APIs reais somente em leitura e confirma que as tabelas publicas
permaneceram inalteradas.

Com isso, a pagina **Esporotricose** esta funcionalmente coberta pela camada
dual.

## Ovitrampas

A pagina **Ovitrampas** foi homologada nos dois bancos. O recorte inclui:

- cadastro local e importacao do cadastro de armadilhas;
- importacao idempotente das leituras e ocorrencias do Conta Ovos;
- resumo, listagem, filtros e edicao individual ou em lote das leituras;
- indicadores, ranking, positivas recentes e monitoramento por localidade;
- ocorrencias historicas e armadilhas marcadas para realocacao;
- busca sem diferenca entre maiusculas e minusculas;
- IDs numericos e alfanumericos, como `126-A`, sem erro de conversao;
- historico das alteracoes de endereco, quarteirao e demais dados;
- criacao e edicao dos diarios;
- vinculo, remocao, movimentacao e reordenacao das armadilhas;
- identificacao de armadilhas a realocar e sem diario;
- grupos, eventos e agentes do calendario;
- integracao dos movimentos com a Agenda;
- geracao dos lotes de leitura a partir do calendario e dos diarios;
- rascunho e conclusao das contagens pelo laboratorista;
- registro das ocorrencias de campo junto com a quantidade de ovos;
- conferencia administrativa e marcacao do envio ao Conta Ovos;
- tela compartilhada de lancamentos laboratoriais em modo PostgreSQL;
- agregacao de agentes com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL;
- recuperacao de IDs com `lastrowid` no SQLite e `RETURNING` no PostgreSQL;
- serializacao uniforme das datas do calendario.

O ensaio controlado e:

```powershell
python scripts\testar_ovitrampas_postgresql.py `
  --database endemias_teste
```

O script exercita cadastro, historico, leituras, ocorrencias, monitoramento,
diarios, ordenacao, calendario e laboratorio em onze tabelas temporarias. Ele
tambem abre as paginas e APIs reais em modo somente leitura. Ao final, compara
as contagens de todas as tabelas publicas para confirmar que a copia de
homologacao nao foi alterada.

## Conta Ovos e SisPNCD

O espelho operacional **Conta Ovos e SisPNCD** foi homologado nos dois bancos.
O recorte inclui:

- selecao automatica do grupo TBO pendente mais recente;
- resumo das pendencias do Conta Ovos e do SisPNCD;
- agrupamento SisPNCD por semana epidemiologica, tipo e localidade;
- classificacao dos tipos de imovel e dos depositos;
- imoveis inspecionados e tratados somente com carga real;
- consolidacao de tratamentos, agentes, dias e quarteiroes;
- resultados laboratoriais e quarteiroes positivos por especie;
- inclusao dos registros BRI;
- baixa dos grupos enviados ao Conta Ovos;
- gravacao do codigo SisPNCD sem sobrescrever codigos existentes;
- suporte central a consultas parametrizadas que contenham padroes `LIKE`;
- serializacao uniforme de datas e valores decimais.

O ensaio controlado e:

```powershell
python scripts\testar_conta_ovos_sispncd_postgresql.py `
  --database endemias_teste
```

O script valida leitura e escrita em oito tabelas temporarias, abre a pagina e
as APIs reais em modo somente leitura e confirma que as contagens das tabelas
publicas permanecem inalteradas.

## Registro Geografico

A pagina **Registro Geografico** foi homologada nos dois bancos. O recorte
inclui:

- cadastro, consulta, edicao e exclusao individual de imoveis;
- criacao, edicao, mudanca de localidade ou numero, limpeza e exclusao de
  quarteiroes;
- vinculo dos servidores de campo e autoria do usuario que atualizou o
  quarteirao no sistema;
- filtros, totais, acompanhamento de atualizacoes e resumo para o mapa;
- tipos de imovel, condominios e estimativa populacional;
- sugestoes e deteccao de logradouros semelhantes;
- previa e aplicacao da edicao em lotes;
- suporte a quarteiroes numericos, decimais e alfanumericos na ordenacao;
- agregacao de servidores com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL;
- recuperacao de identidades com `lastrowid` no SQLite e `RETURNING` no
  PostgreSQL;
- serializacao uniforme de datas e valores numericos;
- manutencao de esquema e importacao inicial por CSV restritas ao SQLite.

Durante a homologacao, tambem foi eliminada uma possibilidade de colisao na
chave de origem de linhas manuais criadas no mesmo segundo.

O ensaio controlado e:

```powershell
python scripts\testar_registro_geografico_postgresql.py `
  --database endemias_teste
```

O script exercita leitura e escrita em cinco tabelas temporarias, incluindo
edicao individual e em lote, mudanca, limpeza e exclusao de quarteiroes.
Depois abre a pagina e as APIs reais somente em leitura e confirma que as
tabelas publicas permaneceram inalteradas.

## Acoes e Atendimentos do Setor

A pagina **Acoes e Atendimentos do Setor** foi homologada nos dois bancos. O
recorte inclui:

- cadastro, consulta, edicao, filtros e exclusao dos registros;
- intervalos de datas, situacoes, casos e busca sem acentos;
- vinculo de multiplos servidores sem duplicacao;
- anexos publicos e restritos, galeria, visualizacao e downloads individuais;
- geracao de ZIP e relatorio tecnico com imagens;
- permissoes de administrador, operador e visualizador;
- auditoria atomica de criacao, edicao, exclusao e alteracoes nos anexos;
- agregacao de servidores com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL;
- insercao idempotente dos vinculos com `ON CONFLICT DO NOTHING`;
- recuperacao das identidades de acoes e anexos pelo helper portavel;
- comparacao direta das datas ISO, sem funcoes exclusivas do SQLite;
- manutencao de esquema em tempo de execucao restrita ao SQLite;
- validacao previa dos arquivos e remocao dos caminhos gravados se a transacao
  de metadados falhar.

O ensaio controlado e:

```powershell
python scripts\testar_acoes_setor_postgresql.py `
  --database endemias_teste
```

O script exercita pagina, CRUD, filtros, servidores, anexos, galeria, ZIP,
download, relatorio, permissoes e auditoria em seis tabelas temporarias. Ao
final, confirma que as contagens das `60` tabelas publicas permaneceram
inalteradas. A regressao ampla do lote teve `399` testes aprovados e `5`
ignorados.

## Boletim Mensal

O **Boletim Mensal** foi homologado nos dois bancos. O recorte inclui:

- indicadores automaticos de visitas PVE, TB, TBO e PE;
- depositos inspecionados e eliminados, coletas e focos positivos;
- visitas e animais de Esporotricose;
- recolhimentos, pneus, BRI, amostras de animais e Acoes do Setor;
- ajustes dos indicadores automaticos e inclusao de linhas manuais;
- ordem, unidade, ativacao e total do fechamento mensal;
- pagina, relatorio para PDF e exportacao XLSX;
- permissao de leitura para visualizador e edicao a partir de operador;
- auditoria gravada na mesma transacao do fechamento;
- conflitos transitorios de escrita tratados com resposta para nova tentativa;
- manutencao de esquema em tempo de execucao restrita ao SQLite;
- deteccao de tabelas pelo helper compativel com ambos os bancos.

O ensaio controlado e:

```powershell
python scripts\testar_boletim_mensal_postgresql.py `
  --database endemias_teste
```

O script exercita todas as fontes operacionais, ajustes, linhas manuais, PDF,
XLSX, permissoes e auditoria em treze tabelas temporarias. Ao final, confirma
que as contagens das `60` tabelas publicas permaneceram inalteradas. A
regressao ampla do lote teve `407` testes aprovados e `5` ignorados.

## Mapa, Notificacoes e Relatorio por Servidor

Os tres modulos foram homologados nos dois bancos. O recorte inclui:

- Mapa geral com visitas, focos, Esporotricose, Pontos Estrategicos e
  Ovitrampas;
- calculo de PE atrasado sem funcoes de data exclusivas do SQLite;
- filtros case-insensitive, `HAVING` e ordenacao alfanumerica portaveis;
- serializacao uniforme de datas nativas, intervalos e valores decimais;
- pagina, filtros, detalhe, historico e impressoes de Notificacoes;
- atualizacao e auditoria de Notificacoes na mesma transacao;
- resposta para nova tentativa em conflitos transitorios de escrita;
- Relatorio por Servidor e consolidado do setor;
- duracoes com `julianday` no SQLite e intervalos no PostgreSQL;
- evolucao semanal, producao operacional, laboratorio, Esporotricose,
  Ovitrampas e Registro Geografico;
- agregacoes distintas com `GROUP_CONCAT` no SQLite e `string_agg` no
  PostgreSQL.

O ensaio controlado e:

```powershell
python scripts\testar_mapa_notificacoes_relatorio_postgresql.py `
  --database endemias_teste
```

O script cria tabelas temporarias para todo o esquema, abre paginas e APIs
reais, grava apenas nas tabelas temporarias de Notificacoes e compara as
contagens publicas antes e depois. As `60` tabelas publicas permaneceram
inalteradas. A regressao ampla teve `419` testes aprovados e `5` ignorados.

## Exportacoes, Consolidados e Central do Sistema

As exportacoes XLSX de visitas, notificacoes e laboratorio e os consolidados
PE, TB, TBO e PVE usam agora o destino configurado na camada dual. Agregacoes
ordenadas usam `GROUP_CONCAT` no SQLite e `string_agg` no PostgreSQL, buscas
textuais preservam a comparacao sem diferenciar caixa e os agrupamentos foram
ajustados para as regras estritas do PostgreSQL.

A Central identifica o backend ativo, exibe status, tamanho, tabelas e indices
PostgreSQL e executa o diagnostico rapido ou completo sem `PRAGMA`. Backup e
backup completo usam `pg_dump` em formato custom, publicam o arquivo somente
depois de `pg_restore --list` e registram SHA-256. A restauracao exige a
confirmacao digitada do banco, cria um dump `pre_restore` e executa
`pg_restore` com limpeza, parada no primeiro erro e transacao unica. Senhas nao
entram nos argumentos nem nos metadados. O DBML continua SQLite-only.

O ensaio controlado e:

```powershell
python scripts\testar_exportacoes_admin_postgresql.py `
  --database endemias_teste
```

O script cria sombras temporarias das tabelas, confere valores reais nas tres
planilhas, gera um consolidado PE, abre a Central e o diagnostico completo e
gera um dump PostgreSQL real em pasta temporaria, validado por `pg_restore
--list`. As `60` tabelas publicas permanecem inalteradas.

Por seguranca, outro banco exige:

```powershell
python scripts\testar_app_postgresql.py `
  --database outro_banco `
  --confirmar-banco outro_banco
```

## Limites atuais

A camada nao reescreve automaticamente o dialeto SQLite. As ocorrencias
restantes foram classificadas em `docs/POSTGRESQL_AUDITORIA_SQL_FINAL.md` como
infraestrutura SQLite, manutencao de esquema restrita, ferramentas historicas
ou helpers com alternativa explicita para PostgreSQL. Novas ocorrencias sem
classificacao fazem `scripts/auditar_sql_sqlite.py` falhar.

Ao encontrar `executescript` no PostgreSQL, o adaptador interrompe a operacao
com uma mensagem explicita. Isso evita uma execucao parcial de uma rotina
incompativel.

## Proxima etapa

Autenticacao, auditoria, Controle de Pessoal, Gestao de Usuarios,
Recolhimentos de Materiais, Amostras de Animais e Visitas de Arboviroses
possuem leitura e escrita validadas. BRI e Pontos Estrategicos tambem estao
homologados, incluindo seus vinculos. O Historico de Importacoes e a pagina
completa de Importacao Kobo tambem estao homologados.
Dashboard Integrado, Producao Operacional e Resultados Laboratoriais possuem
agora suas consultas homologadas nos dois bancos. O bloco de visitas de
Esporotricose, incluindo visitas, animais encontrados, buscas de feridos,
cadastro clinico, receitas, estoque e anexos, tambem esta homologado. O
cadastro, as leituras, o monitoramento, os diarios, o calendario e o fluxo
laboratorial de Ovitrampas tambem estao prontos. O espelho Conta Ovos/SisPNCD
foi homologado na sequencia. O Registro Geografico tambem esta coberto,
incluindo cadastro, edicao, acompanhamento, mapa e impressao. Acoes e
Atendimentos do Setor tambem esta homologado, incluindo anexos e relatorio
tecnico. O Boletim Mensal tambem esta homologado, incluindo indicadores,
fechamento, PDF e XLSX. Mapa geral, Notificacoes e Relatorio por Servidor
tambem estao homologados, incluindo escrita auditada, relatorios individual e
do setor e os blocos operacionais complementares. Exportacoes, consolidados,
diagnostico, backup e restauracao da Central do Sistema tambem estao
implementados. A auditoria final do SQL exclusivo encontrou e corrigiu a
importacao ativa de Esporotricose. O proximo lote e o ensaio integrado com uma
copia recente do SQLite oficial, seguido de concorrencia e preparacao do
servico Windows.

Cada lote deve:

1. substituir manutencao de esquema em tempo de execucao por migracoes;
2. separar SQL comum das poucas consultas especificas de cada banco;
3. validar leituras e gravacoes em ambos os bancos;
4. testar a pagina correspondente contra `endemias_teste`;
5. manter o SQLite oficial como padrao ate a homologacao completa.
