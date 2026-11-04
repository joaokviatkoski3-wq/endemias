# Perfis e administração do sistema — 1.79.0

## Objetivo e conta responsável

O superadmin é a conta técnica responsável pelo sistema. O usuário confirmou
que sua conta pessoal é `joao` (id 2). A ativação promove somente essa conta;
as outras contas, senhas, vínculos e autorizações de laboratório são preservados.
Administradores passam a cuidar da operação, com os limites abaixo.

| Ação | Superadmin | Admin | Operador | Visualizador / usuário |
| --- | --- | --- | --- | --- |
| Consultar os módulos permitidos | Sim | Sim | Sim | Sim |
| Registrar e alterar dados operacionais | Sim | Sim | Conforme o módulo | Não, salvo acesso específico de laboratório |
| Gestão de agentes, auditoria e presença | Sim | Sim | Não | Não |
| Importações operacionais Kobo e gestão de LIRAa | Sim | Sim | Conforme o módulo | Não |
| Criar e administrar contas inferiores a admin | Sim | Sim | Não | Não |
| Criar, promover, alterar ou recuperar senha de admin | Sim | Não | Não | Não |
| Alterar credenciais/configurações da integração Kobo | Sim | Não | Não | Não |
| Central, diagnóstico, backups, downloads e restauração | Sim | Não | Não | Não |
| Criar outro superadmin ou alterar a conta superadmin pela gestão | Não | Não | Não | Não |

O admin não altera outro admin, a própria conta pela gestão nem o superadmin.
Pode trocar a própria senha em **Minha senha**, informando a senha atual.
O superadmin também usa esse caminho para trocar sua própria senha.
Criar/promover alguém a administrador é uma decisão exclusiva do superadmin.

Os sinalizadores **Acesso ao laboratório**, **Somente laboratório** e o vínculo
com agente continuam funcionando para os perfis comuns. O nível `usuario`
continua ocultando a identificação dos demais agentes, sem prometer anonimizar
moradores ou endereços. Não houve cisão Endemias/Ambiental nesta mudança.

## Proteções

- A autorização é conferida no servidor, lendo o perfil atual no banco. Ocultar
  botões não é a única barreira: URLs e requisições diretas também são bloqueadas.
- O banco impede a existência de dois superadmins. A gestão web não oferece
  promoção a esse nível, rebaixamento, desativação ou redefinição dessa conta.
- Recuperação assistida obedece à mesma hierarquia. Um link antigo deixa de
  funcionar se a conta passar a ser protegida ou se o emissor perder autoridade.
- Administradores podem selecionar ACS do ciclo LIRAa, mas não trocar seu UID
  Kobo. A configuração técnica fica com o superadmin.
- Backups completos podem conter chaves e credenciais: ficam restritos ao
  superadmin, inclusive os arquivos antigos e os links de download.

## Se o superadmin esquecer a senha

Outro administrador não consegue tomar essa conta usando recuperação de senha.
No computador oficial, execute `C:\endemias\recuperar_superadmin.bat` com o
botão direito, **Executar como administrador** do Windows.

O procedimento exige confirmar `RECUPERAR joao` e digitar a nova senha duas
vezes, sem exibi-la. Não recebe senha na linha de comando. Funciona apenas na
instalação oficial, para o único superadmin ativo, e registra o evento na
auditoria. A troca invalida os acessos anteriores. Não execute apenas para
testar: esse procedimento realmente altera a senha da conta.

Quem administra o Windows e o banco continua tendo poder técnico sobre o
sistema; a separação dos perfis web não substitui a proteção desse computador.

## Implantação e continuidade

A migração PostgreSQL `0033_superadmin.sql` amplia o CHECK de níveis e cria o
índice único parcial. Não escolhe uma pessoa automaticamente. O ativador
`scripts/ativar_superadmin_windows.py` exige a versão anterior 1.78.0 e promove
exatamente `joao`/id 2 após backup, migração e comparação dos dados anteriores.
O ensaio seguinte roda na conta limitada EndemiasWeb, mantendo tarefa,
credencial, portas, conector e inicialização automática existentes.

SQLite recebe compatibilidade equivalente em bases de desenvolvimento; o
`C:\endemias\endemias.db` de rollback permanece congelado.

Backups anteriores à 1.79 não contêm este esquema/perfil. Sua restauração exige
manutenção local para reaplicar a migração e conferir a conta responsável antes
de liberar uso. O recuperador de senha não cria superadmin em banco antigo.
Preferir backups posteriores à ativação, conferir o catálogo e ensaiar a
restauração em ambiente separado antes de uma restauração real.

## Validação da preparação

- 964 testes gerais: OK, sete ignorados; testes adicionais de UID LIRAa e link
  anterior à promoção executados separadamente.
- PostgreSQL descartável em `127.0.0.1:55441`, banco `endemias_teste`: migração,
  unicidade, hierarquia, recuperação assistida, promoção controlada e recuperação
  local da conta fictícia. Nenhuma senha real alterada pelo ensaio.
- Chromium com CSRF real: admin bloqueado nas operações técnicas e na conta
  protegida, gestão inferior disponível e superadmin com acesso técnico.
  Tela de celular sem transbordamento e zero erros JavaScript.

Estado efetivo da ativação: consultar `ESTADO_ATUAL_PROJETO.md` e o relatório
privado `C:\ProgramData\EndemiasWeb\ativacao179-resultado.json`.
