# Central Conta Ovos: decisao de interface

## Decisao desta etapa

`Conta Ovos` e uma pagina de **consulta da integracao externa**, nunca um proxy em tempo real. Toda tela le exclusivamente o espelho local PostgreSQL ja sincronizado por processos GET supervisionados fora da web; abrir qualquer aba nunca chama a API remota nem envia, atualiza ou exclui dados locais ou remotos.

Isso e deliberado, nao uma limitacao temporaria: a API Conta Ovos nao tem SLA, nao documenta limite de requisicoes e o setor precisa de uma tela responsiva mesmo se o fornecedor estiver fora do ar. O espelho local e a fonte de leitura da interface; a API e a fonte de verdade dos dados que ela administra, e a sincronizacao GET e o unico canal que atualiza o espelho.

## Estrutura desta etapa

```text
Conta Ovos (integracao e analise do espelho local, somente GET)
|- Visao geral                  (KPIs e evolucao gerais, mistura CSV legado e API)
|- Ovitrampas
|  |- Contagens                 (somente proveniencia API)
|  |- Monitoramento             (ranking/positividade, somente proveniencia API)
|  |- Cadastro remoto           (somente espelho contaovos_registro_ovitrampas)
|  |- Mapa                      (coordenadas remotas + territorio local, leitura)
|  `- Sincronizacao e divergencias (estado GET + comparacoes informativas)
|- EDLs                         (reservado, sem funcionalidade simulada)
`- Quarteiroes e acoes          (reservado, sem funcionalidade simulada)

Ovitrampas (operacao local do setor, mantida sem alteracao)
|- Leituras, monitoramento e cadastro operacional
|- Diarios, calendario e laboratorio
`- Fluxos locais de conferencia/contingencia, inclusive importacao CSV
```

**Visao geral** manteve o comportamento anterior (mistura CSV legado e API, porque seu proposito e um retrato geral do historico completo). A sub-area **Ovitrampas**, nova nesta etapa, e mais rigorosa: Contagens e Monitoramento **sempre filtram por proveniencia API** (`arquivo_origem = 'API privada Conta Ovos'`), porque indicadores calculados sobre dado legado de CSV misturado com dado API produziriam uma leitura enganosa do que a integracao efetivamente trouxe.

As duas raizes de nivel superior (`Conta Ovos` e `Ovitrampas`) continuam sem duplicar a mesma funcao. **Conta Ovos** responde "o que a plataforma externa ja possui e o que foi sincronizado?"; **Ovitrampas** responde "como o setor organiza e executa o trabalho local?". Por isso este lote nao removeu nem alterou controles de laboratorio, diarios, calendario, importacao CSV ou contingencias da pagina Ovitrampas — eles continuam necessarios para a operacao e para a recuperacao supervisionada enquanto a integracao amadurece. A linguagem visual da sub-area Ovitrampas (abas internas, KPIs, tabelas) reproduz deliberadamente a de `/ovitrampas`, para que a mesma pessoa reconheca o padrao ao trocar de tela — mas nenhum controle operacional (importar CSV, editar leitura, imprimir diario) foi duplicado ali. Quem precisa operar continua indo para `/ovitrampas`; a nova area so mostra o que a API disse.

## Fonte de verdade, complementos locais e territorio: quem manda em que

Esta e a regra mais importante deste documento, porque e a que mais facilmente se perde em lotes futuros:

- **Contagens de ovos** (`ovitrampas_ocorrencias_conta_ovos`): fonte de verdade e a API Conta Ovos, mas a tabela historica e deliberadamente compartilhada com a importacao CSV legada (decisao ja tomada nos lotes de sincronizacao). Um novo dominio nao deve criar um segundo historico de contagens; deve continuar usando essa tabela e diferenciar por `arquivo_origem`.
- **Cadastro de ovitrampas — campos remotos** (`contaovos_registro_ovitrampas`, novo nesta etapa): fonte de verdade e a API (`getmunicipalityovitrapspublic`, endpoint publico, sem chave). Guarda apenas o que a API devolve: coordenadas, `ovitrap_id` interno, media de ovos, IDs de grupo/bloco/usuario remotos e o instante de sincronizacao. Nunca grava responsavel, telefone ou qualquer outro campo local.
- **Cadastro de ovitrampas — complementos locais** (`ovitrampas_armadilhas`): fonte de verdade e o Endemias. Responsavel, telefone e demais complementos **nunca sao apresentados como se viessem da API**; a interface sempre rotula esses campos como "local" (badge dedicado) quando exibidos ao lado de dados remotos.
- **Quarteiroes, geometria e composicao territorial**: fonte de verdade e local — `/static/quarteiroes.geojson` e o Registro Geografico. A aba Mapa desta central desenha as coordenadas que a API devolveu, mas o quarteirao/localidade mostrados no popup vem do cadastro local (`ovitrampas_armadilhas.quarteirao`), nunca de um calculo geometrico sobre a coordenada remota. A API pode ser **vinculada** a esse territorio (por correspondencia de ID normalizado); ela nunca o **sobrescreve** nem o recalcula.
- **Estado de sincronizacao** (`contaovos_execucoes`, compartilhada entre todos os fluxos GET por `tipo`): resumo ja sanitizado, sem qualquer dado sensivel.

A reconciliacao entre `ovitrampa_id_remoto` (preserva zeros a esquerda, como devolvido pela API) e `ovitrampa_id` local usa a mesma chave de comparacao ja homologada em `app_core/ovitrampas.py::chave_comparacao_ovitrampa_id` (ignora apenas zeros a esquerda para fins de correspondencia, sem alterar nenhum identificador persistido). Isso evita duplicar a logica de reconciliacao que a sincronizacao de contagens ja resolveu.

## Divergencias: informativo, nunca automatico

A aba "Sincronizacao e divergencias" lista tres comparacoes, todas somente leitura:

1. ovitrampas no espelho remoto sem cadastro local correspondente;
2. ovitrampas com cadastro local, mas coordenadas remota/local divergentes alem de uma tolerancia (~50 m);
3. ovitrampas com contagem de proveniencia API mas sem cadastro remoto ainda sincronizado.

Nenhuma dessas listas oferece um botao para corrigir, mesclar ou excluir. A decisao de investigar ou corrigir e sempre humana; a interface so torna a pendencia visivel.

## Fundacao GET do cadastro remoto

`app_core/contaovos_registro.py` fornece a sincronizacao do espelho de cadastro, no mesmo padrao ja homologado para contagens e fila de laboratorio: pagina o endpoint publico ate lista vazia ou limite de 100 paginas, valida escopo territorial (`municipality_code`/`state_code`) e formato de cada registro antes de qualquer escrita, e so entao substitui o espelho local em uma transacao atomica com upsert por `ovitrampa_id_remoto`. A migracao `0005_contaovos_registro_ovitrampas.sql` cria a tabela em PostgreSQL; `contaovos_registro.ensure_schema_connection` cria o equivalente em SQLite para testes.

Diferente da sincronizacao de contagens, este endpoint e **publico** (`getmunicipalityovitrapspublic`, sem parametro `key`), entao nao ha risco de credencial nesta fundacao. Ainda assim, a execucao continua supervisionada por linha de comando (`scripts/sincronizar_registro_ovitrampas_contaovos.py`, com confirmacao explicita e banco padrao `endemias_teste`), exatamente como os demais sincronizadores — **nao ha botao na interface para disparar sincronizacao**. A primeira sincronizacao real (se e quando o setor decidir usa-la) e uma decisao operacional separada deste lote.

## Quem depende de dado remoto ja disponivel, e quem continua local

- Dependem do espelho remoto (podem ficar vazias ate a primeira sincronizacao real do cadastro): Ovitrampas > Cadastro remoto, Ovitrampas > Mapa, parte de Ovitrampas > Sincronizacao e divergencias.
- Ja funcionam com o que esta sincronizado hoje (contagens, via sincronizador ja homologado): Ovitrampas > Contagens, Ovitrampas > Monitoramento.
- Continuam exclusivamente locais e nao migram para esta central: leituras semanais operacionais, diarios, calendario, laboratorio e importacao CSV — todos em `/ovitrampas`.
- Fora de escopo neste lote, com placeholder reservado e sem dado simulado: EDLs e Quarteiroes/acoes. A API documenta os endpoints, mas nenhum contrato foi validado, nenhum schema foi criado e nenhuma sincronizacao GET foi implementada para esses dominios.
- Fora de escopo em qualquer lote de consulta: `/postcounting`, `/postaction` e qualquer `postdelete*`. Envio remoto continua dependente de piloto supervisionado e revisao independente, como ja registrado em `docs/CONTA_OVOS_API.md`.

## Como adicionar um novo dominio remoto sem criar duas fontes concorrentes

Um implementador futuro que for adicionar EDLs, Quarteiroes/acoes ou qualquer outro dominio remoto deve seguir o mesmo criterio usado aqui, nesta ordem:

1. Confirmar que o endpoint GET esta documentado, com campos conhecidos, e decidir se ele e publico ou exige chave.
2. Decidir se o dominio reaproveita uma tabela historica ja existente com fallback CSV (como contagens) ou exige uma tabela de espelho propria (como cadastro remoto) — a resposta depende de existir ou nao um fluxo local paralelo que ja alimente a mesma tabela.
3. Nunca gravar complemento local nem territorio na tabela de espelho remoto; se o dominio tiver complementos locais, eles ficam em sua propria tabela local, anexados apenas na consulta.
4. Migracao PostgreSQL versionada + criacao equivalente em SQLite (`ensure_schema_connection`), com a nova tabela adicionada a `app_core/schema_metadata.py::INTERNAL_TABLES` se ela nao tiver equivalente no SQLite congelado.
5. Sincronizacao supervisionada por script de linha de comando, nunca por botao na interface, com confirmacao explicita e banco padrao `endemias_teste`.
6. Consultas GET-only na central, com tratamento explicito de "espelho ainda nao sincronizado" (nunca erro 500 cru).
7. Testes de proveniencia, filtros, ausencia de schema e ausencia de escrita remota, seguindo `tests/test_contaovos_registro.py` e `tests/test_contaovos_ovitrampas_consultas.py` como referencia.
8. So depois de a consulta estar em uso real: avaliar escrita remota, sempre em lote separado, com reconciliacao GET antes/depois, confirmacao humana e revisao independente — nunca como extensao natural da tela de consulta.

## Checklist para revisao

- Todas as rotas da central, inclusive as novas em `/api/conta-ovos/ovitrampas/*`, devem aceitar apenas `GET`.
- Consultas devem usar o adaptador dual e SQL valido em SQLite e PostgreSQL.
- Contagens e Monitoramento dentro de Ovitrampas devem sempre filtrar por proveniencia API; nunca por dado CSV legado.
- Cadastro remoto nunca deve exibir responsavel/telefone como se fossem da API; sempre com rotulo "local" explicito.
- Mapa nunca deve recalcular nem sobrescrever quarteirao/localidade a partir da coordenada remota.
- Nenhum teste pode usar o banco PostgreSQL `endemias` oficial ou o SQLite congelado; ensaios PostgreSQL usam tabelas temporarias no banco descartavel `endemias_teste`.
- Mudancas futuras na central devem preservar a pagina Ovitrampas e o SisPNCD enquanto seus fluxos operacionais nao tiverem substituto homologado.
