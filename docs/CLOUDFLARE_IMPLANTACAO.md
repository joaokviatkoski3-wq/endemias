# Acesso externo — preparação 1.76.0

Atualizado em 03/11/2026. Branch `codex/preparar-cloudflare`, worktree
`C:\endemias-cloudflare`, derivada da master `f7a98a0`.

## Escopo e decisões confirmadas

- Domínio comprado pelo usuário: `vsatt.com.br`. A conta Cloudflare também
  atende seu Jellyfin; não alterar o domínio, o Tunnel ou regras daquele serviço.
- Login pelo próprio sistema, sem Cloudflare Access, Google ou código por e-mail.
  O Access é opcional e foi dispensado pelo usuário nesta preparação.
- Referência inicial: 20–30 usuários, normalmente menos de dez simultâneos;
  considerar expansão. Não há limite artificial de contas nem separação futura
  de Endemias/Vigilância Ambiental implementada neste lote.
- Usuário autorizou revisar, corrigir e testar a segurança em ambiente isolado.
  Pediu também um termo de responsabilidade no primeiro acesso.
- **Nenhuma publicação, instalação de serviço, mudança de firewall/PostgreSQL,
  migração em produção, integração na master ou reinício oficial neste lote.**
- Produção documentada continua em 1.75.0. A versão 1.76.0 é código preparado,
  não uma declaração de versão ativa. Dados e plano real do LIRAa não são massa
  de teste. Nenhum dado/credencial real foi copiado para o ambiente experimental.

## Diagnóstico e correções

| Achado | Tratamento na branch |
| --- | --- |
| Inicialização com Werkzeug em todas as interfaces | `servir.py` usa Waitress; por padrão apenas 127.0.0.1, 16 threads, limite de conexões e requisição. Perfil externo recusa outra interface e `python app.py`. |
| Confiança ampla no primeiro X-Forwarded-For quando habilitada | Perfil externo aceita somente conector em loopback, valida CF-Connecting-IP, exige HTTPS, descarta cabeçalhos Forwarded/X-Forwarded e valida Host exato. |
| Sessões sem vínculo com senha atual | Novos logins limpam sessão anterior e recebem HMAC da credencial; troca/reset invalida cookies anteriores. Perfil externo exige esse vínculo e cookie `__Host-endemias`, Secure, HttpOnly e SameSite=Lax. |
| Limite apenas por combinação IP/usuário e incremento sujeito a corrida | Mantido limite de cinco por combinação, acrescentado limite de 50 falhas por IP em quinze minutos; incremento atômico e limpeza de tentativas expiradas. Custo de senha também executado para conta inexistente. |
| Formulário consultável pelo ID sem verificar dono | Consulta retorna 404 para outra conta, com exceção do administrador. |
| UUID permitia sobrescrita alheia ou de formulário já revisado | Proprietário, tipo e estado são verificados; UPDATE condicional impede corrida com revisão/oficialização. Envio de campo aceita apenas rascunho/enviado. |
| Service Worker guardava qualquer navegação e arquivos baixados | Cache restrito a recursos estáticos e RG de campo; sair/trocar conta invalida a página offline. Na origem externa, IndexedDB é separado por usuário. |
| Risco de cache de respostas autenticadas na borda/navegador | Respostas privadas recebem private, no-store e Vary: Cookie. Configurar também bypass de cache no hostname na Cloudflare, sem Cache Everything. |
| Mensagens toast interpretadas como HTML | Texto variável passa a usar textContent. |
| Redirecionamento pós-login aceitava formas ambíguas | Rejeita barras invertidas, endereços de rede, controles e mudança de HTTPS para HTTP. |
| Rotas futuras poderiam esquecer autenticação | Barreira geral exige usuário ativo, com exceção explícita de login, logout e recursos públicos necessários. Permissões de cada módulo continuam valendo. |
| Planilha ZIP pode ser pequena comprimida e excessiva ao abrir | Limite de 512 MiB descompactados e dez mil entradas; recusa planilha criptografada. Não executa macros. |
| Upload local de 220 MiB supera plano Free na borda | Perfil externo limita o corpo a 95 MiB (99.614.720 bytes), incluindo multipart; erro 413 amigável. Perfil local conserva seu limite. |
| Importação SSE pode ficar silenciosa | Comentário inicial imediato e heartbeat a cada quinze segundos; não altera as mensagens de progresso ou os dados importados. |
| Componentes instalados com avisos conhecidos | Atualizados apenas na venv isolada: Pillow 13.0.0, Werkzeug 3.1.9, certifi 2026.10.23 e urllib3 2.8.0; pip 26.3 para ferramentas. Requisitos mínimos atualizados. |

