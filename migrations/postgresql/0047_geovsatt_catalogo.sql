CREATE TABLE IF NOT EXISTS geovsatt_camadas (
    codigo TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    grupo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    configuracao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS geovsatt_versoes (
    id_versao BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo TEXT NOT NULL REFERENCES geovsatt_camadas(codigo),
    arquivo TEXT NOT NULL,
    geojson TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    total INTEGER NOT NULL CHECK (total > 0),
    tipo TEXT NOT NULL,
    metadados TEXT NOT NULL,
    autor_id BIGINT NOT NULL,
    criada_em TEXT NOT NULL,
    publicada_em TEXT,
    ativa INTEGER NOT NULL DEFAULT 0 CHECK (ativa IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_geovsatt_versao_ativa ON geovsatt_versoes(codigo) WHERE ativa = 1;
CREATE INDEX IF NOT EXISTS idx_geovsatt_historico ON geovsatt_versoes(codigo, id_versao DESC);
