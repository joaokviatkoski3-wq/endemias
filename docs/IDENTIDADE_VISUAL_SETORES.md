# Identidade visual dos setores

O Ambiental usa verde escuro na navegação, nos controles e na entrada do sistema.
Endemias mantém sua identidade azul e o arquivo `app.css` anterior. O Portal VSATT
combina as duas cores para identificar os acessos de cada setor.

As imagens `static/img/logo_ambiental.png` e `static/img/logo_vsatt.png` são cópias
exatas dos arquivos fornecidos, com proporção e transparência preservadas. Não há
redesenho, geração de imagem nem filtro de cor sobre os logos. Uma base branca
mantém sua leitura também nos fundos escuros. O logo completo aparece maior no
login; no cabeçalho e no menu ele se adapta ao espaço disponível.

O CSS `branding_ambiental.css` é incluído somente no Ambiental, a partir do setor
já disponível nos templates. Inclui login e recuperação de senha, sem modificar
a autenticação. Nas páginas internas, o botão de tema mantém sua função atual;
login Ambiental e portal acompanham a preferência clara/escura do aparelho.

Conferência em Chromium com massa fictícia: desktop de 1365 px e celular de 390 px,
modo claro/escuro, logins, início, dashboard Ambiental, menu móvel, recuperação e
portal. Sem rolagem horizontal ou erros de JavaScript; marcas azul de Endemias
preservadas. Conteúdo e permissões continuam sujeitos às mesmas regras anteriores.

Não houve alteração de banco, migração, domínio, serviço ou dados de produção.
