ALTER TABLE importacoes DROP CONSTRAINT IF EXISTS importacoes_setor_check;
ALTER TABLE importacoes
    ADD CONSTRAINT importacoes_setor_check
    CHECK (setor IN ('endemias','ambiental','legado','geo'));

ALTER TABLE auditoria_eventos DROP CONSTRAINT IF EXISTS auditoria_eventos_setor_check;
ALTER TABLE auditoria_eventos
    ADD CONSTRAINT auditoria_eventos_setor_check
    CHECK (setor IN ('endemias','ambiental','legado','geo'));
