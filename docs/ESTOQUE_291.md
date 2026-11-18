# Estoque e dispensa municipal do ZooMed — versão ativa 2.9.1

Ativada em 18/11/2026, às 11h40 (America/Sao_Paulo), release 5074f63.
Segundo lote aplicado em seguida, com oito auditorias e confirmação por nova
conexão. Nenhuma migração de esquema. Backups PostgreSQL e completo feitos,
preservação conferida de 98 tabelas e arquivos operacionais, prova da conta
limitada e automação Kobo restabelecida. Entradas públicas/locais dos dois
setores e portal responderam HTTP 200 exibindo 2.9.1.

Resultado confirmado: 2.650 cápsulas físicas (930 Município + 1.720 SESA),
das quais 2.590 registradas no ZooMed (870 Município + 1.720 SESA), 60 municipais
dispensadas e zero baixas pendentes. Estoque calculado 640 (SESA 580, Município
60), necessidade quantificada 880 em 11 ativos e déficit 240. Não houve contagem
física. Receitas, anexos, estoque manual e situações clínicas preservados.

Conferência por tutor/data/fonte/quantidade das 85 entregas com baixa: 84
coincidem com a planilha original. Em 18/11, o operador confirmou que as duas
entregas de Celoni são de 13/03/2026, como já constam no VSATT. A linha 18 da
planilha recebida informa 13/03/2025: considerar 13/03/2026 na conciliação por
confirmação expressa do operador. As 85 entregas estão conciliadas com essa
correção da fonte; não há pendência de ano/animal. A planilha original foi
preservada e não houve nova alteração de entrega no banco nem no ZooMed.
Os dois lançamentos municipais dispensados explicam os 87 registros físicos.

## Regra confirmada pelo operador

Medicamento municipal entregue a partir da entrega de Suelen (08/11/2026)
fica somente no VSATT e não exige lançamento no ZooMed. Pitoquinha é outro
caso já abrangido. Continua sendo saída física e reduz estoque e necessidade
da receita. SESA e entregas municipais anteriores seguem a regra histórica.
Baixas já realizadas permanecem como Sim, inclusive municipais.

Estado Não se aplica nas entregas; protegido também na API, inclusive quando
um cliente antigo envia Não para uma nova entrega municipal. O formulário
seleciona a dispensa ao escolher fonte/data elegíveis. Ao mudar para SESA ou
data anterior ao marco, volta à baixa pendente. Sem data, uma nova entrega
municipal usa a data atual para a regra, sem inventar uma data no cadastro.

Filtros, lista de animais, detalhe, exportação CSV, Entregas por fonte e
card de estoque distinguem registrada, pendente e dispensada. Animal sem
entregas mostra Sem entregas, sem inventar baixa pendente ou concluída.
Um animal com histórico registrado e entrega dispensada pode continuar
mostrando Sim no resumo das baixas exigíveis; cada entrega mantém seu estado.

Card mostra total físico de entregas e fontes, total com baixa ZooMed por
fonte, pendentes e dispensadas. Dados locais, sem sincronização automática.
Layout de estoque corrigido para impedir que movimentos alarguem a página no
celular. Edição de entregas usa controles com espaçamento e quebra de linha.

## Segundo lote de correções confirmado pelo usuário

Pedido explícito: Caramelo não recebeu por óbito anterior; Peralta não recebeu
a entrega de 21/10. Excluir somente entregas 45/91, preservando receitas,
cadastros e anexos. Suelen e Pitoquinha receberam: manter 88/96 e marcar
Não se aplica. Usuário confirmou as identidades de Elisama e do tutor de Mika:
data 31 para 04/04/2026, fontes 43/44 para Município, incluir entrega SESA
de Mika de 27/10/2026 na receita 75.

Utilitário específico scripts/corrigir_entregas_confirmadas_20261118.py:
valida IDs/receitas/animais/data/quantidade/fonte/baixa antes de escrever,
gera backup validado, transação única e auditoria incluindo o registro inteiro
das exclusões. Confere a assinatura esperada das cinco tabelas antes de commit
e reconfere por nova conexão após commit. Aplica a mesma dispensa a eventuais
novas entregas municipais pendentes com data desde 08/11, preservando Sim.
Não altera estoque manual, prescrições, situação clínica nem arquivos.

Projeção preparada e depois confirmada na aplicação: 2.650 cápsulas físicas
(930 Município, 1.720 SESA), sendo 2.590 com baixa (870 Município, 1.720 SESA)
e 60 municipais dispensadas. Saldo calculado 640 e necessidade 880, déficit
240. Valores confirmados após a aplicação; não são contagem
física. A dúvida sobre o ano de Celoni foi encerrada pelo operador: ambas são
de 2026. Os vínculos com Banguela/Mimi e as datas no VSATT ficam preservados.

## Validação e implantação

Sem migração de esquema: baixa_zoomed já é texto. Ensaios de UI com dados
fictícios em Chromium a 1440/390 px verificaram seleção de fonte/data, envio,
baixas antigas preservadas, card e ausência de rolagem horizontal da página.
Testes cobrem o marco temporal, SESA, dispensa municipal, preservação de baixa
registrada, filtros/tela/CSV, estoque e rollback do lote completo em erro.
Os 70 testes de Esporotricose passaram antes do último acréscimo de proteção
ao editar legado sem data; os cinco testes da regra passaram após o acréscimo.
Quatro testes do lote específico e cinco do utilitário anterior passaram.
Execução ampla: 1.248 testes em 587 s, seis pulados. Detectou expectativa de
rótulo antigo no smoke e falta de pywin32 no Python de testes; o rótulo foi
atualizado para a regra nova e a dependência temporária foi incluída no ambiente
de ensaio. Reexecução dos dois casos e nove testes de transação: 11 passaram.
Nenhuma dependência foi instalada no Python do serviço.

Ativador scripts/ativar_estoque_291_windows.py usa a rotina controlada existente:
backup PostgreSQL e completo, pausa Kobo, janela curta, integração ff-only,
preservação de tabelas e arquivos, prova da conta limitada e verificação das
entradas. Resultado em C:\ProgramData\EndemiasWeb\ativacao-estoque291-resultado.json:
aplicado/concluído, sem migração, 98 tabelas preservadas, todas as entradas OK.
Backup completo: D:\BackupsEndemias\backups_web\completos\endemias_completo_20261118_113928.zip
(311.597.161 bytes), SHA-256
93323ff45490d0b2081aa06d2ce5e1075a3cd1552bf442f296a9d2a32d43ffa1.

Backup imediatamente anterior às oito correções:
C:\ProgramData\EndemiasWeb\confirmacoes-zoomed-20261118-114001\antes_conta_limitada.dump
(7.756.459 bytes, catálogo validado), SHA-256
de54572fd95ab9dbcbe5fa27a4b1f1685239b87e9dcd99fc3135cf83952bd37e.
Diretório privado guarda fonte, estado anterior e resultado nominal; nenhum
desses dados pessoais foi versionado. Histórico das exclusões está na auditoria.
SQLite congelado preservou o SHA-256 964152e21de44b4fff985f72a0d7945e8e7dcf260bbb019708b868c3b3a7a025.
