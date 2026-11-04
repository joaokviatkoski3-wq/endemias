# Backup do Endemias no Google Drive

Rotina manual combinada em 04/11/2026.

## Preparar e enviar

1. Entre como **joao** em https://endemias.vsatt.com.br.
2. Abra **Central do Sistema** e clique em **Backup completo**. Aguarde a conclusão.
3. Na lista de backups completos, clique em **Baixar**.
4. Escolha uma frase de proteção exclusiva, com pelo menos **20 caracteres**,
   e repita-a. Guarde a frase em local seguro, separado do Google Drive.
5. Confira se o download terminou e o arquivo tem extensão **`.zip.7z`**.
6. Envie esse arquivo à pasta privada de backups no Google Drive e aguarde
   terminar o envio. Mantenha o nome com data para identificar cada cópia.

O envio ao Google Drive é **manual**. A conta não está conectada ao Endemias e
não foi configurada sincronização automática pelo agente.

O backup completo reúne banco PostgreSQL, anexos e configurações do sistema.
Ele não é uma imagem de todo o Windows; uma recuperação em outro computador
também requer preparar o programa e sua infraestrutura.

## Conferir a primeira cópia

Depois de enviar, baixe o arquivo de volta do Drive. A conferência deve
comparar o tamanho/hash com o arquivo enviado e testar a abertura com a frase
de proteção em uma pasta privada, sem restaurar sobre o sistema em uso.
Até essa conferência, preserve as cópias antigas e os backups locais.

Depois, definir a retenção e a substituição das cópias antigas sem proteção.
A existência de uma cópia criptografada nova não protege retroativamente os
arquivos que já foram enviados em formato legível.

## Situação registrada

- Destino informado: **Google Drive pessoal** do responsável.
- Responsável informou que somente ele acessa as pastas e que a conta Google
  possui verificação em duas etapas. Esses controles não foram auditados no Drive.
- Rotina anterior: copiar pastas do sistema e dos backups para o Drive.
  Essas cópias externas foram informadas pelo usuário; seu conteúdo e integridade
  não foram conferidos pelo agente.
- Rotina aprovada: enviar os novos backups completos criptografados `.zip.7z`,
  guardar a frase separadamente e manter as cópias anteriores até validar a nova.
- Primeira cópia criptografada enviada ao Drive e conferida: **pendente**.
- Nenhum arquivo foi enviado, excluído ou compartilhado no Drive pelo agente.

O uso de conta pessoal para dados do setor deve observar as regras da prefeitura.
Uma conta controlada pela instituição facilita a continuidade do acesso se o
responsável mudar de função.

## O que já foi testado localmente

Na implantação 1.80.0, o download criptografado foi testado com dados fictícios.
Um backup completo real local também foi restaurado em ambiente privado separado:
96 tabelas e 663 arquivos conferidos. Isso ainda não valida as cópias existentes
no Drive ou o primeiro arquivo criptografado que será enviado.

Mais detalhes em [Correções de segurança 1.80](CORRECOES_SEGURANCA_180.md).
