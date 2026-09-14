ALTER TABLE visitas
    ADD COLUMN acs_presente bigint,
    ADD COLUMN acs_nome text;

ALTER TABLE visitas
    ADD CONSTRAINT ck_visitas_acs_presente
    CHECK (acs_presente IN (0, 1));
