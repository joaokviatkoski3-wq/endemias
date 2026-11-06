# Piloto do Campo RG — 2.2.0

Escopo aprovado em 06/11/2026: evoluir o RG existente para um piloto restrito,
principalmente em Android pessoal/tablet. Não libera novos usuários, não substitui
o Kobo e não implementa Geo, novos formulários, fotos ou GPS. iPhone tem instrução
de instalação, mas ainda depende de homologação em aparelho real.

## Uso pelo agente

1. Use um aparelho com bloqueio de tela e o navegador habitual. Abra o endereço
   HTTPS oficial de Endemias, entre na própria conta e acesse Formulários → RG.
   O endereço local HTTP continua para uso online; ele não prepara o PWA offline.
2. Em Preparar campo, escolha localidade/quarteirões e baixe as referências.
   A seleção traz nomes de localidades e ruas; não baixa moradores ou prontuários.
   Baixe até 500 quarteirões por operação. Retire referências que não precisar mais.
3. No Android, use Instalar ou o menu do navegador → Instalar aplicativo /
   Adicionar à tela inicial. No iPhone: Safari → Compartilhar → Adicionar à Tela
   de Início. A instalação não torna as demais páginas disponíveis sem internet.
4. Abra Meus quarteirões. Preencha por lado, rua e imóvel. O app salva alterações
   automaticamente no próprio navegador e informa quando a gravação terminou.
   Espere a indicação de salvo antes de fechar; uma interrupção durante a gravação
   ainda pode perder os últimos caracteres. Em caso de erro, mantenha a tela aberta.
5. Ao voltar a conexão, mantenha o app aberto e use Sincronizar agora para conferir.
   Abertura online e retorno da conexão também tentam enviar pendências. Não há
   promessa de envio com o app fechado. O servidor precisa estar disponível.
6. Rascunho recebido continua rascunho. Enviar para revisão muda a solicitação;
   o gestor precisa conferir, aprovar e oficializar antes de alterar o RG oficial.
   Uma devolução aparece após sincronizar; reabra o quarteirão para corrigir.

## Proteção escolhida e limites

O usuário escolheu começar somente com bloqueio de tela do Android, sem outra
senha. Os rascunhos **não recebem criptografia adicional do aplicativo**. Não
registre dados pessoais de moradores nas observações. Um aparelho desbloqueado,
perfil de navegador comprometido ou acesso aos arquivos locais continua sendo risco.

Cada origem e conta usa seu próprio IndexedDB. Sair remove a página offline e
preserva os rascunhos; outra conta não recebe os dados da anterior. Entre novamente
na mesma conta, no mesmo navegador/origem, para retomar. Não mude de aparelho nem
de navegador com pendências. Não há migração automática de rascunhos entre aparelhos.

A preparação offline vence após 24 horas da autenticação online. É necessário
conectar e renovar. Isso limita o uso offline, mas não permite verificar bloqueios
ou permissões revogadas enquanto não houver conexão e não protege contra alteração
do relógio/arquivos por alguém que controla o aparelho. O login online continua
sujeito às políticas e prazo de sessão existentes.

Pendências, rascunhos e registros em revisão não são apagados automaticamente.
Somente cópias com oficialização confirmada são limpas após sete dias do recibo,
ao abrir o RG. É possível apagar manualmente uma cópia já oficializada, com confirmação;
isso não exclui o registro no servidor. Não apague cópias ainda em trabalho.
O navegador pode remover armazenamento, especialmente sob falta de espaço/modo
privado. O pedido de armazenamento persistente ajuda, mas não garante preservação.
Limpar dados/desinstalar/perder aparelho pode perder registros ainda não recebidos.

## Sincronização e compatibilidade

- UUID, aparelho lógico e revisão crescente identificam a captura; recibo só limpa
  a pendência da revisão exata. Repetição recebe o mesmo ID, inclusive após revisão.
- PostgreSQL usa trava por UUID e trava de linha; SQLite usa transação imediata.
  Revisões antigas, mesmo número com conteúdo diferente, outro contexto e
  sobrescrita de aprovado/oficializado são recusados, preservando a cópia local.
- O POST vincula a conta da captura à sessão atual. Há renovação de CSRF antes
  do envio; falhas de login, conta, conexão, servidor e validação têm mensagens.
- O recibo persistido e sua auditoria confirmam na mesma transação. Não há DDL
  nesta versão. Metadados ficam no JSON existente, sem aplicar automaticamente RG.
- O editor preserva ruas/imóveis incompletos; a revisão do gestor prevalece sobre
  o editor bruto anterior. Cadastros antigos mantêm o fluxo legado; rascunho
  local antigo precisa ser reaberto/conferido. Um UUID já recebido pelo protocolo
  anterior não é adotado silenciosamente: há aviso para conferência pelo gestor.
- Service worker v5 guarda apenas a tela de RG e os seus arquivos estáticos.
  APIs, relatórios, anexos e telas administrativas não são cacheados. Falha 5xx
  preserva a tela preparada; logout/troca de conta bloqueiam a cópia anterior.
  Atualização do app aguarda salvar e tocar em Atualizar, evitando recarga no meio
  do preenchimento. IndexedDB continua versão 1, sem apagar bancos anteriores.

## Homologação antes de ampliar

No Android real do agente piloto: instalar, baixar um quarteirão, entrar em modo
avião, preencher, fechar/reabrir, conferir conteúdo e sincronizar com o servidor.
Conferir o recibo, enviar para revisão, devolver/corrigir, aprovar/oficializar com
o gestor e verificar o RG. Testar troca de rede e retomada após login expirado.
Só ampliar após essa validação operacional. A automação em Chromium e PostgreSQL
fictícios não substitui o ensaio com aparelho real nem avalia qualidade dos dados.

## Operação e reversão

Validações em06/11/2026: suíte geral1.152 testes, seis ignorados pelas condições
documentadas nos testes;10 testes focados de protocolo e16 do ativador após
refinamentos. PostgreSQL descartável na porta55444 confirmou concorrência,
recibo idempotente, revisão protegida e vínculo de conta; Node verificou cache,
expiração, logout e resposta atrasada. Chromium com CSP efetiva, larguras
360/390/768/1365: salvamento/reabertura offline, CAS/recibo antigo, revisão/devolução,
502, expiração de login, falta de espaço, troca de conta e atualização sem recarga
prematura. Sem erros JS; instalabilidade sem impedimentos nesse Chromium.
Há ResourceWarnings antigos de conexões SQLite não fechadas na suíte; nenhum
ensaio em aparelho físico foi realizado. Esses resultados não são um pentest.

Preparação em `codex/pwa-rg-piloto`, worktree separada. Produção era 2.1.1 no
início. Ativação usa o procedimento elevado com backup, assinaturas das tabelas,
pausa breve, prova na conta limitada e restauração do agendamento Kobo. Nenhuma
conta, permissão, configuração Kobo, DNS ou rota Tunnel é alterada.

Antes de qualquer reversão manual, sincronizar/conferir o agente piloto e preservar
seus dados locais. O banco local não sofre mudança de versão, mas o cliente antigo
não entende os novos recibos. Não usar cliente antigo para editar capturas novas;
o servidor impede a sobrescrita enquanto a proteção nova estiver ativa. Falha de
instalação antes do uso segue a reversão do ativador, sem restaurar dados reais.
