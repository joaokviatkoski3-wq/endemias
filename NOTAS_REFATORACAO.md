# Notas de Refatoracao - Sistema Endemias

## Estado atual

Aplicacao Flask ainda tem `app.py` como entrada principal, mas a modularizacao ja comecou. As URLs publicas foram mantidas iguais.

## Ja feito

- Criado pacote `app_core/`
  - `auth.py`: hash/verificacao de senha, rate limit de login, `login_required`, `nivel_min`, usuario atual e URL segura.
  - `db.py`: conexao SQLite e helpers `query`, `query_one`, `scalar`.
  - `import_history.py`: tabela e operacoes de historico de importacoes.
  - `utils.py`: datas, parse seguro de inteiros e leitura do modelo de notificacao.
  - `work_types.py`: fonte central para tipos de trabalho, labels, cores, status de notificacao, tipos da agenda e metadados de ETL por tipo.
  - `modules.py`: fonte central para paginas/modulos do sistema, com icones, URLs, descricoes, secoes de navegacao e permissao minima.
  - `version.py`: versao semantica atual exibida no rodape do sistema.
- Criado pacote `blueprints/`
  - `admin.py`: primeiro blueprint real.
  - `processar.py`: upload, dry-run, confirmacao e cancelamento de importacoes.
  - `conta_ovos_sispncd.py`: pagina e APIs de consulta do modulo Conta Ovos e SisPNCD.
  - `consultas.py`: paginas de consulta de dashboard, laboratorio e lista de visitas.
  - `agenda.py`: pagina, eventos, edicao/exclusao e lembretes da agenda.
  - `esporotricose.py`: pagina placeholder do futuro modulo de esporotricose.
  - `relatorio_agente.py`: pagina, PDF, API e consultas do relatorio por agente.
- Rotas de usuarios movidas para blueprint mantendo:
  - `/admin/usuarios`
  - `/admin/usuarios/criar`
  - `/admin/usuarios/<uid>/editar`
  - `/admin/usuarios/<uid>/resetar-senha`
- Rotas de processamento movidas para blueprint mantendo:
  - `/processar`
  - `/processar/iniciar`
  - `/processar/stream/<job_id>`
  - `/processar/confirmar/<job_id>`
  - `/processar/cancelar/<job_id>`
- Rotas da agenda movidas para blueprint mantendo:
  - `/agenda`
  - `/api/agenda/eventos`
  - `/api/agenda/eventos/<id_evento>`
  - `/api/agenda/lembretes`
- Rota de esporotricose movida para blueprint mantendo:
  - `/esporotricose`
- Paginas de consulta movidas para blueprint mantendo:
  - `/dashboard`
  - `/laboratorio`
  - `/visitas`
- Relatorio por agente movido para blueprint mantendo:
  - `/relatorio-agente`
  - `/relatorio-agente/pdf`
  - `/api/relatorio-agente`
- Validacao de upload XLSX movida para `app_core/uploads.py`, mantendo wrapper compatível em `app.py`.
- Eventos automaticos da agenda tiveram textos normalizados para evitar mojibake no calendario e no popup de detalhes.
- Criada pagina placeholder `/esporotricose` para futuro modulo de visitas/importacao de esporotricose, sem alteracao de banco.
- Criada pagina `/conta-ovos-sispncd` com abas "Conta Ovos" e "SisPNCD", integrada ao menu e a home.
- Criado `app_core/sispncd.py` com consultas parametrizadas para:
  - boletim Conta Ovos por data/quarteirao/localidade;
  - consolidado SisPNCD por semana epidemiologica/ano/tipo/localidade.
- Aba Conta Ovos passou a considerar somente TBO com `CONTAOVOS_STATUS = 0`.
- A topbar foi reorganizada em duas linhas no desktop para acomodar mais paginas sem sobreposicao.
- Home recebeu cards para Agenda e Usuarios (Usuarios apenas para admin).
- Visual compartilhado separado do `templates/base.html`:
  - CSS global em `static/css/app.css`;
  - JS global em `static/js/app.js`;
  - `base.html` manteve apenas variaveis dinamicas Jinja e estrutura HTML.
- Navegacao e cards da home passaram a consumir `app_core/modules.py`:
  - topbar, menu mobile e home usam o mesmo cadastro de modulos;
  - paginas administrativas ficam ocultas para visualizador;
  - badges de notificacoes e agenda foram preservadas.
- Versao semantica inicial definida como `1.0.0` (`maio/2026`) e exibida no rodape das paginas.
- Versao atual em desenvolvimento: `1.1.0`, com liberacao de gravacao Conta Ovos/SisPNCD.
- Gravacao em SisPNCD foi liberada apos o marco `v1.0.0`:
  - `/api/sispncd/salvar` grava o codigo somente em visitas pendentes com `SISPNCD IS NULL`;
  - a gravacao respeita semana/ano/tipo/localidade e nao sobrescreve codigos ja preenchidos.
- Gravacao do status Conta Ovos foi liberada apos o marco `v1.0.0`:
  - botao "Salvar status" marca como enviados os TBO pendentes do filtro atual;
  - `/api/conta-ovos/salvar-status` altera `CONTAOVOS_STATUS` de `0` para `1`.
- Pagina Conta Ovos e SisPNCD recebeu painel de pendencias:
  - TBO pendentes para Conta Ovos (`CONTAOVOS_STATUS = 0`);
  - visitas pendentes para SisPNCD (`SISPNCD IS NULL`).
