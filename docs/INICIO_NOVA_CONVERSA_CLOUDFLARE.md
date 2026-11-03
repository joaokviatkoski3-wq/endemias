# Endemias — início da frente de acesso externo via Cloudflare

Documento de passagem preparado em 03/11/2026. Envie este arquivo ao novo
chat do Codex, vinculado ao projeto Endemias. Os caminhos abaixo pertencem
ao computador Windows do setor. Confirme o estado vivo antes de trabalhar;
este documento não substitui os registros operacionais atuais.

## Pedido do usuário

Quero preparar o Endemias para acesso externo pela internet usando Cloudflare
Tunnel, inicialmente a partir do computador Windows 10 em que o sistema já
funciona. **Já comprei o domínio no Registro.br.** O nome do domínio ainda
não foi informado nesta passagem.

Esta nova conversa cuidará da preparação e implementação do acesso externo.
A conversa original continuará cuidando do LIRAa e de outras alterações
funcionais. As duas frentes devem trabalhar sobre o mesmo projeto, com
ambientes de desenvolvimento separados e integração coordenada.

Prepare e teste a solução até ficar pronta para revisão e ativação. Este
pedido permite investigar, desenvolver, testar e documentar em ambiente
isolado. Não autoriza publicar o sistema real, alterar DNS/nameservers,
configurações do computador oficial, banco de produção ou reiniciar seu
serviço sem uma autorização específica para a ação preparada.

## Leia primeiro

No repositório oficial `C:\endemias`, leia nesta ordem:

1. `AGENTS.md`.
2. `CONTEXTO_PARA_IA.md`.
3. `docs/ESTADO_ATUAL_PROJETO.md`.
4. `docs/GUIA_TRABALHO_MULTIAGENTE.md`.
5. `docs/LIRAA_INTEGRACAO_OPERACIONAL.md`, para preservar a integração recente.

Codex é o operador principal. Não é necessária revisão do Claude para
implementar, testar, fazer commit ou push. Preserve alterações de outras
frentes. Não interprete implantações históricas como nova autorização.

## Referência de produção nesta passagem

| Item | Estado registrado |
| --- | --- |
| Repositório | `joaokviatkoski3-wq/endemias` |
| Pasta oficial | `C:\endemias` |
| Branch oficial | `master` |
| Versão ativa | `1.75.0`, ativada em 03/11/2026 às 11h32, America/Sao_Paulo |
| Código funcional dessa versão | `a0d3c3c` |
| Registro posterior de ativação | `39ecfb6` |
| Banco oficial | PostgreSQL `endemias` |
| Porta da aplicação oficial | `5000` |
| Inicialização oficial | Tarefa Windows `Endemias - Servidor`; conferir ação/identidade reais |
| SQLite histórico | `C:\endemias\endemias.db`, congelado para rollback, sem novas escritas |
| Última migração registrada | `0029_liraa_integracao_notificacoes.sql`, já aplicada |

Esses commits são referências históricas, não um ponto a restaurar. Comece
pela `master` mais recente e confira Git, processos, tarefas e configuração.
Não reaplique a 0029 nem outras etapas já concluídas.

O ciclo real do LIRAa é o 4, de 09 a 13/11/2026: cinco sorteios,
261 quarteirões sorteados e seis adicionais intencionais, totalizando 267.
Não alterar ciclos, datas, estratos, N/n, assinatura, sorteios ou adicionais
para preparar o acesso externo. ACS continuam provisórios e editáveis.
Visitas de teste eventualmente criadas pela equipe não autorizam limpeza
automática. Não importar respostas nem lançar resultados reais para ensaiar.

## Separação das duas frentes

- Use uma worktree e branch próprias, derivadas da `master` atual. Sugestão:
  `C:\endemias-cloudflare` e `codex/preparar-cloudflare`. Confira se já
  existem antes de criar ou reutilizar. Se o Codex já tiver criado uma
  worktree para este chat, use-a após confirmar o isolamento.
- Não trabalhe na pasta oficial nem reutilize a worktree do LIRAa.
- Worktree separa arquivos Git, mas não isola banco, portas, anexos, logs,
  credenciais, serviços, backups ou tarefas automáticas. Configure esses
  recursos separadamente antes de executar a aplicação de teste.
- Siga o fluxo de `testar.bat` e `parar_test.bat`. A porta padrão de testes
  é 5002; confira ocupação e coordene seu uso com a outra frente. Não encerre
  processos de outra conversa nem mude scripts compartilhados por conveniência.
- Testes devem usar dados sintéticos e SQLite próprio ou PostgreSQL
  `endemias_teste` isolado. Não apontar o servidor experimental para o
  PostgreSQL `endemias`, nem copiar seus dados/credenciais para um piloto web.
- Desative tarefas/importações automáticas e chamadas externas com escrita
  no ambiente experimental. Credenciais, tokens e arquivos de configuração
  privados não entram no Git nem em saídas do chat.

O objetivo final é acesso externo ao mesmo Endemias oficial, com os mesmos
dados e funcionalidades. O ambiente separado é de desenvolvimento e teste;
não criar uma segunda produção permanente ou uma versão paralela do produto.

## Como acompanhar as alterações do sistema

- A conversa do LIRAa continuará entregando mudanças na `master`.
- Sua branch não recebe essas mudanças automaticamente. Incorpore a
  `master` atualizada em pontos de controle e antes da entrega, resolva os
  conflitos com cuidado e repita os testes afetados.
- Faça commits pequenos e coerentes, com documentação e push da própria
  branch. Não use force push nem descarte alterações alheias.
