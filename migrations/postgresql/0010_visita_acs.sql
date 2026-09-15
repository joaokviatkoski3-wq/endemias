CREATE TABLE visita_acs (
    id_visita text NOT NULL
        REFERENCES visitas(id_visita) ON DELETE CASCADE,
    acs_codigo text NOT NULL,
    CONSTRAINT pk_visita_acs PRIMARY KEY (id_visita, acs_codigo)
);

CREATE INDEX idx_visita_acs_codigo ON visita_acs(acs_codigo);
