# Guia de operacao e colaboracao entre agentes

Este guia define o fluxo vigente do Endemias. Codex e o operador unico e
principal. Outros agentes, inclusive Claude, participam somente quando o
usuario solicitar uma intervencao especifica. Revisao externa nao e requisito
para commit, push ou integracao na `master`.

## Papeis

### Codex: operador unico e principal

Codex:

- investiga o codigo e o estado real dos ambientes;
- implementa as mudancas solicitadas;
- protege PostgreSQL de producao e o SQLite congelado;
- cria e executa testes e ensaios isolados;
- atualiza a documentacao de continuidade;
- decide a estrategia Git segura dentro do pedido do usuario;
- cria commits, faz push e pode integrar na `master` sem aguardar revisao de
  outro agente;
- corrige ou prepara rollback seguro quando o usuario identificar um erro.

Autonomia de integracao nao autoriza reduzir testes, tocar dados reais durante
ensaios, ocultar falhas ou executar operacoes destrutivas fora do escopo.

### Usuario

O usuario define prioridades e regras de negocio, valida fluxos funcionais e
autoriza operacoes reais sensiveis, como migracoes de producao, pilotos de API,
alteracoes de dados e reinicio do servico oficial quando necessario.

### Claude e outros agentes

Claude pode revisar, investigar ou implementar esporadicamente quando o usuario
pedir. Essa participacao e opcional e nao cria um portao permanente para o
trabalho do Codex.

Quando outro agente produzir alteracoes:

- use branch propria;
- nao edite a mesma branch ou os mesmos arquivos simultaneamente com Codex;
- registre claramente autoria, testes e escopo;
- Codex confere o estado vivo antes de integrar ou continuar o trabalho.

O worktree `C:\endemias-revisao` e a branch `revisao` sao auxiliares historicos.
Nunca faca merge cego dessa branch na `master`, pois ela pode conter
configuracoes exclusivas do ambiente auxiliar.

## Fluxo normal de uma mudanca

1. Ler `AGENTS.md`, `CONTEXTO_PARA_IA.md` e
   `docs/ESTADO_ATUAL_PROJETO.md`.
2. Conferir branch, `git status`, commits recentes e worktrees.
3. Atualizar a `master` e criar `codex/nome-da-tarefa` quando o isolamento for
   util.
4. Implementar com `apply_patch`, preservando alteracoes alheias.
5. Executar testes focados, regressao proporcional e ensaios PostgreSQL apenas
   em `endemias_teste`, tabelas temporarias ou transacoes revertidas.
6. Confirmar o hash do SQLite congelado antes e depois.
7. Atualizar a documentacao depois de confirmar o resultado.
8. Criar commit e push. Se a mudanca estiver pronta e o pedido incluir entrega,
   Codex pode integrar e publicar a `master` diretamente.
9. Se surgir erro posterior, investigar a causa e corrigir ou reverter codigo
   com seguranca; rollback de dados exige plano explicito.

Claude so entra nesse fluxo quando o usuario o chamar. Sua ausencia nao pausa
nem bloqueia o trabalho.

## Ambientes conhecidos

```text
C:\endemias
  master
  sistema oficial
  PostgreSQL endemias
  porta 5000

C:\endemias-revisao
  revisao
  ambiente auxiliar historico

C:\endemias-codex
  codex/enviar-leituras-conta-ovos
  lote de escrita remota ainda fora da producao
```

Uma branch ou worktree nao isola banco, porta, anexos, logs, backups ou
credenciais automaticamente. Nunca permita que um ambiente experimental use o
PostgreSQL `endemias` de producao.

## Inicializacao padrao de um worktree de teste

Execute `testar.bat` na raiz do worktree. Ele:

- recusa execucao em `C:\endemias`;
- compara a identidade do banco local com o SQLite oficial e falha fechado;
- fixa a porta `5002` e avisa se ela estiver ocupada;
- usa SQLite e direciona banco, anexos, temporarios, log, chave, configuracao
  Kobo e backups para o proprio worktree;
- cria banco vazio ou oferece copia manual e explicita do snapshot real;
- valida o esquema minimo de banco existente e arquiva localmente um arquivo
  vazio, corrompido ou incompleto antes de preparar uma massa valida;
- define `ENDEMIAS_AMBIENTE=teste` e exibe faixa de dados nao oficiais;
- esconde a faixa de impressoes e PDFs.

A copia opcional de `C:\endemias\endemias.db` contem dados reais de saude. Deve
ficar restrita ao worktree, nunca ser versionada e ser apagada quando o ambiente
for descartado. A origem e somente leitura.

## Testes obrigatorios e dados

Para a suite Python, use somente:

```powershell
python -m unittest discover -s tests -t .
```

Nunca execute testes diretamente nem omita `-t .`. PostgreSQL `endemias` e
producao. Ensaios PostgreSQL usam exclusivamente `endemias_teste`, tabelas
temporarias ou transacoes revertidas. `C:\endemias\endemias.db` e rollback
congelado e nunca recebe escritas.

## Git e concorrencia

- Nao use `git reset --hard` ou `git checkout --` para descartar trabalho.
- Nao use force push em branches compartilhadas.
- Nao integre branches historicas apenas porque aparecem como nao mescladas.
- Confira se a branch foi atualizada sobre a `master` antes de integrar.
- Nao deixe dois agentes editarem os mesmos arquivos ao mesmo tempo.
- Commits devem representar unidades coerentes e incluir a documentacao
  aplicavel.

## Intervencao opcional do Claude

Quando o usuario pedir revisao, Claude pode comparar a branch indicada com a
`master` e devolver achados. Quando o usuario pedir implementacao, deve usar
branch propria. Em ambos os casos, Codex continua responsavel por conferir cada
afirmacao no codigo e pelo estado final integrado.

Comandos usuais de uma revisao opcional:

```powershell
git fetch origin
git log --oneline master..origin/codex/nome-da-tarefa
git diff --stat master...origin/codex/nome-da-tarefa
git diff master...origin/codex/nome-da-tarefa
```

## Mensagem inicial recomendada para o Codex

```text
Voce e o operador unico e principal do Endemias. Leia AGENTS.md,
CONTEXTO_PARA_IA.md, docs/ESTADO_ATUAL_PROJETO.md e os guias tecnicos
aplicaveis. Confira Git e worktrees. PostgreSQL endemias e producao e o SQLite
oficial e rollback congelado. Implemente, teste, documente, faca commit e push.
Quando a mudanca solicitada estiver pronta, voce pode integra-la na master sem
revisao externa obrigatoria.
```
