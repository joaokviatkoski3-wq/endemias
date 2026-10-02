# Histórico completo de visitas em PDF

Implementado no código `1.65.0` em 02/10/2026. A opção fica separada dos
resumos em **Relatório por Agente**, com filtros obrigatórios de agente,
data inicial e data final. A rota autenticada
`/relatorio-agente/visitas/pdf` entrega um PDF A4 real para download.

O relatório lê, sem alterar dados, todas as visitas do agente no intervalo
inclusivo nas tabelas `visitas` (PE/TB/TBO/PVE) e
`esporotricose_visitas`. Uma visita com vários agentes aparece uma vez no
relatório de cada participante. Não há limite artificial de 500 registros como
na lista operacional de esporotricose. As visitas são ordenadas por data e
hora, misturando as duas fontes cronologicamente.

Cada visita inclui os campos preenchidos do registro, inclusive identificação,
endereço, morador, horários, resultado, observações, equipe e ACS humanizado
quando o catálogo local tem o nome. Em vetores, seguem todos os registros de
depósitos inspecionados, tratamentos, coletas, resultados laboratoriais e
focos/notificações vinculados. Em esporotricose, seguem os animais registrados
na visita e o vínculo com imóvel acompanhado, quando existente. Campos vazios
são omitidos; zero é impresso. Dados pré-sistema que não estejam nessas tabelas
não são inventados nem recuperados de outra fonte.

O PDF contém dados pessoais e de saúde. Exige sessão como as páginas de
visitas, é entregue como anexo e envia `Cache-Control: private, no-store`.
Não grava PDF no servidor nem no banco. O arquivo salvo no computador do
usuário deve ser tratado conforme as mesmas restrições de acesso das visitas.

Dependência nova: `reportlab>=4.2,<5` em `requirements.txt`; instalada no
Python local de serviço em 02/10/2026 para teste. Não exige migração de banco.
O serviço oficial ainda precisa carregar o código novo para oferecer a opção;
não atribua a versão nova ao processo em execução sem verificar `/login`.

Validação: `tests/test_relatorio_visitas_completo.py` usa SQLite temporário,
inclui visita compartilhada por dois agentes, resultado laboratorial,
foco, animal e ACS, testa filtros/autenticação e abre o PDF gerado via
PyMuPDF. O PDF de QA foi renderizado com Poppler e inspecionado visualmente.
Depois do ajuste final, 4 testes focados do novo relatório, 25 testes do
relatório de agente preexistente e a regressão ampla com 761 testes
(5 ignorados) passaram em banco de teste isolado. Os avisos `ResourceWarning`
de conexões SQLite em módulos antigos permaneceram, sem falha na suíte.
