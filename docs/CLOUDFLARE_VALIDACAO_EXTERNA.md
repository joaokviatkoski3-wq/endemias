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

## Referencias

- [Cloudflare — token-file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file)
- [Fonte da versao instalada — arquivo protegido do token no Windows](https://github.com/cloudflare/cloudflared/blob/2026.10.7/cmd/cloudflared/windows_service.go)
- [Microsoft — conta virtual e senha NULL](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-changeserviceconfigw)
