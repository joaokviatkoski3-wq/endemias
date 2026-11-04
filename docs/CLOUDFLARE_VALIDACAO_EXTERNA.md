# Validacao externa e conector limitado — 04/11/2026

Continuidade autorizada pelo usuario apos o piloto publico. Producao oficial
permanece 1.75.0 enquanto a preparacao 1.76.0 e validada.

## Testes ponta a ponta no piloto

`scripts/testar_piloto_externo.py` usa exclusivamente o hostname fixo
`https://piloto.vsatt.com.br`, exige marcador local de SQLite sintetico e
le a senha ficticia do arquivo ignorado, sem exporta-la/cookies/respostas.
Aceites automatizados sao somente das contas ficticias do piloto. Nao e
registro de consentimento/aceite de usuario real.

Confirmados em 04/11:

- Login/termos/cookie seguro para admin, operador e visualizador ficticios.
- Paginas principais, formularios/RG, territorializacao, importacao e Central.
- Tres exportacoes XLSX baixadas e reabertas; PDF baixado e reaberto.
- Visualizador sem administracao/escrita; rascunho de outro usuario retorna
  404 e sobrescrita alheia e recusada. Rascunho de ensaio removido ao final.
- Upload XLSX real pela borda e conclusao SSE; primeiro bloco em cerca de
  0,06 s no ensaio. Planilha sem registros de visitas, sem confirmar importacao.
- Arquivo falso recusado e requisicao sem CSRF recusada. Respostas privadas
  sem cache. Isso nao equivale a ensaio de importacao real/longa ou de 95 MiB.

Foi corrigida a preparacao do piloto para copiar o mapeamento publico
`config.json` para a pasta sintetica quando ausente. O banco ja existente e
suas credenciais/aceites sao preservados. Nao copia configuracao/token Kobo.

## Pacote para reduzir privilegios do conector

cloudflared instalado 2026.10.7. Consulta sanitizada confirmou inicializacao
automatica, identidade LocalSystem, argumento `--token-file` e ausencia de
token literal nos argumentos. O instalador oficial atual ja protege o arquivo
`C:\ProgramData\cloudflared\token`; nao foi necessario ler seu conteudo.

`scripts/endurecer_tunnel_windows.py --aplicar`, com administrador, altera
somente a identidade para `NT SERVICE\Cloudflared`, habilita o SID do servico
e limita privilegios a `SeChangeNotifyPrivilege`. A conta virtual nao precisa
de senha administrada. Preserva executavel, argumentos, token, inicio automatico
e recuperacao do servico existentes. Nao altera o Jellyfin ou a conta Cloudflare.

Diretorio do token fica somente RX e token somente R para o SID exclusivo do
conector, alem de SYSTEM/administradores. Sem permissao de escrita nas chaves
ou concessao de leitura a contas comuns/identidade da aplicacao.

Snapshot de conta/SID/privilegios e ACLs fica privado em
`C:\ProgramData\EndemiasTunnel\retorno-<data-hora>`. Nao contem valor do token.
O helper para/reinicia apenas Cloudflared, verifica SID e ausencia de privilegios
administrativos no processo real e aguarda login publico 200/1.76.0. Em falha,
tenta restaurar conta/ACLs e a conexao anterior. `--reverter` permite retorno
posterior de uma aplicacao concluida, sem restaurar banco ou mudar rotas.
Resultado sanitizado em `C:\ProgramData\EndemiasTunnel\resultado.json`.

Quatro testes focados do helper passaram, junto aos sete anteriores da conta
web. Cobre recusa de token literal, escopo de caminho, ausencia de abertura do
token e contrato da API: senha NULL para conta virtual, sem mudar ImagePath.
Conferir resultado administrativo antes de declarar aplicacao concluida.

