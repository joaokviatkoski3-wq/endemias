CREATE TABLE registro_geografico_geojson_importacoes (
    id_importacao text PRIMARY KEY,
    arquivo_nome text NOT NULL,
    arquivo_sha256 text NOT NULL,
    importado_em text NOT NULL,
    importado_por_usuario_id bigint REFERENCES usuarios(id_usuario),
    importado_por_usuario_nome text,
    ativo boolean NOT NULL DEFAULT false,
    total_feicoes bigint NOT NULL CHECK (total_feicoes > 0)
);

CREATE TABLE registro_geografico_quarteiroes_geometrias (
    id_importacao text NOT NULL REFERENCES registro_geografico_geojson_importacoes(id_importacao),
    id_localidade bigint NOT NULL REFERENCES localidades(id_localidade),
    localidade text NOT NULL,
    localidade_origem text NOT NULL,
    quarteirao text NOT NULL,
    geometry_json text NOT NULL,
    properties_json text NOT NULL,
    geometry_hash text NOT NULL,
    centro_lat double precision NOT NULL CHECK (centro_lat BETWEEN -90 AND 90),
    centro_lng double precision NOT NULL CHECK (centro_lng BETWEEN -180 AND 180),
    coordenadas bigint NOT NULL CHECK (coordenadas > 0),
    PRIMARY KEY (id_importacao, id_localidade, quarteirao)
);

CREATE INDEX idx_rg_geojson_importacoes_ativo
    ON registro_geografico_geojson_importacoes (ativo, importado_em DESC);
CREATE INDEX idx_rg_geojson_geometrias_chave
    ON registro_geografico_quarteiroes_geometrias (id_localidade, quarteirao);
