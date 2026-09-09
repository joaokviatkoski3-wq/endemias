CREATE TABLE logradouros_oficiais (
    id_logradouro text PRIMARY KEY,
    nome text NOT NULL,
    nome_normalizado text NOT NULL,
    localidade text NOT NULL,
    ativo boolean NOT NULL DEFAULT true,
    origem_hash char(64) NOT NULL,
    importado_em text NOT NULL,
    atualizado_em text NOT NULL
);

CREATE INDEX idx_logradouros_nome_normalizado
    ON logradouros_oficiais (nome_normalizado);

CREATE INDEX idx_logradouros_ativo_nome
    ON logradouros_oficiais (ativo, nome);
