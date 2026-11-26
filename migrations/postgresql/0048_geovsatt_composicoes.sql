CREATE TABLE IF NOT EXISTS geovsatt_composicoes (
    id_composicao BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    configuracao TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_geovsatt_composicoes_usuario
    ON geovsatt_composicoes(usuario_id, atualizada_em DESC, id_composicao DESC);
