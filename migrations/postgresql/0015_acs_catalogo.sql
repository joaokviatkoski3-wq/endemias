CREATE TABLE acs_catalogo (
    acs_codigo text PRIMARY KEY,
    nome text NOT NULL,
    atualizado_em text NOT NULL
);

CREATE INDEX idx_acs_catalogo_nome ON acs_catalogo(nome);
