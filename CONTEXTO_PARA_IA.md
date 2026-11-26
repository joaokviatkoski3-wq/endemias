# Contexto para continuidade do projeto

Atualizado em 26/11/2026.

O VSATT é o sistema interno de Vigilância em Saúde de Almirante Tamandaré.
O portal reúne Endemias e Vigilância Ambiental, com acesso por setor e perfil.

## Onde começar

1. Leia [o estado operacional](docs/ESTADO_ATUAL_PROJETO.md) para confirmar a
   versão ativa, as pendências e os projetos futuros.
2. Consulte [as regras do repositório](AGENTS.md) e o guia do módulo antes de
   mexer em código, testes, banco ou implantação.
3. Confirme o estado no Git, na aplicação ou no relatório de implantação antes
   de reutilizar um procedimento antigo.

## Desenvolvimento e produção

- `C:/endemias` é a instalação oficial. PostgreSQL `endemias`, local e protegido,
  é a fonte de dados. `endemias.db` é a cópia SQLite congelada para rollback.
- Use uma cópia de trabalho isolada para desenvolvimento. Separe porta, banco,
  anexos, logs e configurações. A raiz de um checkout Git, sozinha, deixa esses
  recursos compartilhados se o ambiente apontar para produção.
- Use SQLite temporário ou PostgreSQL `endemias_teste` em testes. A suíte usa
  `python -m unittest discover -s tests -t .` com a referência de teste configurada.
- Antes de implantar, confira o escopo e a regressão. Confirme o backup e a
  preservação dos dados quando a atualização exigir parada ou migração.
- Codex opera o repositório. Outro agente intervém quando o usuário solicitar,
  conforme o [guia de trabalho](docs/GUIA_TRABALHO_MULTIAGENTE.md).

## Atalhos temporários

Coloque os `.bat` avulsos enviados ao usuário em `C:/VSATT-Temporarios`.
Use caminhos absolutos para os arquivos de apoio e deixe cada atalho pronto
para o usuário apagar após a execução. Os scripts operacionais versionados
continuam nos locais próprios do repositório.

## Histórico

O retrato anterior completo está no commit `de21b05`, em
`CONTEXTO_PARA_IA.md` e `docs/ESTADO_ATUAL_PROJETO.md`. Os guias por módulo
guardam os fluxos e a documentação técnica das etapas anteriores.
