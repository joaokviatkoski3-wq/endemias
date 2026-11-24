ALTER TABLE liraa_leituras
    ADD COLUMN aegypt_exuvias BIGINT NOT NULL DEFAULT 0 CHECK (aegypt_exuvias >= 0),
    ADD COLUMN albopictus_exuvias BIGINT NOT NULL DEFAULT 0 CHECK (albopictus_exuvias >= 0),
    ADD COLUMN outra_exuvias BIGINT NOT NULL DEFAULT 0 CHECK (outra_exuvias >= 0);
