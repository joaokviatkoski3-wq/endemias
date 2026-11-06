# Logos transparentes e identificação provisória — 2.1.1

## Situação

Preparação autorizada em06/11/2026; produção permanece2.1.0, commitc9d4b49,
até execução do novo atalho elevado. Não repetir ativadores anteriores.

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

Após a execução, conferir `C:\ProgramData\EndemiasWeb\ativacao-logos211-resultado.json`,
versão dos três endereços, logins locais5000/5004 e hashes dos ativos públicos.
Até essa conferência a atualização deve ser tratada como candidata.
