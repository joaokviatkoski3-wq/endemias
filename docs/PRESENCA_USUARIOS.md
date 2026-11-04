# Presenca de usuarios — 1.78.0

Solicitada em 04/11/2026. Preparada em `codex/presenca-usuarios`, worktree
`C:\endemias-presenca`. Conferir o estado vivo antes de declarar implantada.

## Uso e significado

Gestao de Usuarios, somente para administradores, mostra **Presenca**,
**Ultima vez online** e total de pessoas online, atualizados a cada 30 segundos.
Online significa sinal autenticado recebido ha no maximo 120 segundos de uma
pagina visivel. Sinal inicial ao abrir/retomar pagina; em segundo plano ou sem
rede o temporizador pausa. Fechar navegador/desconectar resulta em offline
depois da janela, sem depender de eventos de fechamento pouco confiaveis.

Logout encerra somente aquela sessao; outros aparelhos permanecem validos.
Varias abas compartilham a identidade da sessao e contam uma pessoa. Horarios
em America/Sao_Paulo: Agora, Hoje, Ontem, data completa ou Sem registro.
Ausencia de rede/erro na consulta aparece como Sem atualizacao, sem inferir
offline a partir da falha. E um indicador aproximado; celulares podem suspender
paginas. A coleta comeca nesta versao, sem converter logins antigos em presenca.
Paginas ja abertas na versao anterior precisam ser recarregadas/navegadas.

## Implementacao e protecoes

- POST `/api/presenca`: autenticacao/CSRF, identidade e usuario derivados da
  sessao assinada, ignorando IDs/horarios fornecidos pelo cliente. Permitido
  tambem na leitura do termo e para contas exclusivas do laboratorio.
- GET `/admin/usuarios/presenca`: somente administrador, no-store; retorna
  apenas IDs de usuarios, estado e horarios, sem hashes/identidades de sessao.
- Cada login recebe nonce aleatorio; sessoes anteriores usam derivacao estavel
  do CSRF da sessao. Banco armazena somente HMAC da identidade por escopo
  local/externo, horario e vinculo SHA-256 com a senha atual.
- Troca/reset de senha ou desativacao impede considerar sessoes antigas online.
  Troca da propria senha renova nonce para a sessao atual autenticada.
- Tombstone de logout impede reabrir presenca com heartbeat atrasado, inclusive
  em concorrencia e se logout chegou antes do primeiro sinal.
- Gravacao no maximo a cada 20 segundos por sessao reduz duplicacao entre abas.
  Sessoes antigas sao limpas apos 24 horas; ultimo sinal por usuario permanece.
  Nao ha gravação de trilha de paginas, cliques, IP ou localizacao nesta rotina.
- Interface de sessao preserva a assinatura/escopos existentes e impede que
  heartbeat/consulta automatica renovem cookies permanentes sem modificacao
  real da sessao. Polling nao mantem autenticacao indefinidamente.
- Falha de presenca nao interrompe formularios nem impede logout. Service
  worker nao armazena APIs ou POSTs, portanto sinais nao sao enfileirados offline.
- Ajuste relacionado: menu do usuario abre no primeiro clique, consultando o
  estilo efetivo; antes a primeira abertura podia apenas definir display:none.

## Banco e ativacao

Migracao aditiva **0032_presenca_usuarios.sql**, duas tabelas e um indice.
SQLite cria ao usar a rotina; PostgreSQL exige migracao antes da versao nova.
Nao altera dados/cadastros anteriores nem repete migracoes aplicadas.

`scripts/ativar_presenca_windows.py` usa o executor ja validado, parametrizado
com origem 1.77.0, destino 1.78.0, somente 0032. Exige master limpa/commits
exatos; backup/catalogo, parada da tarefa, fast-forward, migracao, assinaturas
anteriores, ensaio da identidade limitada e login local/origem externa.
Mesma tarefa/credencial/ambiente, sem alterar Cloudflared, PostgreSQL ou firewall.
Em falha, retorno de codigo/configuracao preserva banco/migracao/dados novos,
sem restaurar dump. Resultado privado em
`C:\ProgramData\EndemiasWeb\ativacao178-resultado.json`.

## Validacao

- **949 testes gerais passaram, sete ignorados**, sobre massa sintetica e
  runtime dedicado, alem de testes focados de pacote/conta exclusiva/termo.
- PostgreSQL descartavel, 127.0.0.1:55440/endemias_teste: SQL 0032, aparelhos,
  expiracao, corrida entre logout/sinais, senha e limpeza mantendo ultimo online.
- Chromium descartavel/127.0.0.1:5005/SQLite ficticio: CSRF real, varios
  aparelhos e abas, logout parcial, pausa oculta, expiracao e retomada visivel,
  datas em Brasilia, Sem registro, cookie sem renovacao por polling, menu e
  celular 390px sem overflow da pagina. Zero erros JavaScript; scripts tambem
  validados por node --check. Nenhuma credencial real utilizada.
