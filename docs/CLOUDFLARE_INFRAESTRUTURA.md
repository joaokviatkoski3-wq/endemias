# Infraestrutura e piloto local — 03/11/2026

Versão vigente **1.80.0**, segurança atualizada em 04/11 às 14h35,
mesma infraestrutura. Ver `CORRECOES_SEGURANCA_180.md`; histórico 1.76 abaixo.

**Estado posterior, 04/11/2026:** produção local 1.76.0/Waitress ativa na
mesma tarefa EndemiasWeb, LAN/loopback:5000 e origem externa só 127.0.0.1:5001.
PostgreSQL restrito a localhost, apenas 0030 aplicada, backup validado e 90
tabelas anteriores preservadas. Cloudflared agora usa `NT SERVICE\Cloudflared`
limitado, Running/Auto. `endemias.vsatt.com.br` publicado, HTTPS e retorno após
reinício de 09h49 confirmados às 09h58. Piloto continua fictício/manual. O diagnóstico e as versões
anteriores abaixo são históricos; ver `CLOUDFLARE_VALIDACAO_EXTERNA.md`.

Continuação da preparação `1.76.0`, branch `codex/preparar-cloudflare`.
O usuário autorizou a próxima etapa e pediu preservar o acesso local se viável.
Este registro complementa `CLOUDFLARE_IMPLANTACAO.md`. O piloto fictício foi
publicado posteriormente; o sistema oficial continua somente na rede local.

**Etapa autorizada posteriormente:** usuário pediu aplicar a execução limitada
e a proteção de código/chaves. Pacote e escopo em `CLOUDFLARE_CONTA_LIMITADA.md`.
Preserva a versão oficial 1.75.0, sem ativar a 1.76.0 ou publicar o Tunnel.
**Aplicado e confirmado às 16h05:** tarefa limitada EndemiasWeb, Python próprio,
código/chaves protegidos e backup validado; HTTP 200/1.75.0. Usuário confirmou
login por outro aparelho da LAN. Sem publicação ou mudança de firewall. O
fechamento naquele documento substitui o estado anterior de tarefa SYSTEM e
ACLs amplas registrado abaixo como diagnóstico histórico.

## Piloto externo confirmado — atualização posterior de 03/11

- Usuário criou o Tunnel `vsatt-piloto`, instalou o conector pelo MSI/comando
  oficial e configurou `piloto.vsatt.com.br` para `http://127.0.0.1:5003`.
  Confirmou que o endereço abriu no navegador.
- Consulta local confirmou serviço `Cloudflared` Running/Auto, como
  LocalSystem. É distinto da tarefa EndemiasWeb limitada. Revisar identidade
  e proteção do token do conector antes de publicar produção; não presumir
  que ele herdou o endurecimento da aplicação. Não exportar ImagePath/token.
- Listener 5003 continua só loopback, no processo de `scripts/piloto_web.py`.
  Marcador de massa sintética conferido. Não foi apontado para a porta 5000
  ou para o PostgreSQL oficial.
- HTTPS público real: `/login` HTTP 200 com 1.76.0; `/api/formularios` HTTP 401
  sem login; `/` redireciona ao login. Respostas com `private, no-store`,
  Cloudflare `CF-Cache-Status: DYNAMIC`, CSP e HSTS de um dia; cookie de login
  `__Host-endemias` com Secure/HttpOnly. Nenhuma credencial foi enviada nesse
  teste. Isso não prova ausência de outras falhas ou cobertura de todas as rotas.
- Usuário confirmou login fictício, termo e saída/novo login no endereço
  público em 03/11. Testes de funções ainda pendentes. Credencial só no arquivo local ignorado
  `.venv/piloto-web/acesso.local.txt`; não usar contas reais nesse ambiente.
- O piloto é um processo sem autostart; após fechar/reiniciar o computador,
  pode ser necessário iniciá-lo por `piloto_web.bat`. O serviço do conector
  automático não inicia a aplicação piloto. Produção segue 1.75.0/EndemiasWeb.

### Retomada após reinício em 04/11

