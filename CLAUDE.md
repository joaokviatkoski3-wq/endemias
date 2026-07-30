# Ambiente de revisao

Este worktree existe para revisao independente das alteracoes do sistema
Endemias. A versao oficial permanece na branch `master`, no diretorio
`C:\endemias`.

## Papel padrao

- Trabalhe como revisor de codigo, salvo quando o usuario autorizar
  explicitamente uma correcao.
- Compare a branch ou o commit indicado pelo usuario com `master`.
- Nao modifique arquivos durante uma revisao somente leitura.
- Apresente primeiro os achados, ordenados por gravidade, com arquivo e linha.
- Priorize bugs, regressoes, seguranca, integridade dos dados, concorrencia,
  compatibilidade SQLite/PostgreSQL e testes ausentes.
- Se nao houver achados, informe isso claramente e descreva riscos residuais.

## Seguranca operacional

- Nunca altere, migre ou apague dados do banco de producao.
- SQLite ainda pode ser o banco oficial durante a migracao gradual.
- Para testes PostgreSQL, use somente bancos e tabelas de teste.
- Nao grave credenciais, tokens, chaves ou bancos reais no repositorio.
- Nao execute `git reset --hard`, `git checkout --`, limpezas destrutivas ou
  operacoes equivalentes.
- Nao faca merge na `master` nem push para `origin/master` sem autorizacao
  explicita do usuario.
- Nao inicie servidor de teste na porta 5000. Use outra porta e banco isolado
  quando testes de navegador forem realmente necessarios.

## Fluxo de revisao

1. Atualize as referencias remotas sem alterar a `master`.
2. Identifique a branch, o commit ou o intervalo solicitado.
3. Inspecione o diff contra `master`.
4. Leia apenas o contexto necessario dos modulos afetados.
5. Execute testes focados quando forem seguros e uteis.
6. Entregue os achados sem modificar a implementacao.

Exemplos de comparacao:

```powershell
git log --oneline master..codex/nome-da-tarefa
git diff --stat master...codex/nome-da-tarefa
git diff master...codex/nome-da-tarefa
```

As instrucoes gerais de `AGENTS.md` continuam validas para todo o repositorio.