- Coluna `visitas.SISPNC` renomeada para `visitas.SISPNCD`, com backup previo do banco real.
- `templates/base.html` reconhece o endpoint novo `admin.admin_usuarios` no menu.
- Historico de importacoes implementado:
  - tabela `importacoes`;
  - registro de upload, dry-run, confirmacao e cancelamento;
  - card "Ultimas importacoes" em `/processar`.
- `iniciar.bat` usa `pip install -r requirements.txt`.
- Login tem rate limit simples por IP+usuario.
- Traceback exposto em `/api/mapa` foi removido.
- Parametros de paginacao passaram a usar parse seguro.
- `app.py` e templates principais passaram a consumir `app_core/work_types.py` para cores/labels de tipos de trabalho.
- Corrigida ordem de declaracao das constantes globais de tipos no `base.html`; scripts de paginas como `/mapa` agora enxergam `WORK_TYPE_COLORS` antes de executar.
- `etl.py` valida divergencias entre `config.json` e `app_core/work_types.py` ao carregar configuracao.
- Campos variaveis por tipo no ETL foram centralizados em `work_types.py`:
  - coluna de hora inicial;
  - coluna de depositos eliminados;
  - colunas de tratamento;
  - regra padrao de `gera_notificacao`.
- `/api/mapa` passou a retornar contagens dinamicas em `tipos: {codigo: total}` por quarteirao, mantendo campos legados em minusculo por compatibilidade.
- `templates/mapa.html` passou a colorir e detalhar tipos a partir de `tipos`, sem listas fixas `TB/TBO/PE/PVE` no JS.
- Removidos hardcodes adicionais de tipos:
  - filtro de tipo em `templates/laboratorio.html`;
  - tags de tipos na home;
  - validacao de `/saida/download/<tipo>`;
  - codigo do tipo com duracao nas consultas de dashboard/relatorio.

## Testes atuais

Arquivo principal de testes:

```powershell
tests\test_security.py
```

Cobertura atual inclui:

- rate limit de login;
- validacao real de XLSX por assinatura;
- parse seguro de parametros;
- rota protegida sem login;
- paginas principais logadas;
- APIs principais;
- permissoes admin/visualizador;
- historico de importacoes em banco temporario;
- renderizacao do historico em `/processar`.
- validacao de consistencia entre `config.json` e `work_types.py`;
- regras centrais de metadados do ETL.
- contrato dinamico de tipos em `/api/mapa`.
- regra central do tipo que possui calculo de duracao.
- eventos automaticos da agenda sem caracteres mojibake (`Â`, `â`, `ð`).
- pagina `/esporotricose` responde para usuarios logados.
- pagina `/conta-ovos-sispncd` responde para usuarios logados.
- APIs `/api/conta-ovos` e `/api/sispncd/pesquisar` retornam JSON.
- consultas SisPNCD nao alteram a coluna `visitas.SISPNCD`.
- endpoint de salvar SisPNCD grava somente pendentes em banco temporario nos testes.
- consultas Conta Ovos respeitam `CONTAOVOS_STATUS = 0` e o endpoint de salvar status grava somente pendentes em banco temporario nos testes.
- API de pendencias de envio retorna resumo para Conta Ovos e SisPNCD.
- assets compartilhados `/static/css/app.css` e `/static/js/app.js` respondem 200.
- cadastro central de modulos valida icones existentes e permissoes admin/visualizador.
- versao atual aparece no layout principal e na tela de login.

## Comandos de validacao

Rodar apos cada corte:

```powershell
python -m py_compile app.py etl.py app_core\auth.py app_core\db.py app_core\import_history.py app_core\modules.py app_core\sispncd.py app_core\uploads.py app_core\utils.py app_core\version.py app_core\work_types.py blueprints\admin.py blueprints\agenda.py blueprints\consultas.py blueprints\conta_ovos_sispncd.py blueprints\esporotricose.py blueprints\processar.py blueprints\relatorio_agente.py tests\test_security.py
python -m unittest discover -s tests -v
```

Ultimo resultado conhecido:

```text
Ran 39 tests
OK
```

## Proximos passos recomendados

1. Mover outro blueprint pequeno quando fizer sentido.
   - Opcoes:
     - `notificacoes`: modulo maior, mas com ganho relevante por reduzir bastante o `app.py`.
     - APIs de consulta maiores (`dashboard`, `laboratorio`, `visitas`) em cortes separados.
2. Preparar base para novos tipos importados por planilha.
   - Sugestao:
     - criar registro central de tipos de importacao futuros;
     - manter paginas placeholder enquanto as tabelas/ETL nao existem;
     - encaixar novas paginas no cadastro central de modulos.

## Cuidados

- Manter URLs iguais durante a refatoracao.
- Rodar testes a cada fatia.
- Nao alterar nem limpar `endemias.db` diretamente sem backup.
- O ambiente desta sessao nao tinha `git` disponivel.
- Existem arquivos sensiveis locais ignorados pelo `.gitignore`: `endemias.db`, `secret.key`, logs, uploads e notificacoes geradas.

## Prompt sugerido para novo chat

```text
Estamos trabalhando no projeto C:\endemias. Leia NOTAS_REFATORACAO.md, revise o estado atual e continue a refatoracao pelo proximo passo recomendado. Mantenha URLs iguais e rode os testes apos cada corte.
```
