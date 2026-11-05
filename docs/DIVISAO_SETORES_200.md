# Divisão de setores — candidata 2.0.0-rc.1

Atualizado em 05/11/2026. **Candidata ativada no Windows** (release `29b478a`).
Produção Endemias agora 2.0.0-rc.1; origens locais dos três hosts conferidas.
Rotas/HTTPS públicos dos três hosts confirmados em 05/11. Esta entrega
não declara a versão 2.0 estável. Preparação em `C:\endemias-setores`, branch
`codex/divisao-setores-2`; código integrado na master pela janela administrativa.

## Versão ativa 2.0.0-rc.1 — divisão ativada em 05/11/2026

- Usuário executou o atalho administrativo e informou conclusão. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao-setores200rc1-resultado.json`:
  `status=aplicado`, `stage=concluido`, release `29b478a`, janela 09h04.
  Somente 0035 aplicada; 96 tabelas/colunas anteriores comparadas e preservadas,
  assim como arquivos operacionais, chave, config e SQLite congelado. Contas,
  níveis e senhas preservados; contas comuns continuam Endemias.
- Backup PostgreSQL de 7.541.541 bytes/catalogado, SHA-256
  `57c00bdfb971c3f5b89153950061949ca8b4678bc4cc034ebe48fdeeb21b763c`.
  Completo anterior à 0035: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_090441.zip`,
  310.611.983 bytes, SHA-256
  `b8974c9f1ef756dbbba2bff95bb58cd41eb1764c87b91704162295c2e1b511b3`.
  Restaurar este completo para código 2.0 exige aplicar 0035 antes de abrir uso.
- Mesma tarefa/identidade/credencial do servidor. Prova real na conta limitada
  passou em todos os checks, incluindo escrita controlada nos dois Kobo,
  chaves por setor, três hosts, negação anônima, backup SQL e código sem escrita.
  Tarefa Kobo das 12h30 encontrada e devolvida ao estado original; mesmo horário
  e identidade. Executor agora seleciona os dois setores separadamente.
  Primeira execução automática após a divisão ainda não conferida.
- LAN Endemias 5000 e Ambiental 5004 respondem 200 no servidor; origem Tunnel
  127.0.0.1:5001 responde aos três Hosts corretamente. Regra Ambiental criada
  só para interface/sub-rede local e perfis privado/domínio. Teste de outro
  aparelho confirmado pelo usuário em 05/11. **Reinício real confirmado:**
  usuário informou sucesso; LastBootUpTime passou de 04/11 09h49 para
  05/11/2026 09h21. Cloudflared automático/rodando, portas locais e origem
  corretas e três HTTPS 200 após o boot; logins dos setores seguem 2.0.0-rc.1
  com no-store/private. Perda real da internet ainda não simulada.
- **Publicação dos três hosts confirmada em 05/11:** usuário salvou as rotas
  no mesmo Tunnel. Portal `https://vsatt.com.br` 200, links corretos e sem cookie
  do sistema; `https://endemias.vsatt.com.br/login` e
  `https://ambiental.vsatt.com.br/login` 200/2.0.0-rc.1, cada título correto,
  `no-store, private` e CF DYNAMIC. APIs anônimas dos dois setores retornam 401.
  HTTP 301 para HTTPS nos três, TLS 1.0/1.1 recusados com alerta de versão,
  certificados conferidos e TLS 1.2/1.3 aceitos. Evidência local:
  `C:\endemias-setores\.venv\publicacao-setores-tls.json`.
- Usuário confirmou acesso com sua conta real aos dois setores pelo portal e
  abertura do login Ambiental em outro aparelho da rede local. Não foram
  alteradas contas comuns, senhas ou níveis. Estética continua adiada.
- Prévia fictícia aprovada pelo usuário em 05/11. Estética do Ambiental/portal
  ficou para depois. Não marcar 2.0 estável antes das conferências operacionais.
  Geo permanece futuro. Não repetir o atalho de atualização já aplicado.

## Decisões confirmadas pelo usuário

| Entrada | Conteúdo |
| --- | --- |
| `https://vsatt.com.br` | Portal público de escolha, sem dados operacionais ou sessão. Dois links para os setores. |
| `https://endemias.vsatt.com.br` | Módulos de Endemias, sem Esporotricose e Amostras de Animais. |
| `https://ambiental.vsatt.com.br` | Esporotricose integral, Amostras de Animais, Meteorologia, Vigiágua vazio, agenda, dashboard, relatórios, mapa e importação Kobo próprios. |
| `geo.vsatt.com.br` | Somente planejamento posterior à 2.0. Nenhum aplicativo/hostname Geo implementado. |

