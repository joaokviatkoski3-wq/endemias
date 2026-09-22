# Casos humanos de esporotricose

## Finalidade

O sistema possui um cadastro separado para pacientes humanos com
esporotricose em **Esporotricose > Casos humanos**. Ele serve ao acompanhamento
epidemiológico do Setor de Endemias e não substitui o prontuário da UBS.

Medicamentos, receitas, dispensações e condutas clínicas de pacientes humanos
não são registrados neste módulo.

## Acesso e privacidade

Todas as páginas, APIs, anexos, downloads e vínculos são restritos ao nível
`admin`. Operadores e visualizadores não podem sequer consultar a lista.

O sistema audita:

- abertura da área e do detalhe de um paciente;
- criação e alteração do cadastro;
- novos acompanhamentos;
- confirmação e retirada de vínculos;
- inclusão, exclusão e download de anexos.

Na lista, o cartão SUS aparece mascarado. O valor completo só aparece no
detalhe administrativo. O cartão é armazenado como texto para preservar zeros
à esquerda e, quando informado, não pode se repetir em outro paciente.

## Dados e acompanhamento

O cadastro inclui nome, nascimento, cartão SUS, nome da mãe, telefone, data de
notificação, endereço, localidade, quarteirão, coordenadas, observações e
situação do bloqueio (`Realizado` ou `Não realizado`). Quando ainda não se sabe,
o campo fica sem informação; isso não equivale a bloqueio não realizado.

Os status iniciais são `Em tratamento`, `Acabou tratamento` e `Outros`. O
último exige uma descrição complementar.

Cada acompanhamento registra data, status e observações. Salvar um
acompanhamento também atualiza o status atual do paciente, sem guardar
informações de medicação humana.

## Vínculos com imóveis e animais

No detalhe do paciente, a ação **Buscar sugestões** compara o endereço atual
com imóveis já consolidados no histórico de visitas e animais doentes
cadastrados. Localidade, quarteirão, semelhança do logradouro/endereço e número
formam uma pontuação explicada na tela.

A sugestão nunca cria vínculo automaticamente. Um administrador precisa
confirmar cada relação e também pode desfazê-la. Localidade isolada é apenas um
indício fraco; não identifica um imóvel nem um animal por conta própria.

## Anexos

São aceitos PDFs, imagens e documentos já suportados pelos anexos de animais,
com limite de 20 MB por arquivo. Imagens são convertidas para PDF. Os arquivos
ficam em `esporotricose_humanos/<id do paciente>` dentro da pasta externa de
anexos e os metadados permanecem no banco.

## Implantação

A migração PostgreSQL `0016_esporotricose_pacientes_humanos.sql` cria as
tabelas de pacientes, acompanhamentos, anexos e vínculos com imóveis e animais.
Ela deve ser aplicada antes do reinício da versão `1.48.0`. A migração é
aditiva e não altera registros existentes de visitas, imóveis ou animais.

O patch `1.48.1` corrige a ordenação da listagem no PostgreSQL. A falha antiga
afetava somente a consulta da lista e não removia pacientes já cadastrados.

A migração aditiva `0017_esporotricose_humanos_bloqueio.sql` acrescenta a
situação do bloqueio aos pacientes humanos. Os cadastros existentes recebem
valor vazio e podem ser atualizados pela edição do paciente. Aplicar antes de
reiniciar a versão `1.49.1`.

## CSV para QGIS

A partir da versão `1.49.0`, a lista possui a ação **CSV QGIS**. O arquivo:

- respeita os filtros atuais de pesquisa, status, bloqueio e localidade;
- exporta todos os registros correspondentes, sem a paginação da tela;
- usa UTF-8 com BOM e separador `;`;
- mantém `latitude` e `longitude` em colunas numéricas separadas;
- inclui endereço completo, situação, bloqueio, datas, quantidades de vínculos,
  acompanhamentos e anexos;
- inclui dados identificadores completos, inclusive cartão SUS, somente porque
  o download é exclusivo de administradores.

No QGIS, importe como **Texto delimitado**, selecione ponto e use `longitude`
como campo X e `latitude` como campo Y, com SRC `EPSG:4326`. O CSV contém dados
pessoais e de saúde e deve permanecer em ambiente autorizado. Cada download é
registrado na auditoria.
