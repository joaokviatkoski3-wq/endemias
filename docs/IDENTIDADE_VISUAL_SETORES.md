# Identidade visual dos setores

O Ambiental usa verde escuro na navegação, nos controles e na entrada do sistema.
Endemias mantém sua identidade azul. O Portal VSATT
combina as duas cores para identificar os acessos de cada setor.

Desde a2.1.1 as três imagens `logo_endemias.png`, `logo_ambiental.png` e
`logo_vsatt.png` são cópias exatas dos novos arquivos fornecidos em06/11, com
proporção, cores e transparência preservadas. Não há redesenho ou geração de
imagem. As bases brancas da2.1.0 foram retiradas. Um contorno branco sutil em
CSS reforça a leitura em tamanhos pequenos, acompanhando a transparência.
O logo completo aparece maior no login; cabeçalho/menu adaptam-se ao espaço.

O CSS `branding_ambiental.css` é incluído somente no Ambiental, a partir do setor
já disponível nos templates. Inclui login e recuperação de senha, sem modificar
a autenticação. Nas páginas internas, o botão de tema mantém sua função atual;
login Ambiental acompanha a preferência clara/escura do aparelho. O portal
permanece claro mesmo quando o aparelho prefere tema escuro. Avisos discretos
nos rodapés identificam as marcas Ambiental/VSATT e a sigla VSATT como
provisórias e não oficiais. Endemias não recebe esse aviso.

Conferência em Chromium com massa fictícia: desktop de 1365 px e celular de 390 px,
modo claro/escuro, logins, início, dashboard Ambiental, menu móvel, recuperação e
portal. Sem rolagem horizontal ou erros de JavaScript; marcas azul de Endemias
preservadas. Conteúdo e permissões continuam sujeitos às mesmas regras anteriores.

Não há migração de banco nem mudança de autenticação, permissões, domínio ou
configuração do serviço. A implantação2.1.1 e suas verificações estão em
`docs/LOGOS_TRANSPARENTES_211.md`.