- Meteorologia permanece nos dois setores; dados meteorológicos são comuns.
- Conta e senha únicas no cadastro; acesso ordinário a um setor. Admin e
  superadmin acessam ambos, sempre na aplicação/entrada correspondente.
- Agentes de Endemias fazem visitas de Esporotricose **somente pelo Kobo**.
  Não há exceção para acessar a gestão web Ambiental. Seus vínculos antigos
  às visitas continuam válidos e não dependem do setor de sua conta web.
- Cadastro de agentes e localidades/base territorial é compartilhado.
  Hierarquia e restrições pessoais anteriores permanecem, inclusive laboratório
  exclusivo em Endemias. Administração técnica/backups continuam globais e
  reservados ao superadmin. Gestão de contas é comum aos dois setores.

## Implementação preparada

`ENDEMIAS_SETORES_ENABLED=1` ativa a divisão explicitamente. Desligado, preserva
o comportamento anterior. Não habilitar no serviço antes da migração/testes.

- `app_core/setores.py`: permissão de setor separada do nível da conta.
  URLs/APIs de outro setor são recusadas mesmo para gestores. Endpoints novos
  sem definição de setor falham fechados. Ocultar menus não é o controle de acesso.
- `app_core/dominios.py`: encaminhamento por Host exato, com aplicações Flask
  distintas; root só exibe os dois links. Host desconhecido é recusado.
  Cada aplicação externa conserva a validação do conector local/HTTPS.
- Cookies externos permanecem host-only, Secure, HttpOnly e SameSite=Lax.
  Chaves derivadas distinguem setor e entrada local/externa. Não há SSO;
  credenciais são as mesmas e cada domínio mantém sua sessão. Na ativação,
  cookies antigos deixarão de autenticar; usuários entrarão novamente.
- Agenda: eventos manuais têm setor; leituras, alteração e exclusão por ID
  respeitam o setor. Eventos automáticos ambientais vêm só de Esporotricose
  e Amostras; os de Endemias excluem essas fontes.
- Painel/relatórios ambientais iniciais agregam visitas de Esporotricose e
  registros de Amostras por data/localidade/quarteirão, com filtros e exportações
  CSV/XLSX/PDF. Não incluem arboviroses. A gestão clínica detalhada permanece
  no módulo completo de Esporotricose, agora somente no Ambiental.
- Mapa Ambiental inicial usa a base territorial comum e camadas/contagens
  próprias das duas fontes. Registros sem correspondência territorial são
  informados, sem inventar coordenadas. Não substitui o projeto futuro Geo.
- Dashboard, mapa, produção operacional, relatório individual/PDF completo e
  boletim mensal de Endemias excluem consultas/indicadores ambientais. Itens
  ambientais antigos do boletim são preservados ao salvar o boletim Endemias.
- Kobo: configurações `kobo_config.json` e `kobo_ambiental.json`, formulários,
  prévias, lotes, uploads, ETL e históricos separados. UID arbitrário não pode
  substituir o configurado na prévia. Jobs temporários usam subpastas por setor.
  Backup completo inclui ambas as configurações; arquivo Ambiental é ignorado
  pelo Git. Tokens não são exibidos em respostas.
- Auditoria nova registra o setor da ação; listagem/exportação respeitam o
  setor. Central técnica conserva consulta global e histórico anterior.
- Mudar o setor de uma conta encerra suas sessões sem alterar sua senha.
  Links de recuperação apontam ao setor da conta. Gestores conservam ambos.

## Banco e dados existentes

Migração **aditiva 0035**, aplicada pela janela de 05/11:

- `usuarios.setor`: padrão Endemias. Não adivinhar a lotação real das pessoas.
  Após homologação, responsável atribuirá Ambiental na Gestão de Usuários.
- `agenda_eventos.setor`: padrão Endemias para os eventos manuais existentes.
  Responsável deve revisar os compromissos antigos; não é possível classificá-los
  com segurança pelo título. Nenhum evento é apagado ou movido automaticamente.
- `importacoes.setor` e `auditoria_eventos.setor`: registros anteriores ficam
  como `legado`, preservados na Central técnica. Lotes antigos podem ser mistos;
  não são apresentados como histórico exclusivo de nenhum setor.