Windows reiniciado às 08h05. Cloudflared estava Running/Auto e a produção
respondia 200/1.75.0; portas 5002/5003 não tinham listener. O piloto público
retornou 502 porque a aplicação de ensaio, ainda manual, não estava iniciada.
Iniciado novamente `scripts/piloto_web.py` com os mesmos recursos fictícios.
Confirmados listeners somente em 127.0.0.1:5002/5003, `/login` público com
200/1.76.0 e API sem login 401, respostas privadas sem cache. Sem nova
configuração de serviço/tarefa, DNS, firewall, produção ou banco real.
Para próximos reinícios, iniciar `piloto_web.bat` na worktree; a tarefa
automática da produção e o serviço automático do Tunnel são independentes.

## Diagnóstico inicial (histórico; atualizações acima)

| Item | Evidência e conclusão |
| --- | --- |
| Produção | GET /login na porta 5000 retornou HTTP 200 e versão 1.75.0. Master continua em f7a98a0, sem alterações deste lote. |
| DNS público | Consultas a 1.1.1.1 e 8.8.8.8 ainda retornaram a.auto.dns.br/b.auto.dns.br. Usuário salvou bristol/cullen no Registro.br; confirmar término da transição antes do hostname público. |
| Windows | Windows 10 Pro 22H2, build 19045.6466. A referência de segurança consultada para outubro/2026 é 19045.7807, KB5126657. Usuário decidiu manter esse Windows por enquanto; a ausência de cobertura de segurança é uma limitação conhecida, não impedimento técnico para continuar a preparação. |
| ESU | Windows Professional aparece ativado, mas as entradas ESU consultadas não aparecem licenciadas. Consulta específica do ESU comercial ano 2 retornou LicenseStatus=0. Isso não deve ser confundido com simples ativação do Windows. Não foi feita compra, ativação de licença ou atualização. |
| Tarefa do servidor | Relatório executado pelo usuário como administrador confirmou SID S-1-5-18 (SYSTEM), nível HighestAvailable, launcher iniciar_servidor.ps1, backend PostgreSQL e banco oficial, sem opção Waitress. A versão real da tarefa foi confirmada, não inferida do histórico. |
| Serviço PostgreSQL | postgresql-x64-18 em execução automática como NetworkService; é distinto da tarefa da aplicação que roda como SYSTEM. |
| PostgreSQL — escuta | listen_addresses='*', porta 5432. Não foi alterado. |
| PostgreSQL — autenticação | pg_hba.conf contém apenas conexões locais/127.0.0.1/::1, todas com scram-sha-256, incluindo replicação. Portanto, escuta em todas as interfaces não significa que acessos remotos estão autorizados. |
| Firewall | Os três perfis Windows estão habilitados. Essa consulta não prova a política efetiva de uma porta específica; não foram criadas regras. |
| Rede do Tunnel | Conexões TCP de saída na porta 7844 passaram para region1.v2.argotunnel.com e region2.v2.argotunnel.com. UDP/QUIC e funcionamento de um Tunnel real não foram demonstrados. |
| cloudflared | Não encontrado no PATH nem na consulta de serviços da máquina. Não foi instalado/registrado nesta etapa. |

O pacote KB5126256 é de preparação de licenciamento; sua presença não prova
cobertura ESU ou atualização cumulativa instalada. A Microsoft distingue ESU
institucional/comercial do programa de consumo. A adequação do computador
deve ser definida com o responsável pela TI, sem presumir que o programa
pessoal se aplica ao computador do setor.

**Decisão posterior do usuário em 03/11:** manter o computador/Windows atuais,
aplicar as proteções viáveis e considerar VPS futuramente, quando houver
investimento. ESU, compra de computador ou migração não são exigências para
avançar nesta preparação. Isso não torna o Windows atualizado nem elimina o
risco de falhas sem correção. Tunnel, antivírus e conta restrita são camadas
adicionais; não substituem correções do sistema operacional. Nenhuma compra,
contratação de VPS ou migração foi autorizada por essa intenção futura.

O diagnóstico da tarefa não exporta argumentos completos, senhas, chaves,
XML bruto ou conteúdo de arquivos pgpass. O relatório fica somente na pasta
ignorada `.venv`, não no repositório remoto.

## Acesso local preservado sem duplicar produção

Implementada a opção de servir duas entradas no **mesmo processo**, com o
mesmo banco, anexos, rotinas e locks, compartilhando o pool do Waitress:

```text
Equipe do setor -> IPv4 privado:5000 e localhost:5000 -> entrada local
Internet -> Cloudflare -> cloudflared -> 127.0.0.1:5001 -> entrada externa
                                      mesmo processo / mesmo PostgreSQL
```

- Não há segundo cadastro, segunda produção, cópia de dados ou sincronização
  entre duas bases. O modo é opt-in; a instalação atual não foi modificada.
- Porta externa aceita somente conector em loopback, HTTPS encaminhado e
  hostname permitido. Nunca abrir a porta 5001 no roteador/firewall.
- Entrada local usa somente o IPv4 privado explicitamente configurado e o
  loopback. Não aceita bind curinga ou IP público. Confirmar IP estável/reserva
  DHCP antes da implantação; o código não modifica o roteador.
- A seleção da aplicação ocorre pela escuta real do servidor, não por um
  cabeçalho Host ou Forwarded que possa ser falsificado pelo visitante.
- Cookies têm nomes e chaves derivadas diferentes; um cookie da LAN não é
  aceito na entrada externa, nem o contrário. Cada endereço pede seu login.
  Troca de senha invalida as sessões anteriores. O aceite do termo é comum
  à conta/banco e não precisa ser repetido por causa da entrada utilizada.
- A entrada LAN mantém o modelo HTTP existente. Portanto, exige rede confiável
  e firewall limitado à rede do setor; HTTP não cifra senhas e conteúdo na LAN.
  Separar cookies não elimina esse risco do transporte. HTTPS local com
  certificado confiável é uma evolução distinta, sem contornar avisos do
  navegador. A entrada pública permanece obrigatoriamente HTTPS.
- Sem internet, o computador e a LAN podem alcançar essa entrada local.
  Integrações externas (Kobo, meteorologia, Conta Ovos) continuam dependentes
  de rede, assim como recursos externos que não estejam disponíveis no cache.
- Offline de formulários nas entradas novas tem armazenamento por usuário.
  Antes de integrar, sincronizar/conferir rascunhos antigos do armazenamento
  legado em cada aparelho. Eles não são apagados nem atribuídos a uma conta
  automaticamente; não presumir propriedade de dados antigos compartilhados.

### Configuração preparada, ainda não aplicada ao serviço

Além dos parâmetros PostgreSQL e PythonPath existentes no launcher:

```text
-Servidor waitress -AcessoExterno -AllowedHosts vsatt.com.br
-AcessoLocal -LocalBind <IPv4 privado confirmado> -LocalPort 5000 -TunnelPort 5001
```

Equivalentes de ambiente: ENDEMIAS_ACESSO_LOCAL=1, ENDEMIAS_LOCAL_BIND,
ENDEMIAS_LOCAL_PORT e ENDEMIAS_TUNNEL_PORT. O perfil só externo anterior
permanece disponível quando a opção local não é informada. Reservar a escuta
5001 para o Tunnel e conservar os limites de upload específicos de cada entrada:
95 MiB externo, 220 MiB local.

## Piloto disponível somente neste computador

`piloto_web.bat`, na worktree, inicia um ambiente identificado como teste:

- SQLite novo com informações fictícias, sem copiar dados de produção.
- Banco, chave, arquivos, configurações, logs e backups em `.venv/piloto-web`.
- Credencial de ensaio gerada aleatoriamente em `acesso.local.txt`, ignorado
  pelo Git; senhas conhecidas da fixture não permanecem habilitadas.
- Acesso local de revisão em `http://127.0.0.1:5002`.
- Entrada reservada a futuro Tunnel em `127.0.0.1:5003`, também só loopback,
  preparada para `piloto.vsatt.com.br` como hostname proposto, sem criar DNS.
- Não usa porta 5000, não lê credenciais do banco oficial, não configura tarefas
  automáticas e bloqueia chamadas reais ao Conta Ovos.
- A opção `scripts/piloto_web.py --validar` prepara/valida a massa e não abre
  portas. Se 5002/5003 estiverem ocupadas, falha sem encerrar processos alheios.
- Não instala serviço nem Tunnel. Encerrar o processo do piloto fecha ambas
  as escutas; a produção continua independente.

## Verificação administrativa sem mudar política de scripts

