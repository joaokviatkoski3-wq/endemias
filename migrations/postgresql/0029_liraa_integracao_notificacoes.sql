-- Vínculo localizado: visitas/tubos/leituras LIRAa permanecem nas tabelas próprias.
ALTER TABLE focos_positivos ADD COLUMN id_visita_liraa bigint
    REFERENCES liraa_visitas(id_visita) ON DELETE CASCADE;
CREATE UNIQUE INDEX idx_focos_visita_liraa ON focos_positivos(id_visita_liraa);
-- Preserva o campo antigo e acrescenta a identificação textual do levantamento.
ALTER TABLE focos_positivos ADD COLUMN quarteirao_liraa text;

ALTER TABLE liraa_leituras ADD COLUMN origem text NOT NULL DEFAULT 'sistema'
    CHECK (origem IN ('sistema','kobo'));
ALTER TABLE liraa_leituras ADD COLUMN kobo_uuid text;
CREATE UNIQUE INDEX idx_liraa_leituras_kobo_uuid ON liraa_leituras(kobo_uuid);