O código não impõe um total de usuários. As 16 threads são um limite de trabalho
simultâneo do servidor, não de contas. Requisições adicionais aguardam; aumentar
threads indiscriminadamente pode sobrecarregar CPU e conexões PostgreSQL.

## Termo de ciência e responsabilidade

- Texto em `app_core/termos_uso.py`, versão `2026-11-03.1`, com SHA-256 do
  conteúdo e versão. É compromisso do usuário sobre finalidade, sigilo,
  exportações, senha, aparelho/offline e comunicação de incidentes.
- Não é consentimento de pacientes, garantia contra vazamento, transferência
  das obrigações da instituição nem certificação de conformidade com a LGPD.
- Checkbox desmarcado; aceite explícito por POST com CSRF e conferência da
  versão/hash apresentados. É possível sair sem aceitar; páginas e APIs de
  trabalho ficam bloqueadas até o aceite, inclusive para administradores.
- Registro durável em `usuarios_termos`: usuário, versão, hash, cópia integral
  do texto, horário UTC e IP validado. Sobrevive ao logout e ao novo login.
  Mudar conteúdo/versão pede novo aceite; atualizar texto exige nova versão.
- Migração aditiva **0030_usuarios_termos.sql**, preparada, **não aplicada em
  produção**. Não há alteração nas tabelas operacionais existentes.
- Habilitado obrigatoriamente no perfil externo. Para ensaio local independente:
  `ENDEMIAS_TERMOS_USO=1`. A versão normal/local não o ativa automaticamente
  neste lote para evitar afetar a instalação oficial antes da integração.
- Conferir texto e canal de incidentes com a gestão responsável antes do uso
  institucional; a redação implementada usa responsável pelo sistema/chefia.

## Configuração preparada

Não executar estes exemplos na instalação oficial antes da janela autorizada.
Não gravar senhas ou token do Tunnel no Git.

```powershell
# Exemplo do futuro processo externo, com banco/credencial configurados
# separadamente para a instalação aprovada.
$env:ENDEMIAS_ACESSO_EXTERNO = '1'
$env:ENDEMIAS_ALLOWED_HOSTS = 'vsatt.com.br'
$env:ENDEMIAS_BIND = '127.0.0.1'
$env:ENDEMIAS_THREADS = '16'
python servir.py --validar
python servir.py
```

Perfil externo falha fechado sem host exato, sem chave de sessão de pelo menos
32 bytes ou com interface de escuta diferente de 127.0.0.1. `--validar` não abre
porta, mas importa a aplicação e prepara seus diretórios; não substitui conferir
o destino do banco e os arquivos de credenciais antes da execução.

O conector cloudflared deve estar no mesmo computador, encaminhando
`vsatt.com.br` para `http://127.0.0.1:5000`, preservando o Host público. Somente
o conector local pode alcançar esse listener. Não usar ProxyFix adicional,
trusted_proxy='*' ou aceitar o X-Forwarded-For fornecido pelo navegador.
Um acesso direto HTTP a esse processo será recusado; é intencional.

O exemplo acima descreve o modo somente externo da primeira etapa. Para a
preferência atual do usuário (acesso local preservado), preparar as opções de
duas entradas em `CLOUDFLARE_INFRAESTRUTURA.md`: LAN/localhost na porta 5000 e
Tunnel em 127.0.0.1:5001, com sessões separadas no mesmo processo e banco.

O launcher existente `scripts/iniciar_servidor.ps1` recebeu opções aditivas
`-Servidor waitress -AcessoExterno -AllowedHosts vsatt.com.br -Threads 16`.
O padrão continua Werkzeug/local. `-ValidarSomente`, com Waitress, valida sem
abrir porta. Manter os parâmetros existentes de backend, banco, usuário,
PythonPath e arquivo pgpass da instalação aprovada. Nenhuma tarefa foi
registrada ou alterada por essa edição do arquivo na worktree.

Cloudflare: forçar HTTPS no hostname; não criar Cache Everything e preparar
bypass de cache para toda a aplicação. O domínio pode continuar com DNS na
Cloudflare mesmo se o piloto do sistema for interrompido. HSTS inicial de um
dia, sem includeSubDomains e sem preload.

### Acesso da equipe na rede local

**Atualização de 03/11, etapa seguinte:** usuário preferiu preservar acesso
local. A opção de duas entradas no mesmo processo foi implementada e ensaiada;
ver `CLOUDFLARE_INFRAESTRUTURA.md`. A proposta original a seguir documenta o
modo somente externo; não é mais a única alternativa preparada.

