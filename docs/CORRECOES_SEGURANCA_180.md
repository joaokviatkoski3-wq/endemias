# Correções de segurança — preparação 1.80.0

Atualizado em 04/11/2026. Produção confirmada em **1.79.0**. Este documento
descreve o pacote preparado em `C:\endemias-seguranca`, branch
`codex/correcao-seguranca`; não comprova sua ativação.

## Situação dos pontos apresentados pelo usuário

| Ponto | Mudança preparada / situação |
| --- | --- |
| Scripts em BRI e Amostras de Animais | Textos escapados nos resumos, registros, vínculos PE e etiquetas. Mesmo tratamento aplicado a cartões do mapa e tipos de depósito/tratamento do Conta Ovos. Não altera os dados importados no banco. |
| Política de scripts | Scripts dos templates recebem nonce aleatório por resposta. `script-src` usa nonce e `strict-dynamic`; `object-src 'none'`. Eventos inline bloqueados nas duas telas afetadas, login/recuperação e download de backups. Outros módulos ainda permitem eventos inline por compatibilidade; a remoção completa é trabalho posterior, não está declarada concluída. |
| Cookie reutilizado depois de sair | Registro revogável no banco, validado a cada requisição autenticada. Logout revoga a sessão antes de limpar o cookie; outra sessão do mesmo usuário continua independente. |
| HTTP local | Continua disponível por necessidade operacional. Usar o domínio HTTPS oficial como entrada habitual. Instalação de certificados nos aparelhos não foi escolhida; HTTPS local permanece em avaliação. Downloads de backup pela rede local HTTP serão recusados, para não transmitir a frase de proteção sem criptografia. Loopback do próprio servidor é permitido. |
| Windows sem cobertura de atualizações | Mantido por decisão explícita do usuário. O pacote não corrige nem oculta esse risco. |
| TLS antigo / HTTP público | Teste atual confirmou TLS 1.0/1.1/1.2/1.3 aceitos e HTTP 403 sem redirecionamento. Nenhuma mudança Cloudflare feita; controle do navegador foi interrompido por não conseguir confirmar a URL. Passos manuais abaixo. |
| Fórmulas em CSV | Campos textuais recebem proteção contra início de fórmula, inclusive prefixos de espaço/controle. Coordenadas e colunas numéricas declaradas preservam números finitos. Aspas, separadores e quebras seguem o CSV padrão. |
| Duas cópias antigas de banco | Ativador inventaria/hash e restringe ACL da raiz e dos dois arquivos identificados, sem excluir conteúdo. Essa alteração depende da execução administrativa do ativador. |
| Backup completo sem criptografia | Originais locais continuam no formato atual, dentro das pastas privadas. Downloads de banco e completos passam a exigir frase de 20+ caracteres e geram um envelope 7z/AES-256 com nomes internos criptografados. Só superadmin pode baixar. A frase não é salva no banco ou em arquivo. |
| Somente senha | Lista local de senhas comuns e rejeição de sequências/repetições nas novas criações/trocas. Não houve inspeção ou troca das senhas reais. Segundo fator não ativado: usuário pediu explicação antes de adotar. |

O escape usa os valores como texto no HTML, sem remover informações da fonte.
A revisão de outros pontos foi dirigida às montagens de HTML relacionadas; não
é uma declaração de ausência de vulnerabilidades em todo o sistema.

## Sessões depois da ativação

A migração `0034_sessoes_revogaveis.sql` cria `usuarios_sessoes`. O banco guarda
o hash do identificador aleatório, conta, vínculo com a senha, criação, limite
absoluto de oito horas e revogação. Identificadores ausentes, expirados,
revogados ou vinculados à senha anterior são recusados. A limpeza de registros
expirados não revalida cookies antigos. Falha no banco não anuncia logout
concluído nem libera autenticação sem a verificação.

**Todos os usuários precisarão entrar novamente após a atualização.** Os
cookies anteriores à 1.80 não têm registro válido. Múltiplos aparelhos continuam
permitidos; sair de um não encerra o outro. A senha atual e os perfis não mudam.
Testes unitários antigos que injetam autenticação simulada usam `TESTING`;
instâncias reais exigem o registro, inclusive fora do perfil externo.

## Baixar e guardar uma cópia

1. Entre como `joao` pelo endereço HTTPS oficial e abra **Central do Sistema**.
2. Crie o backup desejado e clique em **Baixar**.
3. Escolha uma frase exclusiva de pelo menos 20 caracteres e confirme-a.
4. O download será um arquivo `.zip.7z`, `.dump.7z` ou `.db.7z`.
5. Guarde a frase separadamente. Sem ela, uma cópia externa não poderá ser
   aberta. O servidor mantém o original na pasta privada e permite nova
   exportação enquanto esse original existir.

