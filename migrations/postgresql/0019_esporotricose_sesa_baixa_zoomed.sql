-- Corrige a confusao entre procedencia do itraconazol e registro da baixa.
-- Zoomed e o sistema de baixa; SESA e a fonte antes rotulada como Zoomed.
-- A situacao de baixa de cada entrega e preservada, inclusive a municipal.
ALTER TABLE esporotricose_doentes_entregas
    DROP CONSTRAINT ck_esporo_entregas_fonte_medicacao;
ALTER TABLE esporotricose_estoque_medicacao
    DROP CONSTRAINT ck_esporo_estoque_fonte_medicacao;

UPDATE esporotricose_doentes_entregas
   SET fonte_medicacao = 'SESA'
 WHERE fonte_medicacao = 'Zoomed';
UPDATE esporotricose_estoque_medicacao
   SET fonte_medicacao = 'SESA'
 WHERE fonte_medicacao = 'Zoomed';

ALTER TABLE esporotricose_doentes_entregas
    ALTER COLUMN fonte_medicacao SET DEFAULT 'SESA';
ALTER TABLE esporotricose_estoque_medicacao
    ALTER COLUMN fonte_medicacao SET DEFAULT 'SESA';

ALTER TABLE esporotricose_doentes_entregas
    ADD CONSTRAINT ck_esporo_entregas_fonte_medicacao
    CHECK (fonte_medicacao IN ('SESA', 'Município'));
ALTER TABLE esporotricose_estoque_medicacao
    ADD CONSTRAINT ck_esporo_estoque_fonte_medicacao
    CHECK (fonte_medicacao IN ('SESA', 'Município'));