A proposta para ativação é usar o mesmo endereço HTTPS também dentro do setor.
O perfil externo não preserva login por `http://IP:5000`: o cookie Secure e a
escuta local são incompatíveis com esse acesso direto. Isso deve ser validado
com a equipe antes da troca. Enquanto esta preparação não for integrada,
o acesso local oficial atual segue funcionando como antes.

Esse desenho depende de energia, computador, conexão de internet e Cloudflare.
Se acesso local sem internet for indispensável, preparar e ensaiar uma solução
específica antes da ativação; não habilitar cookies inseguros ou um listener
desprotegido para contornar o perfil externo.

## Ensaios executados e limites da evidência

- Python: `python -m unittest discover -s tests -t .`, executado pela venv,
  sempre sobre cópia temporária da massa **sintética** criada pelo script
  `scripts/preparar_massa_web_teste.py`. Não usa o SQLite congelado como origem.
  Resultado: **890 testes, sem falhas, seis ignorados**, sobre massa fictícia.
  Ajustes finais de cabeçalhos estáticos foram conferidos também pela suíte
  específica de segurança: **14 testes sem falhas**, depois da regressão geral.
- Regressões específicas: propriedade/estado de formulários, ausência de login,
  rota nova sem decorator, reset de senha, concorrência no contador de falhas,
  Host/IP/HTTPS falsos, termo/CSRF/persistência/nova versão e SSE.
- JavaScript: cache não guarda relatórios/anexos/APIs; RG abre offline; troca
  de conta/logout removem a página; novos dados externos separados por conta.
  Oito arquivos de testes JS passaram, incluindo os fluxos anteriores de
  laboratório/plano/mapa LIRAa, microáreas e exportação RG.
- PostgreSQL 18 **descartável**, localhost:55434, banco endemias_teste, conta
  sintética: migração 0030 em tabelas temporárias, aceite idempotente,
  formulários e contador atômico. Integração LIRAa existente ensaiada também,
  incluindo importação, leitura, notificações, relatórios e exclusão integrada.
- Backup PostgreSQL de dados fictícios criado com pg_dump e restaurado com
  pg_restore em outro banco descartável; conferência de conteúdo retornou
  verdadeiro. Não foi uma restauração ou cópia do banco oficial.
- HTTP real com Waitress: login, cookie Secure/HttpOnly, CSRF, primeiro aceite,
  página inicial e resposta 413 pelo limite de corpo.
- Carga HTTP sintética (consultas/páginas leves, SQLite isolado):

| Requisições concorrentes | Total de requisições | Erros | Mediana | p95 |
| --- | --- | --- | --- | --- |
| 10 | 30 | 0 | 110 ms | 153 ms |
| 30 | 90 | 0 | 340 ms | 505 ms |
| 60 | 180 | 0 | 829 ms | 934 ms |

Essas medições não dimensionam o uso real: não incluem internet/Cloudflare,
volume real de dados, execução concorrente de relatórios/importações ou o
comportamento do PostgreSQL oficial. Não garantem capacidade para sessenta
usuários reais simultâneos. Repetir uma carga representativa antes de ampliar
o público; manter as consultas e permissões atuais na expansão gradual.

- Navegador de ensaio: termo em 1280 px e 390 px, sem rolagem horizontal;
  confirmação, logout e novo login sem repetir a mesma versão.
- RG de campo abriu offline no navegador sem erros JavaScript, com recursos
  estáticos completos; logout removeu a página do Cache Storage. Scripts de
  reprodução: `scripts/testar_http_web.py` e `scripts/testar_interface_web.py`.
  O segundo requer Playwright/Chromium apenas no ambiente de desenvolvimento.
- Auditoria de dependências instaladas na venv: pip-audit sem vulnerabilidades
  conhecidas após atualização; pip check sem conflitos. É um retrato da base
  consultada, não garantia de ausência de falhas.
- Não houve teste do Tunnel real, reconexão/boot do conector, latência externa,
  upload grande pela borda ou importação superior ao timeout da Cloudflare.
  Heartbeat foi preparado; compatibilidade ponta a ponta ainda exige piloto.
- Não são ensaiados ataques de uma pessoa com controle do Windows/navegador.
  Offline deliberadamente mantém dados no aparelho; separação por usuário não
  equivale a criptografia do IndexedDB. Encerrar sessão remove a página offline,
  mas preserva rascunhos para evitar perda de trabalho.
