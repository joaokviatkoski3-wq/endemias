# Infraestrutura e piloto local — 03/11/2026

Continuação da preparação `1.76.0`, branch `codex/preparar-cloudflare`.
O usuário autorizou a próxima etapa e pediu preservar o acesso local se viável.
Este registro complementa `CLOUDFLARE_IMPLANTACAO.md`; não declara publicação.

## Estado confirmado nesta etapa

| Item | Evidência e conclusão |
| --- | --- |
| Produção | GET /login na porta 5000 retornou HTTP 200 e versão 1.75.0. Master continua em f7a98a0, sem alterações deste lote. |
| DNS público | Consultas a 1.1.1.1 e 8.8.8.8 ainda retornaram a.auto.dns.br/b.auto.dns.br. Usuário salvou bristol/cullen no Registro.br; confirmar término da transição antes do hostname público. |
| Windows | Windows 10 Pro 22H2, build 19045.6466. A referência de segurança consultada para outubro/2026 é 19045.7807, KB5126657. A máquina precisa adequar suas atualizações antes de receber dados reais pela internet. |
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

Antes de publicar dados reais: adequar Windows/atualizações, trocar a tarefa
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

## Fontes oficiais consultadas em 03/11/2026

- [Ativação e verificação do ESU comercial](https://learn.microsoft.com/en-us/windows/whats-new/enable-extended-security-updates)
- [ESU de consumo e limites de elegibilidade](https://www.microsoft.com/en-us/windows/extended-security-updates)
- [Atualização Windows 10 de outubro/2026](https://support.microsoft.com/en-us/servicing/os/windows-10/2026/10/kb5126657-windows-10-21h2-22h2-security-update)
- [Cloudflare — saída do Tunnel e firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)
- [Waitress — escutas e configurações](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
