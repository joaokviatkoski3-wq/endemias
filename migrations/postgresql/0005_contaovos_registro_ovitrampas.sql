CREATE TABLE contaovos_registro_ovitrampas (
    ovitrampa_id_remoto  text PRIMARY KEY,
    ovitrap_id           text,
    latitude             double precision,
    longitude            double precision,
    coordenada_erro      bigint,
    municipio            text,
    municipio_codigo     text,
    estado               text,
    ovos_media           double precision,
    quarteirao_remoto_id text,
    grupo_remoto_id      text,
    usuario_remoto_id    text,
    atualizado_remoto_em text,
    sincronizado_em      text NOT NULL
);

CREATE INDEX idx_contaovos_registro_ovitrampas_sincronizado
    ON contaovos_registro_ovitrampas (sincronizado_em DESC);
