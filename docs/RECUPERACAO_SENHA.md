# Recuperacao de senha assistida — 1.77.0

Solicitada pelo usuario em 04/11/2026. Preparada em
`C:\endemias-recuperacao-senha`, branch `codex/recuperacao-senha`.
Consultar o estado vivo antes de interpretar esta preparacao como implantada.

## Uso

- Login oferece **Esqueci minha senha**, com orientacao para procurar o
  responsavel pelo sistema no setor. Nao coleta identificadores ou cria
  pedidos publicos; nao ha envio automatico por e-mail/WhatsApp.
- Em **Gestao de Usuarios**, administrador pode escolher **Gerar link de
  recuperacao** para uma conta ativa. Confirmar identidade antes de entregar
  o link em conversa privada. A senha definitiva e escolhida pelo titular.
- Link vale por 15 minutos e uma utilizacao. Gerar outro substitui o anterior.
  O reset aleatorio ja existente permanece disponivel.
- A pessoa digita/confirma a nova senha, com politica vigente (minimo dez
  caracteres), e entra normalmente. Nao ha login automatico. Sessoes anteriores
  dos perfis local e externo sao invalidadas pelo vinculo com o hash da senha.

## Protecoes

Token aleatorio de 32 bytes, SHA-256 no banco, unico por conta e vinculado
ao hash da senha vigente. Conta inativa, administrador emissor inativo/sem
papel admin, troca de senha, link substituido, usado ou expirado impedem uso.
Geracao nao troca a senha nem invalida a sessao atual do titular.

Token e fragmento do link (`#...`), nunca caminho/query HTTP. Pagina extrai
o fragmento, remove-o do endereco e envia o token somente no corpo POST com
CSRF. Referrer-Policy no-referrer, sem recursos externos, no-store e noindex.
Origem dos links configurada no servidor (`RECOVERY_BASE_URL`, HTTPS), padrao
`https://endemias.vsatt.com.br`; nunca derivada do Host recebido.

Limites persistentes: dez falhas de recuperacao por IP e vinte emissoes por
administrador em quinze minutos. Solicitar/errar recuperacao nao desativa
a conta. Limite geral de falhas por IP de login continua vigente; recuperacao
concluida limpa somente as falhas usuario/IP correspondentes ao titular.

Auditoria registra emissor, titular e conclusao, sem senha/token/link. Auditoria
e alteracao de senha/consumo participam da mesma transacao: falha desfaz ambos.
SQLite usa BEGIN IMMEDIATE; PostgreSQL bloqueia a linha do titular FOR UPDATE.
Consumos simultaneos resultam em uma unica troca.

## Banco e implantacao

Migracao aditiva **0031_recuperacao_senha.sql** cria uma tabela, sem alterar
dados anteriores. SQLite cria a estrutura ao usar a funcionalidade; PostgreSQL
exige migracao antes de servir a versao nova. Nao repetir migracoes aplicadas.

`scripts/ativar_recuperacao_senha_windows.py` exige master limpa/commit exato,
versao 1.76.0/Waitress e mesma identidade limitada. Faz backup/catalogo, para
somente a tarefa web, integra por fast-forward, aplica somente 0031, compara
dados anteriores, ensaia conta limitada e inicia 1.77.0 nas duas entradas.
Preserva ambiente, credenciais, Cloudflared, firewall, PostgreSQL e caminhos.
Em falha retorna codigo/configuracao, mantendo banco/migracao/dados novos.
Nunca restaura dump automaticamente. Relatorio privado em
`C:\ProgramData\EndemiasWeb\ativacao177-resultado.json`.

## Validacao

Regressao geral com runtime dedicado e massa sintetica: **928 testes passaram,
sete ignorados**. Testes focados adicionais do limite de emissao, auditoria/
limpeza de falhas e preservacao da configuracao de ativacao tambem passaram.

- Testes unitarios/rotas sobre contas ficticias: expiracao, substituicao,
  vinculo de senha, autorizacao, CSRF, ausencia de segredos na auditoria,
  rollback e consumo simultaneo unico.
- PostgreSQL descartavel, loopback:55439, banco endemias_teste: SQL 0031,
  expiracao, substituicao, transacao e dois consumidores reais concorrentes.
- Chromium descartavel, loopback:5004, SQLite ficticio: administrador gera
  link pela interface, confirmacao divergente preserva link, troca correta,
  sessao antiga revogada, novo login e recusa de reutilizacao. CSRF real,
  viewport 390px sem overflow e zero erros JavaScript. Token ausente de
  todos os enderecos HTTP observados. Credenciais reais nao utilizadas.

Referencia: [OWASP — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).
