# Guia de trabalho com Codex e Claude Code

Este guia define como duas IAs devem colaborar sem disputar arquivos, alterar
dados reais ou publicar codigo ainda nao revisado.

## Papeis

### Codex: implementador principal

- investiga o codigo existente;
- implementa a solicitacao;
- cria ou atualiza testes;
- executa testes focados e regressao proporcional ao risco;
- atualiza documentacao;
- corrige os achados da revisao;
- cria commits e faz push da branch de trabalho;
- integra na `master` somente depois da aprovacao.

### Claude Code: revisor independente

- compara a branch do Codex com `master`;
- trabalha somente em leitura por padrao;
- procura bugs, regressoes, falhas de seguranca e perda de dados;
- confere concorrencia e compatibilidade SQLite/PostgreSQL;
- valida se os testes cobrem as regras alteradas;
- apresenta achados por gravidade, com arquivo e linha;
- nao faz merge nem push para `master`;
- nao reimplementa a tarefa, salvo autorizacao expressa.

### Usuario: aprovacao operacional

- explica o fluxo real do setor;
- testa a interface e as regras de negocio;
- decide se os achados foram resolvidos;
- autoriza a integracao na versao oficial.

## Excecao: Claude como implementador

O usuario pode pedir diretamente ao Claude que intervenha no codigo em uma
tarefa excepcional. Essa autorizacao substitui o modo somente leitura apenas
para o escopo informado e deve indicar a branch de trabalho. Um achado de
revisao, uma sugestao do Codex ou uma solicitacao indireta nao contam como essa
autorizacao.

Quando receber essa autorizacao, o Claude pode:

- investigar e editar os arquivos incluidos no escopo;
- criar ou ajustar os testes necessarios;
- executar a regressao proporcional ao risco;
- criar commit e fazer push somente na branch autorizada;
- entregar ao usuario o resumo das mudancas, testes e riscos residuais.

A excecao preserva os seguintes limites:

- Codex e Claude nao trabalham simultaneamente na mesma branch ou nos mesmos
  arquivos;
- a implementacao do Claude recebe revisao independente, normalmente do Codex
  ou de outro revisor indicado pelo usuario, antes da integracao;
- autorizacao para editar, commitar e publicar a branch nao autoriza por si so
  merge ou push na `master`;
- alteracoes em dados reais, credenciais, tarefas do Windows, reinicializacao
  do sistema e outras acoes operacionais ou destrutivas exigem autorizacao
  especifica do usuario;
- encerrada a tarefa excepcional, o Claude volta automaticamente ao papel de
  revisor somente leitura.

## Estado atual das pastas

```text
C:\endemias
  branch master
  sistema oficial
  porta 5000

C:\endemias-revisao
  branch revisao
  ambiente auxiliar do Claude
  porta 5002
  banco SQLite local de teste
```

A pasta dedicada do Codex ainda nao foi criada. Quando o fluxo revisado for
adotado, a sugestao e:

```powershell
cd C:\endemias
git fetch origin
git worktree add C:\endemias-codex -b codex/nome-do-lote master
```

Nao execute esse comando com `codex/nome-do-lote` ja existente. Nesse caso,
use a branch existente ou escolha outro nome.

## Tamanho dos lotes

Por acordo entre o usuario, o Codex e o Claude, o padrao da migracao passa a
ser implementar **2 a 3 modulos relacionados por branch** antes de solicitar
uma revisao. O objetivo e reduzir o custo de contexto e o tempo de revisao sem
perder a separacao entre implementacao, revisao e integracao.

Um modulo de risco alto, uma mudanca destrutiva ou um conjunto que fique grande
demais para revisao clara pode continuar em uma branch isolada. O usuario
tambem pode definir outro recorte expressamente.

## Fluxo completo de um lote

1. Atualizar a `master` oficial e confirmar que esta limpa.
2. Criar uma branch `codex/nome-curto-do-lote` a partir da `master`.
3. Codex implementa os 2 ou 3 modulos relacionados somente nessa branch.
4. Codex executa testes, cria commit e faz push da branch.
5. Claude executa `git fetch origin` em `C:\endemias-revisao`.
6. Claude revisa `master...origin/codex/nome-curto-do-lote` sem editar.
7. Usuario leva os achados ao Codex.
8. Codex corrige na mesma branch, testa, commita e faz push.
9. Claude revisa novamente somente os novos commits ou o diff completo.
10. Usuario faz o teste funcional no ambiente da branch.
11. Depois da aprovacao, Codex integra a branch na `master`.
12. Executar regressao final aplicavel.
13. Fazer push de `master`.
14. Reiniciar o sistema oficial quando necessario.

## Comandos de revisao para o Claude

```powershell
cd C:\endemias-revisao
git fetch origin
git log --oneline master..origin/codex/nome-do-lote
git diff --stat master...origin/codex/nome-do-lote
git diff master...origin/codex/nome-do-lote
```

O Claude nao precisa trocar de branch para revisar. Isso evita perder as
configuracoes proprias da branch `revisao`.

Para revisar apenas a rodada de correcoes, forneca os hashes:

```powershell
git diff HASH_ANTERIOR..HASH_NOVO
```

## Teste da implementacao

O teste funcional deve ocorrer no worktree do Codex ou num worktree temporario
baseado na branch do lote. Nao use a pasta oficial para testar codigo ainda
nao aprovado.

Cada ambiente precisa ter:

- porta propria;
- banco proprio;
- anexos e uploads proprios;
- logs e backups proprios;
- credenciais locais nao versionadas;
- indicacao visual clara de ambiente de teste.

Separar branch nao separa banco automaticamente. Esse e o risco operacional
mais importante do fluxo multiagente.

