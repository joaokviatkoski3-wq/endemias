# Central Conta Ovos: decisao de interface

## Decisao desta etapa

`Conta Ovos` passa a ser uma pagina principal de **consulta da integracao externa**. Nesta primeira etapa ela mostra exclusivamente o espelho local de dados ja sincronizados: resumo, historico de contagens e cadastro de ovitrampas. Abrir a pagina nunca chama a API privada e nunca envia, atualiza ou exclui dados locais ou remotos.

O objetivo e substituir gradualmente a consulta por planilhas exportadas por uma interface pesquisavel dentro do Endemias, sem transformar a visualizacao em uma acao operacional irreversivel.

## Separacao intencional de responsabilidades

```text
Conta Ovos (integracao e analise do espelho local)
|- Visao geral
|- Ovitrampas
|  |- Contagens sincronizadas
|  `- Cadastro importado
|- EDLs                         (reservado)
`- Quarteiroes e acoes          (reservado)

Ovitrampas (operacao local do setor, mantida)
|- Leituras, monitoramento e cadastro operacional
|- Diarios, calendario e laboratorio
`- Fluxos locais de conferencia/contingencia
```

As duas raizes nao duplicam a mesma funcao. **Conta Ovos** responde "o que a plataforma externa ja possui e o que foi sincronizado?"; **Ovitrampas** responde "como o setor organiza e executa o trabalho local?". Por isso, nesta etapa, nao remover controles de laboratorio, diarios, calendario, importacao CSV ou contingencias da pagina Ovitrampas. Eles continuam necessarios para a operacao e para a recuperacao supervisionada enquanto a integracao amadurece.

`Conta Ovos e SisPNCD` foi renomeado na navegacao para **SisPNCD**, pois o novo centro passou a concentrar a identidade Conta Ovos. A rota antiga permanece para compatibilidade e conserva o boletim TBO manual como contingencia; nao ha migracao automatica desse fluxo neste lote.

## Fonte e limites dos dados

- Contagens: `ovitrampas_ocorrencias_conta_ovos`, atualizada somente pelo sincronizador GET supervisionado e identificada por `counting_id` local.
- Cadastro: `ovitrampas_armadilhas`, historico importado que inclui os campos locais ainda necessarios, como responsavel e telefone.
- Estado de sincronizacao: `contaovos_execucoes`, cujo resumo ja e sanitizado.
- A tela mostra o que esta no banco no momento da consulta; nao promete que a API remota esteja atualizada. A data de importacao deixa essa diferenca visivel ao operador.

Nenhum endpoint da central importa chave, monta URL da API ou usa `postcounting`. Escrita remota, quando e se for autorizada, devera continuar em lote separado, com reconciliacao GET antes/depois, confirmacao humana e revisao independente.

## Evolucao planejada

1. Ampliar filtros e detalhes de Ovitrampas com campos que a API disponibilize e que estejam persistidos e validados localmente.
2. Adicionar EDLs como nova aba do mesmo centro somente quando houver uso no setor, contrato de API confirmado, schema/migracao e sincronizacao GET.
3. Adicionar Quarteiroes e acoes pelo mesmo criterio, sem assumir que apagar ou recriar objetos remotos preserva seus bloqueios.
4. Avaliar escritas e automatizacoes separadamente, depois de a consulta ser usada e conferida no fluxo real. A interface de consulta nao deve ganhar botoes de escrita por conveniencia.

## Checklist para revisao

- Todas as rotas da central devem aceitar apenas `GET`.
- Consultas devem usar o adaptador dual e SQL valido em SQLite e PostgreSQL.
- Nenhum teste pode usar o banco PostgreSQL `endemias` oficial ou o SQLite congelado; ensaios PostgreSQL usam tabelas temporarias no banco descartavel.
- Mudancas futuras na central devem preservar a pagina Ovitrampas e o SisPNCD enquanto seus fluxos operacionais nao tiverem substituto homologado.
