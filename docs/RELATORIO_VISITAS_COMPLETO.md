# Histórico de visitas em PDF compacto

Implementado no código `1.65.0` e compactado em `1.65.1`, em 02/10/2026. A opção fica separada dos
resumos em **Relatório por Agente**, com filtros obrigatórios de agente,
data inicial e data final. A rota autenticada
`/relatorio-agente/visitas/pdf` entrega um PDF A4 paisagem para download.

O relatório lê, sem alterar dados, todas as visitas do agente no intervalo
inclusivo nas tabelas `visitas` (PE/TB/TBO/PVE) e
`esporotricose_visitas`. Uma visita com vários agentes aparece uma vez no
relatório de cada participante. Não há limite artificial de 500 registros como
na lista operacional de esporotricose. As visitas são ordenadas por data e
hora, misturando as duas fontes cronologicamente.

Cada visita ocupa no máximo cinco linhas, distribuídas em colunas: data e
horário, tipo/resultado, localidade/quarteirão, endereço, morador/telefone,
imóvel, agentes/ACS, atividades e observações. Depósitos são somados por
inspecionados, eliminados e tratados, com os tipos indicados. Tratamentos,
coletas/tubos, resultados laboratoriais positivos, focos/notificações e
animais são resumidos quando existirem. O PDF não mostra identificadores da
visita, Kobo, localidade ou registros associados, nem `submission_time`,
`processado_em` ou a localidade oficial duplicada. Textos longos são
abreviados com reticências para cumprir o limite de cinco linhas. O banco
continua intacto e todos os registros selecionados são considerados no
resumo. Dados pré-sistema que não estejam nas tabelas de visitas não são
inventados nem recuperados de outra fonte.

O PDF contém dados pessoais e de saúde. Exige sessão como as páginas de
visitas, é entregue como anexo e envia `Cache-Control: private, no-store`.
Não grava PDF no servidor nem no banco. O arquivo salvo no computador do
usuário deve ser tratado conforme as mesmas restrições de acesso das visitas.

Dependência nova: `reportlab>=4.2,<5` em `requirements.txt`; instalada no
Python local de serviço em 02/10/2026 para teste. Não exige migração de banco.
O serviço oficial ainda precisa carregar o código novo para oferecer o formato compacto;
não atribua a versão nova ao processo em execução sem verificar `/login`.

Validação inicial de `1.65.0`: `tests/test_relatorio_visitas_completo.py` usa SQLite temporário,
inclui visita compartilhada por dois agentes, resultado laboratorial,
foco, animal e ACS, testa filtros/autenticação e abre o PDF gerado via
PyMuPDF. O PDF de QA foi renderizado com Poppler e inspecionado visualmente.
Depois do ajuste final, 4 testes focados do novo relatório, 25 testes do
relatório de agente preexistente e a regressão ampla com 761 testes
(5 ignorados) passaram em banco de teste isolado. Os avisos `ResourceWarning`
de conexões SQLite em módulos antigos permaneceram, sem falha na suíte.

Validação do formato `1.65.1`: 30 testes focados e a regressão isolada com
762 testes (5 ignorados) passaram. Uma amostra A4 paisagem foi renderizada
com Poppler e conferida visualmente: blocos de 4-5 linhas, sem cortes no
resumo dos depósitos, com colunas alinhadas. Os arquivos de QA foram
removidos. Em 02/10/2026, `/login` respondeu `Endemias v1.65.0`; o formato
compacto ainda depende de reinício do serviço para aparecer.
