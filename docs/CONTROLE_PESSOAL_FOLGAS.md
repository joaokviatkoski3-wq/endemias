# Controle de Pessoal — Folgas e Ausências

O módulo administrativo reúne as abas **Servidores** e **Folgas e Ausências**.
A aba de folgas abre em `/admin/agentes?aba=folgas`. Admin e superadmin podem
consultar e registrar ocorrências no Endemias e no Ambiental. O saldo acompanha
o cadastro do servidor nos dois setores, e cada lançamento registra o setor de
origem.

## Operação

1. Em **Conceder saldo**, informe a atividade que originou o crédito, sua data,
   a quantidade aprovada e a validade. Registre o número do ofício ou protocolo,
   quando houver. Meio dia equivale a uma unidade e um dia equivale a duas.
2. Na miniagenda, selecione uma data ou use **Registrar ocorrência**. A folga
   reserva o saldo imediatamente. Meio dia exige início e fim no mesmo dia,
   de acordo com a jornada do servidor. Para registrar uma folga de dia anterior,
   informe o motivo na observação e confirme seu uso em seguida.
3. Após o fim do período, abra a ocorrência **A confirmar** e confirme a
   utilização. Para corrigir um registro, cancele com motivo e lance o correto.
4. Para registrar uma falta, escolha dia inteiro ou informe os horários reais.
   Classifique como pendente de justificativa, justificada, abonada ou não
   justificada. Atualize a classificação quando houver decisão administrativa.

O consumo usa os créditos válidos na data da folga, em ordem de vencimento,
incluindo o último dia de validade. Um dia pode consumir dois créditos de meio
dia. Cancelar uma ocorrência libera suas reservas ou estorna a utilização. A
validade original continua aplicável, de modo que o estorno de um crédito
vencido fica no saldo expirado. Cancele primeiro as ocorrências vinculadas para
cancelar um crédito com consumo ativo. Faltas são registradas separadamente do
saldo. A miniagenda usa mês, semana e lista, e o extrato reúne os lançamentos
inclusive de servidores inativos. Para inativos, use o extrato para consultar
ou corrigir registros existentes.

O módulo apoia a gestão interna. A autorização e a validade de cada folga
seguem a orientação do RH. Use referências administrativas e mantenha
documentos médicos no fluxo oficial de pessoal.

## Banco e validação

A migração PostgreSQL `0052_pessoal_folgas.sql` acrescenta as tabelas de
créditos, ocorrências e consumos. A inicialização SQLite prepara tabelas
equivalentes no ambiente de ensaio. As operações de saldo são serializadas por
servidor no PostgreSQL e dentro de uma transação de escrita no SQLite. As
alterações gravam auditoria na mesma transação. Antes da implantação, confira
o número da migração após integrar o trabalho paralelo e ensaie no banco de
teste com contas administrativas dos dois perfis.
