# Notificacoes a partir de resultados laboratoriais

Atualizado em 09/09/2026.

## Regra de negocio vigente

Um resultado laboratorial cria ou atualiza um foco por visita quando houver ao
menos uma forma de **Aedes aegypti** (larva, pupa, exuvia ou adulto). O foco
reune todos os tubos positivos da visita.

A pagina `Notificacoes` mostra somente focos com `gera_notificacao=1`. A regra
para esse campo e:

| Tipo de trabalho | Tipo do imovel | Gera notificacao |
| --- | --- | --- |
| PE | qualquer | Nao |
| TB, TBO ou PVE | `TB` ou `Terreno Baldio` | Nao |
| TB, TBO ou PVE | qualquer outro | Sim |

Resultados de Aedes albopictus ou de outra especie nao criam foco nem
notificacao.

## Fluxos cobertos

- Importacao Kobo/planilha de larvas: o ETL chama a regra comum ao concluir a
  associacao entre tubo e visita.
- Lançamentos Laboratorio: salvar um resultado ou editar um lancamento recente
  recalcula o foco da visita na mesma transacao do resultado.

O foco e mantido para analise mesmo quando nao deve aparecer em Notificacoes;
nesses casos `gera_notificacao` vale `0`. Ao atualizar um foco existente, o
status manual (`impressa`, `entregue` etc.) nao e sobrescrito.

## Previa do historico

O script abaixo apenas lista positivos cuja situacao atual diverge da regra.
Ele nao cria, altera nem arquiva notificacoes:

```powershell
python scripts/diagnosticar_notificacoes_laboratorio.py --database endemias --confirmar-banco endemias
```

Motivos possiveis:

- `positivo_sem_foco`: resultado positivo sem foco correspondente;
- `notificacao_desativada`: deveria aparecer, mas `gera_notificacao=0`;
- `notificacao_indevida`: deveria ficar fora da fila, mas `gera_notificacao=1`.

Qualquer reconciliacao historica deve ser feita somente depois da conferencia
humana dessa previa. Nao ha criacao retroativa automatica nesta correcao.
