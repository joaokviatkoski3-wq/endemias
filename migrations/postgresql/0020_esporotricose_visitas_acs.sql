-- Acompanhamento de ACS nas visitas de Esporotricose, separado das PVE.
ALTER TABLE esporotricose_visitas
    ADD COLUMN acs_presente bigint,
    ADD COLUMN acs_nome text,
    ADD CONSTRAINT ck_esporo_visitas_acs_presente CHECK (acs_presente IN (0, 1));

CREATE TABLE esporotricose_visita_acs (
    id_visita text NOT NULL REFERENCES esporotricose_visitas(id_visita) ON DELETE CASCADE,
    acs_codigo text NOT NULL,
    CONSTRAINT pk_esporotricose_visita_acs PRIMARY KEY (id_visita, acs_codigo)
);
CREATE INDEX idx_esporo_visita_acs_codigo ON esporotricose_visita_acs(acs_codigo);
