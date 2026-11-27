CREATE TABLE IF NOT EXISTS geovsatt_posicoes_tubitos_liraa (
    id_tubito bigint PRIMARY KEY REFERENCES liraa_visita_tubitos(id_tubito) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude > -90 AND latitude < 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude > -180 AND longitude < 180),
    atualizado_em TEXT NOT NULL
);
