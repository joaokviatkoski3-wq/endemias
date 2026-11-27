CREATE TABLE IF NOT EXISTS geovsatt_dengue (
    chave TEXT PRIMARY KEY,
    ano INTEGER NOT NULL,
    notificacao TEXT NOT NULL,
    data_notificacao TEXT,
    data_bloqueio TEXT,
    origem TEXT,
    unidade TEXT,
    resultado TEXT,
    endereco TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    conflito INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS geovsatt_dengue_sync (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sincronizado_em TEXT NOT NULL,
    total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS geovsatt_enderecos_verificados (
    chave TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    fonte TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