O arquivo 7z pode ser aberto pelo [7-Zip oficial](https://www.7-zip.org/).
Ao extrair com a frase correta, obtém-se o ZIP/dump/SQLite original. Descompactar
não restaura automaticamente o sistema: uma restauração real precisa de janela
de manutenção, validação do banco e conferência dos anexos/configurações.
Não restaurar sobre a produção para testar uma cópia.

Os downloads usam um temporário fechado ao terminar a resposta, na área de
uploads protegida da conta web. A implantação instala `py7zr==1.1.4` e suas
dependências a partir de nove wheels locais com SHA-256 conferido no manifesto
versionado. Consulta OSV desses nove pacotes em 04/11: nenhum alerta retornado.

### Cópia na nuvem

É possível guardar o arquivo **já criptografado** em pasta privada de uma conta
institucional no OneDrive, Google Drive ou serviço definido pelo responsável.
A primeira rotina pode ser manual: baixar, enviar o arquivo e registrar a data.
O destino deve ter acesso restrito e verificação em duas etapas. A frase deve
ficar em local separado do arquivo e acessível ao responsável pela recuperação.

Manter cópias datadas e retenção ajuda a recuperar versões anteriores, pois a
sincronização também pode propagar exclusões e alterações. Automatizar somente
depois de definir conta, pasta, credenciais apropriadas e rotina de recuperação.
Não houve upload de dados, configuração de nuvem, compartilhamento ou cadastro
de credenciais nesta preparação. Não foi confirmada uma cópia externa real.

O usuário informou que só dispõe de conta pessoal. Ela funciona tecnicamente;
para dados do setor, a preferência é uma conta controlada pela instituição,
com continuidade de acesso se o responsável mudar de função. A compatibilidade
de uma conta pessoal com as regras do setor ainda não foi estabelecida. Uso
provisório deve considerar arquivo previamente cifrado, pasta privada, MFA e
frase separada; criptografia não define autorização institucional. Ver também
o [guia de segurança da ANPD, seção sobre nuvem](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-vf.pdf/@@display-file/file).

O ensaio deste pacote recuperou cópias **fictícias**, inclusive chave fictícia e
backup SQLite, comparando os bytes. Uma restauração completa de backup real
PostgreSQL/anexos em ambiente privado separado ainda está pendente.

## Ajustes manuais da Cloudflare

No painel da Cloudflare, selecione **vsatt.com.br** e entre em
**SSL/TLS → Edge Certificates (Certificados de borda)**:

1. **Minimum TLS Version:** selecionar **TLS 1.2**.
2. **TLS 1.3:** manter habilitado.
3. **Always Use HTTPS:** habilitar.

Esses controles são da borda Cloudflare. O pacote Flask não muda esses valores.
Após aplicar, repetir o ensaio de TLS e de redirecionamento HTTP para HTTPS.
Não alterar o Tunnel ou abrir portas para essa correção.

Referências oficiais: [TLS mínimo](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/),
[redirecionamento HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/),
[sessões e logout](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[CSV Injection](https://community.owasp.org/attacks/CSV_Injection),
[criptografia e cabeçalhos 7z](https://py7zr.readthedocs.io/en/latest/api.html),
[privacidade e compartilhamento no OneDrive](https://support.microsoft.com/en-us/onedrive/share-files-and-folders-in-microsoft-onedrive).

## Ativação e retorno

Executar `scripts/ativar_seguranca_windows.py` com Python de manutenção elevado,
informando os commits completos atual e proposto. O atalho preparado na Área de
Trabalho contém os valores conferidos para esta janela.

- Exige master limpa, pacote limpo, versão de origem 1.79, Waitress/PostgreSQL.
- Antes de parar o servidor: confere wheels, instala apenas a dependência
  necessária no Python protegido e confere conflitos; inventaria/protege as
  duas cópias antigas com hashes e permissões anteriores em registro privado.
- Depois: backup catalogado, parada breve da tarefa existente, integração,
  somente 0034, comparação dos dados/arquivos, ensaio na conta EndemiasWeb e
  retorno dos logins nas entradas 5000/5001. Perfis e senhas não são alterados.
- Com a aplicação parada, este lote também cria um backup completo atual na
  pasta privada configurada, registra tamanho/hash e mantém o arquivo para
  posterior exportação cifrada e ensaio de restauração real. A pasta atual de
  completos estava vazia na inspeção desta preparação.
- Retorno automático durante a janela preserva banco/dados novos e a migração
  aditiva; retorna código/configuração se necessário. Os pacotes adicionados e
  a proteção de ACL das cópias antigas permanecem; não são revertidos para
  permissões amplas. Não restaura dump sobre produção.

Relatórios privados: `C:\ProgramData\EndemiasWeb\seguranca180-preparacao.json`
e `ativacao180-resultado.json`. Sucesso da preparação não prova sucesso da
ativação. Não repetir depois de ativar; conferir os relatórios e a versão viva.

## Validação

980 testes gerais: OK, seis ignorados. Dezesseis focados de backup/exportação/
ativação também passaram; a proteção CSP final foi reconferida no navegador.
Ensaio PostgreSQL descartável (`127.0.0.1:55442`, `endemias_teste`) confirmou
migração 0034, revogação persistente, aparelhos independentes, expiração e troca
de senha. A instância foi encerrada ao final; não usou banco oficial.

Chromium com CSRF real, em massa fictícia, confirmou escape sem depender de CSP,
bloqueio de evento injetado com CSP, mapa, cookie copiado inválido após logout,
download protegido e recuperação idêntica ao arquivo original. Zero erros JS.
Validações em SQLite cobrem também fórmulas, coordenadas, proteção de downloads
HTTP local e os limites de permissão herdados da 1.79.
