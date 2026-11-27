CREATE TABLE IF NOT EXISTS geovsatt_posicoes_coletas (
    id_coleta TEXT PRIMARY KEY REFERENCES coletas(id_coleta) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude > -90 AND latitude < 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude > -180 AND longitude < 180),
    atualizado_em TEXT NOT NULL
);