- Nenhuma cópia/transferência/apagamento das tabelas de Esporotricose ou Amostras.
  Propriedade lógica e consultas mudam; chaves e relações existentes permanecem.

PostgreSQL não recebe DDL na inicialização web: com a divisão ligada, a fábrica
confere as colunas e recusa iniciar se a migração estiver ausente. SQLite de
teste recebe compatibilidade local. **Nunca executar testes no SQLite congelado.**

## Pacote de implantação preparado em 05/11

Usuário aprovou a prévia local com massa fictícia e pediu prosseguir; estética
fica para depois. Todas as contas comuns continuam Endemias inicialmente.

`scripts/ativar_setores_windows.py` faz a janela administrativa com backups,
0035, comparação das colunas anteriores e dos arquivos operacionais, configuração
Kobo separada/ACL restrita, atualização do bootstrap protegido, prova na mesma
conta limitada, regra LAN Ambiental e sondas dos três hosts. Não redefine tarefa,
identidade ou senha. O retorno captura configurações eventualmente alteradas e
restaura código/configuração anterior, conservando esquema aditivo e dados novos.
Os relatórios não gravam tokens ou linhas de dados; snapshots são privados.

O executor diário Kobo das 12h30 é preservado: mesma tarefa/identidade/horário,
pausada apenas na janela. O script existente passa a executar os dois setores
explicitamente e devolve erro se algum falhar, sem impedir o outro de tentar.
Se estiver importando, o instalador recusa iniciar a troca e aguarda nova tentativa
após a execução terminar; não mata uma importação em andamento.

46 testes focados passaram, e dez verificações do instalador/executor foram
repetidas após os ajustes finais. As simulações cobriram sucesso e falha na prova
limitada, com retorno de configurações/serviço/agendamento e banco preservado.
O comparador foi ensaiado num PostgreSQL novo: aceita a coluna adicionada e
detecta mudança numa coluna antiga. Ainda falta a execução na identidade real.

Relatório esperado após a execução:
`C:\ProgramData\EndemiasWeb\ativacao-setores200rc1-resultado.json`.
Somente `status=aplicado`, `stage=concluido` e checks verdadeiros confirmam ativação.
Em falha, preservar relatórios e snapshots; não executar ativadores antigos.

## Procedimento de implantação ainda pendente

Não executar ativadores antigos 1.77/1.78/1.79/1.80 para esta candidata.
Antes de publicar, preparar a janela Windows específica, com backup completo
e PostgreSQL conferidos, inventário/assinaturas dos dados anteriores, cópia
privada das configurações/ACL e plano de retorno. Este documento acompanha o novo
ativador e a integração na master não deve ocorrer com o processo ativo lendo
templates antigos/novos misturados.

1. Prévia homologada em 05/11; repetir a conferência com os endereços reais após
   ativação. Contas comuns continuam Endemias, conforme decisão do usuário.
2. Preparar divisão privada da configuração Kobo, sem imprimir tokens.
   `setores.dividir_kobo` prepara os dois objetos em memória. Conferir os UIDs;
   preservar os originais no backup. Dar à conta limitada a mesma permissão
   controlada de edição no novo arquivo, sem conceder escrita no código.
3. Parar a aplicação na janela, fazer backups, integrar release, aplicar somente
   0035 e conferir dados anteriores por hash/contagem. Configurar opt-in
   `ENDEMIAS_SETORES_ENABLED=1`, `ENDEMIAS_DOMINIO_BASE=vsatt.com.br` e manter
   `ENDEMIAS_ALLOWED_HOSTS=endemias.vsatt.com.br` (a fábrica monta o outro app).
   Não sobrescrever a tarefa, identidade, credencial do Windows ou a chave base.
4. Conferir processo na identidade limitada, dependências, leitura/gravação
   controlada dos dois arquivos Kobo, login de cada aplicação e bloqueios.
   O código preparado mantém LAN Endemias em 5000 e Tunnel em 127.0.0.1:5001.
   Acrescenta LAN Ambiental em **5004**, configurável por
   `ENDEMIAS_AMBIENTAL_LOCAL_PORT`. Cookies locais têm nomes distintos.
   Preparar regra Windows só para a rede local autorizada, sem abrir roteador.