## PostgreSQL nos ambientes

Quando a migracao estiver concluida:

```text
master/producao      -> endemias
Codex/teste         -> endemias_codex
Claude/revisao      -> endemias_revisao
ensaio de migracao  -> endemias_migracao
```

Nunca permita que uma branch experimental use a base `endemias` oficial. Use
usuarios PostgreSQL separados e conceda ao ambiente de teste acesso apenas ao
banco correspondente quando possivel.

## Como o Claude deve apresentar a revisao

Ordem obrigatoria:

1. achados criticos;
2. achados altos;
3. achados medios;
4. achados baixos relevantes;
5. testes ausentes e riscos residuais;
6. perguntas ou premissas.

Cada achado deve conter:

- gravidade;
- arquivo e linha;
- comportamento incorreto;
- situacao concreta que reproduz o problema;
- impacto;
- orientacao objetiva, sem reescrever toda a solucao.

Nao tratar preferencia estetica subjetiva como bug. Nao produzir um resumo
longo antes dos achados.

## Como passar os achados de volta ao Codex

Envie o texto integral da revisao e acrescente:

```text
Corrija os achados validos na mesma branch. Antes de editar, confira cada
afirmacao no codigo; nao aplique mecanicamente sugestoes incorretas. Preserve o
escopo original, execute os testes necessarios, faca commit e push. Depois
resuma quais achados foram corrigidos e quais foram rejeitados, com motivo.
```

Uma IA revisora pode se enganar. O Codex deve validar tecnicamente cada achado.

## Prevencao de conflitos

- Nunca deixe Codex e Claude editarem o mesmo arquivo simultaneamente.
- Uma branch deve ter um implementador responsavel.
- Nao use `git reset --hard` ou `git checkout --` para resolver divergencias.
- Nao force push em branches compartilhadas.
- Nao faca merge da branch `revisao` inteira na `master`.
- Nao misture modulos sem relacao. O lote padrao pode reunir 2 ou 3 modulos
  relacionados, desde que o diff continue claro e testavel.
- Se a `master` mudar durante um lote, atualize a branch com cuidado e
  execute novamente os testes.
- Commits devem ser pequenos o suficiente para revisao, mas representar uma
  unidade funcional coerente.

## Quando vale chamar o Claude

Revisao recomendada:

- migracao PostgreSQL;
- autenticacao, permissoes e auditoria;
- alteracoes destrutivas;
- importacao e sincronizacao de dados;
- estoque e calculos clinicos;
- API Conta Ovos;
- funcionamento offline;
- backups e restauracao;
- mudancas em varios modulos.

Revisao separada normalmente dispensavel:

- texto ou rotulo isolado;
- ajuste pequeno de CSS;
- troca de icone;
- correcao visual de baixo risco;
- documentacao sem mudanca operacional.

Agrupe pequenas correcoes relacionadas num lote para economizar uso do Claude.

## Mensagem inicial recomendada para o novo Codex

```text
Voce sera o implementador principal do projeto Endemias. O repositorio esta em
C:\endemias e a branch oficial e master. Antes de qualquer acao, leia
AGENTS.md, CONTEXTO_PARA_IA.md, docs/GUIA_CONTINUIDADE_TECNICA.md,
docs/GUIA_TRABALHO_MULTIAGENTE.md e a documentacao PostgreSQL indicada por
eles. Confira git status e os commits recentes.

PostgreSQL e producao. O SQLite esta congelado como rollback e nunca pode ser
aberto em paralelo ou receber novas escritas. Nunca altere dados reais nos
testes PostgreSQL. Toda modificacao deve terminar em commit e push. Mantenha a
compatibilidade dual para testes e rollback controlado.

Primeiro, apenas confirme resumidamente o estado que encontrou, a proxima
etapa e os cuidados que seguira. Nao modifique nada nessa primeira resposta.
Depois eu autorizarei a continuacao.
```

## Mensagem inicial recomendada para o Claude Code

```text
Voce sera o revisor independente do projeto Endemias. Abra
C:\endemias-revisao e leia CLAUDE.md, AGENTS.md, CONTEXTO_PARA_IA.md,
docs/GUIA_CONTINUIDADE_TECNICA.md e docs/GUIA_TRABALHO_MULTIAGENTE.md.

Seu papel padrao e somente leitura: comparar branches do Codex com master,
procurar bugs, regressoes, falhas de seguranca, riscos de perda de dados,
problemas de concorrencia e incompatibilidades SQLite/PostgreSQL. Nao edite,
nao faca merge e nao envie nada para master sem minha autorizacao expressa.

Primeiro, confira o repositorio e confirme resumidamente que entendeu seu papel
e o estado atual. Nao revise nenhuma branch ate eu informar o nome dela.
```

## Mensagem para iniciar uma implementacao

```text
Crie uma branch codex/NOME a partir da master atualizada e implemente a tarefa
abaixo. Preserve SQLite e PostgreSQL, use banco de teste, execute testes
focados e regressao proporcional ao risco, atualize a documentacao, faca
commit e push da branch. Nao integre na master ainda, pois o Claude revisara.

Tarefa:
[DESCREVER AQUI]

Criterios de aceitacao:
[LISTAR AQUI]
```

## Mensagem para iniciar uma revisao

```text
Revise origin/codex/NOME em comparacao com master.

Objetivo da mudanca:
[DESCREVER]

Criterios de aceitacao:
[LISTAR]

Nao modifique arquivos. Apresente somente achados reais, ordenados por
gravidade, com arquivo e linha, cenario de reproducao, impacto e testes
ausentes. Se nao houver problemas, diga claramente e informe os riscos
residuais.
```
