# LIRAa — múltiplas sequências por envio

Versão 2.6.0 ativa em 06/11/2026 às 16h11, release `d219216`.
Usuário autorizou esta ampliação na importação LIRAa. Não altera a expansão de
TB/TBO/PVE nem importa dados reais durante implantação.

## Interpretação

Vírgula, ponto e vírgula, barra, hífen, travessões, barra vertical, quebra de
linha, tabulação e combinações, com espaços opcionais, separam unidades.
Exemplos: `1,2,3`, `1 - 2 - 3`, `1/2/3`, `1 ; 2 ; 3`, `B1, B2, B3`.
Listas simples por espaços (`1 2 3`, `A1 A2 A3`) e conjunção (`1 e 2 e 3`)
também são reconhecidas. Letras são uniformizadas em maiúsculas; sequências
repetidas são deduplicadas com aviso: `1, 2, 2` representa duas unidades.
Um valor isolado `3` é uma unidade. `1-3` são duas unidades; não há expansão de
intervalos. Expressões como `1 a 3` são recusadas por ambiguidade.

Identificadores compostos como `A-1` e `B/02` são preservados quando isolados
ou separados por delimitador claro (`A-1, A-2`). `A-1 - A-2` também é aceito.
Cadeias ambíguas como `A-1-A-2` pedem revisão e separação por vírgulas.
`N/A`, `S/N` e um traço isolado não viram listas de unidades. Limites: 2.000
caracteres brutos, 100 por identificador, 50 partes por envio e 10.000 visitas
por lote expandido. Limite excedido recusa a operação; não trunca silenciosamente.

## Identidade, dados compartilhados e laboratório

A primeira unidade mantém o UUID Kobo original. As demais recebem identificador
determinístico calculado do UUID original e da sequência, mantendo a chave única
existente. O JSON `tratamento_json._sequencias_v1` registra origem, texto original,
conjunto, primeira unidade e avisos; não foi acrescentada tabela ou coluna.
A ordem pode mudar na reimportação sem trocar a identidade da primeira unidade.
Mudança do conjunto de unidades de um grupo já importado exige conferência,
sem apagar ou acrescentar silenciosamente unidades a um grupo existente.

Data, endereço, tipo, ciclo, plano e participantes derivam do mesmo lançamento.
Tubitos, tratamentos e cargas ficam apenas na primeira unidade. Leituras continuam
vinculadas aos mesmos tubitos, sem duplicação. Quando há coleta e várias unidades,
a prévia/lista orienta conferir sua atribuição entre os imóveis. Não se inventam
resultados negativos nem se espalha um positivo por todas as unidades.

O boletim conta as visitas elegíveis separadas. Ensaio com três unidades e dois
tubitos positivos confirmou três imóveis trabalhados e apenas um imóvel positivo.
Regras de período, ciclo, estrato, sorteio/adicional e pendências de leitura foram
preservadas. Essa regra trata visitas de campo; não muda o inventário de imóveis
nem a regra do condomínio no plano amostral.

## Reimportação e histórico

A expansão é centralizada em `_preparar`, comum à prévia/importação específica,
API, planilha e aplicação dos formulários internos. UUID repetido é recusado;
repetir envio/alterar separadores não duplica visitas. Exclusões são respeitadas.
Se o grupo inteiro foi excluído e restaram exclusões de unidades, uma restauração
parcial sem metadados suficientes exige conferência; não ressuscita irmãos.

Envios legados já importados, sem os metadados desta versão, são ignorados como
antes. Se o texto contiver lista, a prévia avisa que o registro antigo não foi
expandido. Sua revisão/recomposição histórica é uma etapa separada; este pacote
não altera visitas, amostras, leituras ou boletins antigos automaticamente.

## Validação

98 testes do conjunto LIRAa passaram; após os ajustes finais, 16 testes focados
do importador passaram, incluindo formatos, duplicidade, limites, exclusões,
legado, reordenação e recusa sem escrita parcial. Sete testes da aplicação via
ETL/formulário interno, 33 de setores/prova limitada e 24 do instalador passaram.
PostgreSQL descartável (55444) confirmou três visitas, um tubito e reimportação
idempotente pela integração geral. Boletim/laboratório foram ensaiados em SQLite.
Não houve consulta de respostas nem escrita no banco de produção durante testes.
Ainda é necessária conferência operacional de um pequeno lote na prévia.

Ativação confirmada: relatório `ativacao-liraa260-resultado.json` aplicado/concluído,
backup completo e PostgreSQL realizados, 96 tabelas preservadas e prova limitada
OK (incluindo compilação da tela e parser de sequências). Contas, ambiente,
configurações Kobo e automação preservados. Nove verificações de publicação
passaram: cinco entradas em 2.6.0, API sem sessão negada e código/template iguais
aos testados. Nenhum lote real importado e nenhum histórico reprocessado nesta
conferência. A validação operacional de um lote pequeno na prévia segue pendente.

## Conferência do lote de 09/11/2026

Às 12h36, a consulta de produção em leitura comparou 198 envios da API Kobo
com 221 visitas do ciclo 4. Nenhum envio do recorte ficou ausente de uma das
fontes. Doze envios originaram 35 visitas com sequências múltiplas, sem
identificadores esperados ausentes, sequência divergente ou cópia de tubos e
tratamento nas unidades adicionais. Há 214 visitas sorteadas e sete fora do
sorteio atual. Foram encontrados seis tubitos com número válido, sem repetição
no ciclo e sem leituras registradas naquele momento.

Um tubo veio de uma visita só com ACS, quatro de visitas com ACE e ACS e um de
visita sem participante informado. A fila antiga buscava ACE na relação de
agentes. A candidata 2.6.1 mostra a equipe registrada também com ACS na fila,
no formulário de leitura e no histórico. Resolve rótulos pelo catálogo local
ou pelo formulário de referência e exibe o código quando faltar um rótulo.
Aplica-se aos tubos já gravados. Ativação administrativa pendente.

Evidência agregada local em .venv/liraa-20261109-auditoria.json da worktree.
A consulta não gravou no banco nem no Kobo. O ensaio PostgreSQL e os testes
integrados cobriram coleta só com ACS. SQLite também cobriu equipe mista,
Outros ACS e ausência de participantes.
