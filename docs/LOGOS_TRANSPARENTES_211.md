# Logos transparentes e identificação provisória — 2.1.1

## Situação

Atualização aplicada em06/11/2026 pelo usuário, janela08h43. Versão ativa
**2.1.1**, release `3acb3276a583fb90581744983de0029f6a98551a`, origemc9d4b49.
Relatório `C:\ProgramData\EndemiasWeb\ativacao-logos211-resultado.json`
aplicado/concluído;96 tabelas/dados/arquivos preservados, sem DDL ou restauração
de banco. Mesma identidade, tarefa e ambiente; configurações Kobo preservadas,
agendamento devolvido. Prova da conta limitada aprovada. Não repetir o atalho.

## Alterações

- Os arquivos fornecidos `Logo-endemias.png`, `ambiental.png` e `vsatt.png`
  substituem os três ativos correspondentes em `static/img`. PNGs RGBA com
  alpha0–255, copiados byte a byte; sem edição ou redesenho.
- Bases brancas removidas no cabeçalho, menu móvel, login e portal. Inversões
  de cor dos logos retiradas; pequeno contorno em CSS acompanha a silhueta
  transparente para manter a leitura quando reduzida. Controles do menu
  conservam seu contraste. Endemias continua azul e Ambiental verde.
- Ambiental, inclusive login e recuperação: aviso discreto no rodapé sobre
  o uso provisório/não oficial do logotipo até adoção de uma marca oficial.
- Portal: aviso sobre as marcas Ambiental e VSATT e a sigla VSATT, provisórias
  e não oficiais. Texto não atribui esse caráter ao setor ou ao serviço público.
- Portal sempre claro, independentemente da preferência escura do aparelho.
  Os dois sistemas mantêm seus modos claro/escuro. Logos e CSS principais
  ganham referência de versão para atualização do cache.

## Verificação

- 30 testes existentes de setores e14 do ativador, sem falhas. Sem testes novos
  que apenas reproduzam o CSS; validação visual pelo navegador.
- Chromium com contas/dados fictícios e CSRF:26 combinações desktop1365px e
  celular390px, logins, inícios, menus móveis, Dashboard Ambiental, recuperação
  e portal, claro/escuro. Sem erros JS/rolagem horizontal; transparência por
  estilo calculado, ausência de inversão de cor e avisos por setor conferidos.
- Portal apresenta o mesmo fundo claro com preferência light/dark. PNGs,
  proporções e alpha conferidos; hashes iguais aos originais. Evidências
  privadas em `.venv/logos211-provas` na worktree de integração.
- A primeira rodada visual parou porque a faixa do ambiente fictício cobria
  o botão de fechar o menu Endemias. A rodada final usa o fechamento pelo
  fundo externo, também disponível na interface, sem ocultar a faixa.
- Produção consultada anonimamente: três HTTPS200/2.1.0; sem conta real ou
  alteração operacional. SQLite congelado mantém o hash anterior.
- Prova nativa ampliada para ler também o novo logo Endemias; a verificação
  focada de hostname/cookies e prova de instalação passou novamente.

## Implantação

`scripts/ativar_logos_211_windows.py` usa o atualizador homologado, origem2.1.0,
destino2.1.1 e marcador `ativacao-logos211`. Exige os commits exatos, faz backup
SQL/completo antes de parar a aplicação e compara as96 tabelas e arquivos
operacionais. Sem migração, reimportação Kobo ou mudança de contas, ambiente,
tarefa, portas, Cloudflare e firewall. Prova da identidade limitada inclui
os novos ativos e logins. O agendamento é devolvido ao estado anterior.

## Conferência após implantação

Dezesseis checagens passaram, registradas em `.venv/publicacao-211.json`:
portal e dois logins HTTPS, além de locais5000/5004,200/2.1.1 com no-store;
portal sem cookie e IDs de requisição válidos. Avisos presentes no portal e
Ambiental, ausentes em Endemias. Ajuda e dashboard sem sessão401 nos dois
domínios. Três PNGs, três CSS e script da ajuda iguais à instalação.

Os PNGs publicados preservam exatamente os arquivos fornecidos e sua
transparência. O CSS app instalado/publicado possui quatro CRLF a mais que a
worktree, por normalização do Git: conteúdo igual ao normalizar quebras de
linha, sem diferença funcional. CSS do portal sem preferência escura e HTML
com color-scheme light. Não foi necessário mudar código ou configuração nessa
conferência. Nenhum login de conta real ou escrita operacional foi executado.

SQLite congelado conferido, SHA-256 inalterado:
`964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
Backups registrados pelo atualizador:

- SQL: `C:\ProgramData\EndemiasWeb\ativacao-logos211-20261106-084314\antes_conta_limitada.dump`,
  7.549.413 bytes, catálogo validado;
  SHA-256 `50c8dd9650d7f8f469d0abb802d25bb7f2a86bd1eb285b19eef87ef56b97b9ad`.
- Completo: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261106_084326.zip`,
  310.618.548 bytes;
  SHA-256 `b432c0149ea8cbe762b3734055b6eadf4575c4e4f67664a483a75639488e3dcd`.