- Mantenha um registro próprio, como `docs/CLOUDFLARE_IMPLANTACAO.md`, com
  estado confirmado, arquivos alterados, testes, pendências e próxima ação.
  Não grave senhas, tokens ou dados pessoais nesse documento.
- Combine a edição de arquivos compartilhados, principalmente `app.py`,
  autenticação, dependências, inicialização e documentação de estado.
- Enquanto a preparação do LIRAa estiver em andamento, a conversa original
  coordena integrações na `master` e mudanças no serviço oficial. Entregue
  sua branch pronta e indique dependências/ordem de implantação. Não faça
  merge, troca de serviço ou ativação externa concorrentes por iniciativa própria.
- Correções urgentes de segurança que afetem a produção devem ser comunicadas
  com o problema concreto e a correção proposta para integração coordenada.

## Arquitetura inicial a validar

Fluxo proposto para usuários autorizados:

```text
Navegador HTTPS
    -> Cloudflare Access
    -> Cloudflare Tunnel
    -> servidor de aplicação local adequado à produção
    -> Endemias e PostgreSQL local
```

O Tunnel conecta a aplicação local à Cloudflare; não transfere a aplicação
nem o banco para hospedagem na nuvem. O acesso dependerá de o computador,
o serviço, a energia e a internet do setor estarem disponíveis.

Prepare acesso restrito à equipe, mantendo também o login e as permissões
do Endemias. Não abrir portas no roteador, não publicar o PostgreSQL e não
deixar dados reais acessíveis anonimamente durante um teste.

A publicação deve usar um servidor adequado ao Windows, avaliando Waitress,
interfaces de escuta, proxy confiável, HTTPS/cookies, controle de host e
proteção de anexos. Preserve o acesso local necessário à equipe; decidir
como ele continuará funcionando antes de trocar a escuta do servidor.

Na leitura do código em 03/11, `app.py` ainda usava
`werkzeug.serving.make_server("0.0.0.0", ...)`, e os padrões de
`ENDEMIAS_SESSION_COOKIE_SECURE` e `ENDEMIAS_TRUST_PROXY_HEADERS` eram falsos.
Rever essas configurações antes da publicação; não considerar a ativação
do Tunnel, sozinha, preparação suficiente do servidor.

Avaliações antigas também apontaram conta de serviço, escuta do PostgreSQL,
uploads grandes e importações demoradas como pontos de atenção. Confirme
o estado atual; não apresente observações antigas como diagnóstico atual.

## Domínio e Windows

- O domínio está comprado no Registro.br. Identifique seu nome, situação,
  servidores DNS atuais, registros existentes e eventual uso de e-mail/site.
  O nome pode ser perguntado ao usuário se não estiver disponível no contexto.
- Compra do domínio não confirma que a zona já esteja na Cloudflare.
  Prepare a configuração preservando registros e serviços existentes.
- Proponha um subdomínio para o Endemias, sem inventar um domínio real.
  Preparar DNS, nameservers e, se aplicável, DNSSEC com sequência de mudança
  e retorno. Alterações externas dependem de autorização específica.
- O usuário pretende usar Windows 10. Confirme edição, versão e cobertura
  efetiva de atualizações de segurança/ESU ou alternativa suportada antes
  da ativação externa. Não presumir cobertura porque o Windows está ativado.
- Não solicitar senhas pelo chat. Use autenticação interativa ou os
  mecanismos autorizados de credenciais, sem copiar segredos para documentos.

## Trabalho esperado

1. Faça uma auditoria inicial somente leitura do código e da infraestrutura.
   Apresente um diagnóstico breve, distinguindo confirmado, não verificado
   e decisão necessária. Confirme as documentações e limites atuais dos serviços.
2. Prepare a worktree e o ambiente de testes. Prossiga com o desenvolvimento
   isolado que não dependa de decisão pendente, sem pedir confirmação para
   cada alteração reversível já abrangida por este pedido.
3. Implemente em etapas: servidor/configuração, proteção de acesso,
   compatibilidade dos fluxos, operação e recuperação. Mantenha o escopo
   funcional do sistema e suas integrações atuais.
4. Valide login/logout, permissões, anexos, importações, laboratório,
   notificações, LIRAa, relatórios, PDFs/XLSX, mapas, rotinas de fundo,
   requisições demoradas, limites de upload e uso local/externo.
5. Teste reinicialização, queda de conexão, reconexão do Tunnel, recuperação
   e restauração de backup em ambiente isolado. Não substituir backups reais
   nem executar uma restauração sobre o banco oficial.
6. Execute a regressão aplicável. Para a suíte Python do projeto, use
   `python -m unittest discover -s tests -t .`, sempre com banco isolado.
7. Entregue código testado, documentação, commit e push da própria branch.
   Descreva o que falta para ativar e o que já está demonstrado por testes.
8. Antes de pedir autorização de publicação, deixe um plano concreto de
   implantação e retorno: alterações, impacto no acesso local, backup,
   sequência, critérios de sucesso e como desfazer a mudança com segurança.
   A ativação externa será combinada em uma janela que preserve o LIRAa.

## Fontes para conferir no início

- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
- [Aplicação web protegida por Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [Atualizações estendidas do Windows 10](https://learn.microsoft.com/en-us/windows/whats-new/extended-security-updates)
- [Worktrees no Codex](https://learn.chatgpt.com/docs/environments/git-worktrees)

Comece confirmando o estado atual e preparando a frente isolada. Explique
as decisões em linguagem simples e registre o que foi efetivamente realizado.
