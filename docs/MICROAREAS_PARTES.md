# Quarteiroes parciais em microareas

Estado em 29/09/2026: implementacao integrada a `master`. A saida do migrador
executado pelo usuario confirmou a aplicacao da 0022 no PostgreSQL oficial.
O servico foi reiniciado e `/login` respondeu HTTP 200 com versao `1.58.0`.

## Uso previsto

Em Territorializacao > Microareas > Mapa, o administrador escolhe a localidade
e abre uma microarea existente ou cria outra. No editor de lados, informa o
quarteirao e busca os logradouros e lados que constam no RG. Se o quarteirao
ja pertence por inteiro a uma microarea, o aviso oferece **Editar microarea**;
sem abrir a dona, os lados aparecem bloqueados para evitar atribuicao dupla.
Seleciona um lado, clica em **Desenhar**, marca os vertices no mapa e clica
em **Concluir e salvar lado**. O desenho pode ficar dentro, fora ou cruzar o
contorno do quarteirao oficial; cabe ao administrador conferir sua posicao.
Informe antes o numero da
microarea. Tanto na edicao quanto na criacao de microarea nova, o sistema
grava imediatamente e rele o cadastro para confirmar o lado salvo. O lado so
aparece na lista da microarea depois dessa confirmacao. Se o servidor rejeitar
o desenho, aparece um erro explicito, os vertices permanecem no mapa para
corrigir/repetir, e um F5 antes de salvar produz aviso do navegador.
Pode desfazer o ultimo vertice, cancelar e redesenhar. O vinculo de um quarteirao inteiro pode ser
convertido em lados parciais na edicao da mesma microarea; os lados nao
selecionados ficam sem atribuicao. Outro administrador podera atribui-los a
outra microarea. Remover um lado e salvar desassocia apenas esse lado.

Cada quarteirao pode pertencer inteiro a uma unica microarea **ou** ter lados
em microareas diferentes. O mesmo lado, identificado por localidade,
quarteirao, logradouro e lado do RG, so pode pertencer a uma microarea. O
poligono desenhado pode ficar em qualquer posicao, mas nao pode ocupar
area de outro lado ja desenhado do mesmo quarteirao. Fronteiras podem coincidir. A validacao
geometrica e feita no servidor com Shapely. O sistema nao desenha nem
deduz automaticamente o limite real de um lado: a conferencia do desenho
com o territorio continua sendo responsabilidade de quem cadastra. O lado
continua vinculado ao quarteirao e ao trecho do RG informados; nao se trata
de uma atribuicao geografica automatica pelo local onde o desenho caiu.

O mapa exibe os poligonos parciais por cor da microarea, a lista mostra os
lados, e o XLSX detalha tipo de atribuicao, logradouro e lado. GeoJSON e KML
exportam os desenhos. Para uso no QGIS, o GeoJSON preserva cada lado como
feature independente. O KML agrupa por microarea e descreve seus lados.

## Indicadores e atualizacao do mapa

Nos lados parciais, imoveis e populacao estimada vem das linhas do RG para
aquele logradouro e lado; nao resultam da area do poligono. O controle de
condominios segue a regra das microareas inteiras. Cada quarteirao e contado
uma vez no total do recorte, mesmo se seus lados pertencem a microareas
diferentes. Lados nao atribuidos nao entram na estimativa.

Se um novo GeoJSON oficial mudar a geometria-base de um quarteirao, os
desenhos anteriores sao marcados como desatualizados. GeoJSON/KML de
microareas com esses desenhos nao sao exportados ate que sejam redesenhados e
salvos. A importacao da camada nao apaga os vinculos; revisar os desenhos
apos importacao e etapa obrigatoria.
Se um logradouro/lado deixar de constar no RG, o vinculo e sinalizado e a
exportacao fica suspensa ate sua revisao.

## Implantacao e verificacao

1. Shapely 2.1.2 foi instalado no Python local usado nos testes. Conferir o
   mesmo interpretador no processo do servico apos o reinicio.
2. O usuario aplicou `migrations/postgresql/0022_territorializacao_microareas_partes.sql`
   pelo migrador oficial apos validacao dos backups.
3. A branch foi integrada a `master` e o servico reiniciado com sucesso.
   Fazer teste funcional autorizado com um quarteirao que possua lados
   preenchidos no RG, sem criar dados de teste em producao automaticamente.

Testes automatizados usam SQLite temporario, nunca o banco de producao.
