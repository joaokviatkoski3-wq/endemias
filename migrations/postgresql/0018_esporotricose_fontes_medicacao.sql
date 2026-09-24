-- Diferencia a procedência do itraconazol sem alterar os lançamentos legados.
-- Até esta migração, todas as entradas e entregas registradas eram da Zoomed.
ALTER TABLE esporotricose_doentes_entregas
    ADD COLUMN fonte_medicacao text NOT NULL DEFAULT 'Zoomed';
ALTER TABLE esporotricose_estoque_medicacao
    ADD COLUMN fonte_medicacao text NOT NULL DEFAULT 'Zoomed';

ALTER TABLE esporotricose_doentes_entregas
    ADD CONSTRAINT ck_esporo_entregas_fonte_medicacao
    CHECK (fonte_medicacao IN ('Zoomed', 'Município'));
ALTER TABLE esporotricose_estoque_medicacao
    ADD CONSTRAINT ck_esporo_estoque_fonte_medicacao
    CHECK (fonte_medicacao IN ('Zoomed', 'Município'));
