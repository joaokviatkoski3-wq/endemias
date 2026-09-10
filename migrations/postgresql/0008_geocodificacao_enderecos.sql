ALTER TABLE enderecos_normalizados
    ADD COLUMN latitude double precision,
    ADD COLUMN longitude double precision,
    ADD COLUMN geocodificacao_status text NOT NULL DEFAULT 'pendente',
    ADD COLUMN geocodificacao_fonte text,
    ADD COLUMN geocodificacao_consulta text,
    ADD COLUMN geocodificacao_resultado text,
    ADD COLUMN geocodificacao_precisao text,
    ADD COLUMN geocodificacao_detalhes_json text,
    ADD COLUMN geocodificado_em text,
    ADD COLUMN geocodificado_por text;

ALTER TABLE enderecos_normalizados
    ADD CONSTRAINT ck_enderecos_geocodificacao_status CHECK (
        geocodificacao_status IN (
            'pendente', 'automatico', 'aproximado', 'nao_encontrado',
            'erro', 'aguarda_manual', 'manual'
        )
    );

CREATE INDEX idx_enderecos_geocodificacao_status
    ON enderecos_normalizados (geocodificacao_status);