A primeira tentativa com PowerShell foi impedida pela política de execução.
O atalho foi substituído por Python + consulta nativa `schtasks /Query /XML`,
com resumo sanitizado em `scripts/verificar_tarefa_web.py`. Não usa
ExecutionPolicy Bypass nem altera políticas do Windows. O usuário executou a
nova versão como administrador e a consulta funcionou.

## Validação e próximos passos

- Quatro regressões novas passaram: rejeição de sessão trocada entre entradas;
  cabeçalhos falsos na LAN; recusa de configuração pública/curinga/portas iguais;
  duas escutas HTTP reais, mesmo pool e leitura externa de formulário fictício
  enviado pela entrada local.
- Um teste do diagnóstico confirma que argumentos/credenciais fictícias não
  aparecem no relatório sanitizado.
- Regressão geral desta etapa: **894 testes sem falhas, seis ignorados**.
  O teste novo do diagnóstico nativo passou separadamente, pois foi adicionado
  depois do início dessa execução. HTTP real, CSRF e carga sintética repetidos
  sem erros após a separação das chaves de sessão.
- Piloto iniciado nesta etapa e confirmado em 127.0.0.1:5002/5003, sem escuta
  LAN/pública. Navegador de ensaio fez login e exibiu o termo sem marcar o
  checkbox ou registrar aceite automaticamente. A credencial não foi impressa
  no chat. O piloto é um processo de desenvolvimento, sem inicialização
  automática: quando iniciado pelo atalho, Ctrl+C encerra a execução.
- Produção continuou respondendo HTTP 200 com 1.75.0; SQLite congelado manteve
  o hash registrado no documento de implantação. Não houve reinício ou mudança
  de configuração oficial. Não houve novo Tunnel, DNS, conta ou ACL.

Antes de publicar dados reais: registrar a limitação do Windows atual, trocar a tarefa
SYSTEM por identidade restrita com permissões revisadas, reduzir a escuta do
PostgreSQL a localhost sem mudar desnecessariamente o pg_hba, confirmar regra
LAN do firewall, DNS ativo e concluir piloto do Tunnel. Essas alterações de
produção permanecem pendentes de preparação final e autorização da janela.

### Plano concreto para a identidade da aplicação

Preparar uma conta local dedicada, sem perfil de administrador e sem uso
interativo. A tarefa usa essa identidade e o Python da aplicação. A conta
precisa de leitura/execução no código, leitura na chave e nas configurações
privadas, escrita somente nos diretórios operacionais, logs e backups necessários.
Mover logs para diretório operacional quando a rotação exigir criação de
arquivos; não conceder escrita geral na pasta do código.

Credencial PostgreSQL deve continuar protegida por ACL, com leitura para a nova
identidade, sem copiar senha para chat ou Git. Preparar exportação da tarefa
atual em local privado para retorno. Criação de conta, concessão de direitos,
mudança de ACL, instalação de dependências e troca da tarefa não foram executadas.

### Conferência adicional e plano de permissões

- Defender consultado em 03/11: antivírus e proteção em tempo real ativos,
  proteção contra adulteração ativa, assinaturas de 03/11 e idade zero. Isso
  confirma o estado consultado, não a cobertura das correções do Windows.
- As ACLs consultadas em `C:\endemias` permitem Modify para Usuários
  autenticados. `secret.key`, `kobo_config.json` e `config.json` herdam regras
  amplas; `secret.key` também permite leitura ao grupo Usuários. Não foi lido
  o conteúdo desses arquivos. Isso é acesso pelo Windows, não prova de acesso
  anônimo pela aplicação ou de vazamento ocorrido.
- Portanto, conceder somente RX explicitamente à nova conta é insuficiente
  se ela continuar recebendo Modify por seus grupos. A revisão deve considerar
  permissões herdadas e o acesso efetivo, preservando o acesso de manutenção.
- ACLs individuais de pgpass/Conta Ovos retornaram acesso negado nesta sessão.
  Não inferir permissões exatas desses arquivos pela ACL do diretório pai.
- As duas pastas atuais de backup têm herança desabilitada e regras próprias;
  a nova identidade não foi acrescentada. Uma simples troca da tarefa pode
  quebrar os backups feitos pela aplicação.

Plano concreto para a janela de ativação, ainda **não aplicado**:

| Recurso | Acesso da identidade web | Preparação necessária |
| --- | --- | --- |
| Código, templates, estáticos, scripts, Python/venv | Ler/executar; sem criar, alterar ou excluir código | Exportar ACLs antes; retirar concessões de escrita de grupos amplos no destino de execução, preservar SYSTEM/administradores e manutenção autorizada; conferir em subpastas e no diretório pai. Não aplicar remoção recursiva genérica em toda a máquina. |
| `secret.key` | Somente leitura | Proteger arquivo e diretório contra leitura de usuários comuns e substituição pela conta web; preservar a chave atual, não regenerar. Usar `ENDEMIAS_SECRET_KEY_PATH` se realocar, mantendo backup privado. |
| `pgpass.conf` e `contaovos.key` | Somente leitura dos arquivos necessários | Conferir em contexto administrativo, conceder à identidade exata; não liberar o diretório inteiro nem mudar para credenciais no comando. |
| Configuração Kobo | Leitura e gravação restritas | A aplicação permite edição administrativa; manter em diretório operacional privado via `ENDEMIAS_KOBO_CONFIG_PATH`, sem conceder escrita no código para isso. Preservar token e conteúdo. |
| `config.json` | Leitura para processar planilhas | Confirmar consumidores e manter caminho via `ENDEMIAS_CONFIG_PATH`; não confundir com configuração Kobo editável. |
| Anexos e uploads temporários | Modificar dentro dessas pastas | Preservar conteúdo e definir ACLs próprias; caminhos `ENDEMIAS_ANEXOS_DIR` e `ENDEMIAS_UPLOAD_TEMP`. |
| Log com rotação | Criar/alterar/excluir arquivos dentro de pasta exclusiva de logs | Realocar `ENDEMIAS_LOG_PATH`; conceder escrita só no arquivo atual não permite a rotação. Criar pasta antes de iniciar, pois o handler não a cria. |
| Estado sanitizado Conta Ovos | Modificar em pasta exclusiva | `write_status` cria temporário e usa replace. Usar `ENDEMIAS_CONTAOVOS_STATUS_FILE` separado do diretório de credenciais para permitir a operação sem escrita nas chaves. |
| Backups disparados pela aplicação | Acesso estritamente necessário aos destinos aprovados | Conferir geração, listagem, download e retenção; preservar tarefas automáticas existentes. Evitar que a identidade web possa apagar todas as cópias de recuperação. Separação adicional/cópia externa ainda precisa ser verificada. |
| Banco e seus arquivos internos | Conexão SQL local; sem acesso NTFS aos arquivos do PostgreSQL | Manter serviço NetworkService independente; conferir privilégios do papel da aplicação sem supor que a conta Windows restringe privilégios SQL. |

O código já oferece os caminhos de ambiente acima; não é necessário alterar
a estrutura das tabelas para separar os diretórios. Outros processos (backup,
importação agendada e manutenção) também devem apontar para as mesmas
configurações aprovadas se houver realocação. Não mover configurações somente
para o processo web e deixar tarefas existentes usando outra cópia.

Validar com a identidade final, incluindo tentativas de escrever no código e
na chave (devem falhar), leitura das credenciais sem exibi-las, anexos,
importação, gravação de configuração, rotação de logs e backups de ensaio.
Guardar a definição original da tarefa e ACLs em local privado antes de mudar.
Concluir a validação antes de substituir a tarefa oficial. A criação da conta,
troca da tarefa e alteração de permissões continuam pendentes; esta conferência
não modificou nenhuma delas. Produção reconfirmada HTTP 200/1.75.0 e hash do
SQLite congelado preservado.

## Fontes oficiais consultadas em 03/11/2026

- [Ativação e verificação do ESU comercial](https://learn.microsoft.com/en-us/windows/whats-new/enable-extended-security-updates)
- [ESU de consumo e limites de elegibilidade](https://www.microsoft.com/en-us/windows/extended-security-updates)
- [Atualização Windows 10 de outubro/2026](https://support.microsoft.com/en-us/servicing/os/windows-10/2026/10/kb5126657-windows-10-21h2-22h2-security-update)
- [Cloudflare — saída do Tunnel e firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)
- [Waitress — escutas e configurações](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