**Aplicado em 04/11:** Cloudflared executa como `NT SERVICE\Cloudflared`,
sem administrador e com privilegios reduzidos; SID real do processo conferido,
token somente leitura para o conector, argumentos/inicio automatico preservados.
Piloto respondeu 200/1.76.0 apos a reconexao. Resultado privado em ProgramData.
A primeira inspecao pediu TOKEN_DUPLICATE desnecessariamente e foi negada;
a checagem foi corrigida para TOKEN_QUERY e grupos do token real. Conta/ACLs
anteriores e piloto foram recuperados antes da tentativa concluida.

## Preparacao da ativacao oficial

- Usuario escolheu `endemias.vsatt.com.br` como endereco oficial; root disponivel
  para futura entrada geral, ambiental somente quando a cisao for implementada.
- Usuario confirmou que a equipe ainda nao usa o formulario RG offline.
- Consulta administrativa somente leitura: 7 contas ativas, 4 administradores,
  papel SQL sem privilegios administrativos, migracoes anteriores integras,
  somente 0030 pendente. Contas/permissoes reais preservadas, sem mudar senhas.
- IP local configurado manualmente, DHCP desabilitado. Entrada local prevista
  no mesmo IP/porta 5000 e localhost; entrada Tunnel somente 127.0.0.1:5001.
- Wrapper nativo preparado para Waitress, sem alterar a senha/tarefa existente.
  Corrigido isolamento de argv: servir.py recebe somente seus argumentos,
  nao os parametros --config do wrapper. Quatro regressões especificas passaram.
- Antes de aplicar: backup, parada da tarefa, integracao do codigo validado,
  somente migracao 0030, reducao da escuta PostgreSQL a localhost, ensaio sob
  identidade final e confirmacao das duas entradas. Retorno preserva o banco e
  os aceites eventualmente registrados; nunca restaurar dados automaticamente.

## Pacote de ativacao local

`scripts/ativar_acesso_externo_windows.py` exige commits completos de origem
e release, master limpa e pertencimento do commit de origem ao pacote.
Preserva a tarefa e sua credencial; atualiza somente configuracao/entrada
nativa ja protegidas, com `server=waitress`, hostname escolhido e duas portas.
Cria dump previo com catalogo validado e snapshot privado de configuracoes.
Com aplicacao parada, registra assinaturas/contagens de tabelas anteriores,
reduz listen_addresses para localhost, integra por fast-forward e aplica
somente 0030 se pendente. Chave, Kobo, config e SQLite congelado preservados.

Antes de servir, usa a mesma tarefa limitada em modo de ensaio: verifica
permissoes/banco/backup e login do perfil externo sem registrar aceite real.
Depois serve LAN/loopback:5000 e origem Tunnel somente 127.0.0.1:5001,
confere login 1.76.0 nas duas entradas e assinaturas das tabelas anteriores.
Em falha, retorna codigo/configuracao/tarefa e escuta anteriores, confirma
login 1.75.0 e mantem o banco/0030/aceites. Resultado sanitizado fica em
`C:\ProgramData\EndemiasWeb\ativacao176-resultado.json`.

Regressao final apos conciliar a master: **910 testes passaram, sete ignorados**
em massa sintetica e na venv dedicada. Cinco testes de ativacao passaram
separadamente, incluindo preservacao de chave/configuracao, recusa de host/IP
fora do escopo, argv do wrapper, exigencia Waitress e mudanca pontual do
postgresql.conf sem corromper CRLF. Navegador HTTPS descartavel confirmou RG
offline, desktop/390px, logout removendo pagina do cache e zero erros JS.

Esta etapa ativa somente a origem preparada localmente. Publicacao oficial
sera o encaminhamento de `endemias.vsatt.com.br` para 127.0.0.1:5001 no painel.

## Referencias

- [Cloudflare — token-file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file)
- [Fonte da versao instalada — arquivo protegido do token no Windows](https://github.com/cloudflare/cloudflared/blob/2026.10.7/cmd/cloudflared/windows_service.go)
- [Microsoft — conta virtual e senha NULL](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-changeserviceconfigw)