5. No mesmo Tunnel, cadastrar os hostnames **exatos** `ambiental.vsatt.com.br`
   e `vsatt.com.br`, origem `http://127.0.0.1:5001`; conservar Endemias.
   Não forçar um único HTTP Host Header para as três rotas; preservar o Host
   solicitado. Conferir DNS, certificado, TLS mínimo 1.2 e redirecionamento HTTPS.
   Nenhuma dessas ações de Cloudflare foi feita nesta preparação.
6. Testar externamente login, setor errado, links, importação fictícia em
   homologação, relatórios, ausência de cache público e recuperação; conferir
   LAN dos dois setores com a internet desconectada. Fazer ensaio de reinício
   real após implantação. Aplicação deve voltar junto com a tarefa/Tunnel.
7. Se houver rotina Kobo agendada, inventariar a configuração antes da troca:
   `importar_kobo_automatico.py --setor endemias|ambiental` seleciona configuração,
   formulários, histórico e ETL. Com opt-in ligado, rotina sem setor explícito
   é recusada. Nenhuma tarefa automática nova foi criada/alterada.

Retorno: parar, voltar código/ambiente/configurações capturados e conferir
Endemias. A 0035 é aditiva; **não restaurar dump nem apagar registros novos
automaticamente**. Tratar mudanças de setor feitas após a abertura e eventos
novos ao decidir o retorno; não executar redução destrutiva do esquema.

## Validação e limites

Ensaios automatizados usam somente massa fictícia em worktree e PostgreSQL
temporário fora de 5432. Scripts:
`testar_setores_browser.py` (Chromium/CSRF/desktop/celular) e
`testar_setores_postgresql.py` (cluster novo SCRAM, migrações, consultas e
exportações; encerra/remove cluster e credenciais temporárias).
Resultado final: **1.001 testes OK, seis ignorados** (21 novos da divisão).
Ensaio focado de 29 testes de setores/Kobo automático também OK. Chromium
com CSRF real, desktop/celular e sessões locais simultâneas sem erros JavaScript.
PostgreSQL descartável SCRAM/55444 confirmou a 0035 aditiva, consultas, agendas,
relatórios/PDF e exportações; cluster/credenciais temporários removidos.
Três entradas Waitress e o encaminhamento por Host exato conferidos com portas
aleatórias de teste. Nenhuma escuta/serviço de homologação deixado ativo.

Corrigidos na preparação um carregamento antecipado de formatação do dashboard,
um rótulo compatível da importação e um import da rotina Kobo. A suíte completa
foi repetida após os ajustes, com o resultado acima. Evidências locais ignoradas
pelo Git: `.venv/regressao-confirmada.log`, `setores-focados-final.log`,
`setores-browser-resultado.json` e `setores-pg-resultado.json`.

Ainda não confirmados: classificação dos compromissos antigos, primeiro
processamento automático Kobo após divisão e perda real da internet. Reinício
real da divisão confirmado em 05/11/2026, assim como retorno dos três HTTPS. Login real nos setores e LAN em outro aparelho foram confirmados
pelo usuário. Ajustes visuais ficaram para depois. Não usar testes sintéticos como
declaração de prontidão operacional ou implantação concluída.

Windows sem atualização, HTTP local, MFA e primeiro upload cifrado ao Drive
permanecem conforme o estado anterior; não foram alterados nem declarados
resolvidos por esta divisão.


## Painel Cloudflare — orientação conferida em 05/11

Na interface atual: **Networking → Tunnels → vsatt-piloto → Routes → Add route
→ Published application**. Em algumas telas a aba é chamada Published
application routes/Public hostnames. Usar o Tunnel existente, sem reinstalar o
conector. Origem comum: tipo HTTP, URL `127.0.0.1:5001`, caminho vazio.

| Subdomínio | Domínio | HTTP Host Header específico da rota |
| --- | --- | --- |
| `ambiental` | `vsatt.com.br` | `ambiental.vsatt.com.br` |
| vazio | `vsatt.com.br` | `vsatt.com.br` |

O campo HTTP Host Header fica nas configurações adicionais/HTTP da própria rota.
Cada rota deve transmitir seu hostname; não copiar um override Endemias para as
outras. Conservar a rota Endemias existente. A criação das rotas/DNS será manual,
pois não há ferramenta Cloudflare conectada disponível nesta sessão.

Fontes oficiais: [criar rota publicada](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
e [HTTP Host Header](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/#httphostheader).