- Inspeção e regressões não constituem certificação de segurança. A política
  CSP ainda permite scripts inline por compatibilidade com a interface atual;
  não foi feita conversão completa para nonces nem teste de penetração externo.

### Preservação da instalação oficial

Ao final dos ensaios, GET em `http://127.0.0.1:5000/login` retornou HTTP 200
com 1.75.0. `C:\endemias` permaneceu limpa em `f7a98a0`. O SQLite congelado
manteve SHA-256 `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`
antes/depois. A instância PostgreSQL descartável foi encerrada; o serviço
oficial não foi reiniciado. Não houve conexão dos ensaios ao banco de produção.

## Condições operacionais antes de qualquer ativação

Diagnóstico atualizado de Windows, tarefa SYSTEM, pg_hba e rede do Tunnel em
`CLOUDFLARE_INFRAESTRUTURA.md`. A tarefa já foi consultada pelo usuário como
administrador; a falha de acesso descrita no histórico abaixo foi resolvida
para a coleta, sem alterar sua identidade ou ação.

1. Conferir a master mais recente e coordenar a integração com a frente LIRAa.
   Templates recarregam em produção: não integrar este lote com o serviço
   ativo, pois há rotas e migração novas. Não reaplicar a 0029 nem mudar plano,
   sorteios, ACS ou respostas Kobo como parte dessa implantação.
2. Confirmar suporte de segurança do Windows 10 Pro 19045/ESU. A presença do
   pacote KB5126256 não prova licença/cobertura efetiva. Essa cobertura ainda
   não foi demonstrada. Planejar alternativa suportada se necessário.
3. Conferir identidade/ação real da tarefa oficial em sessão administrativa.
   Consulta desta sessão retornou acesso negado. Não assumir que a identidade
   histórica SYSTEM continua válida; preparar conta restrita e permissões
   sobre dados/chaves/credenciais e diretórios necessários.
4. PostgreSQL continua escutando em 0.0.0.0/:: na porta 5432 na inspeção inicial.
   Restringir a localhost se não houver consumidores remotos legítimos, após
   verificar configuração, backup e impacto. Não publicar essa porta.
5. Revisar contas ativas, necessidade de permissões e senhas individuais; sem
   cadastro público. Login existente passa a ser a barreira exposta à internet.
   Limites locais não eliminam ataques distribuídos; preparar regra de taxa
   apropriada na borda para /login sem interferir nos demais serviços da conta.
6. Validar a forma de acesso local descrita acima e o texto institucional do
   termo. Definir responsáveis e tratamento dos registros de aceite/backups.
7. Validar backup e restauração em instância isolada, preservando ACL e chaves;
   manter tarefa/ambiente anterior exportados e pacote de retorno disponível.
8. Confirmar DNS ativo, DNSSEC com a configuração fornecida pela Cloudflare e
   regras apenas de vsatt.com.br. DNSSEC não foi ativado pelo agente.

### Sequência proposta de implantação e retorno

Na janela autorizada: verificar Git/backup; parar serviço oficial; integrar o
código validado e instalar dependências em ambiente próprio; aplicar somente a
0030 pendente; configurar processo Waitress/conta restrita; validar localmente
com headers de ensaio; configurar cloudflared e hostname, HTTPS e cache; testar
duas contas com permissões diferentes antes de liberar os demais usuários.

Critérios: identidade/IP corretos, login/logout e reset; aceite uma vez por
versão; recusa de rotas/anexos sem autorização; laboratório, LIRAa, mapas,
relatórios/PDF/XLSX e importação sintética; uploads dentro/fora do limite;
reconexão e reinicialização de serviços; acesso da equipe; contagens/assinaturas
dos dados anteriores preservadas. Fazer piloto pequeno com acompanhamento.

Se falhar: suspender apenas o novo hostname/conector, restaurar tarefa e
ambiente/código anteriores e validar o acesso local. Não alterar o Jellyfin.
A tabela aditiva usuarios_termos pode permanecer para não perder os aceites;
não apagar dados ou restaurar banco operacional mecanicamente. Uma restauração
do banco requer plano e autorização próprios. Não é necessário desfazer toda
a delegação DNS para interromper o acesso do sistema.

## Referências consultadas

- [Flask — segurança](https://flask.palletsprojects.com/en/stable/web-security/)
- [Waitress — argumentos](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
- [Cloudflare — cabeçalhos](https://developers.cloudflare.com/fundamentals/reference/http-headers/)
- [Cloudflare — limite de upload](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/)
- [Cloudflare — limites de conexão](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)
- [LGPD, texto atualizado — Câmara dos Deputados](https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html)
- [ANPD — perguntas frequentes](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes)
