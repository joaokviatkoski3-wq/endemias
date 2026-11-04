ALTER TABLE usuarios ADD COLUMN setor TEXT NOT NULL DEFAULT 'endemias'
    CHECK (setor IN ('endemias','ambiental'));
ALTER TABLE agenda_eventos ADD COLUMN setor TEXT NOT NULL DEFAULT 'endemias'
    CHECK (setor IN ('endemias','ambiental'));
CREATE INDEX idx_agenda_setor_data ON agenda_eventos(setor,data_inicio);

ALTER TABLE importacoes ADD COLUMN setor TEXT NOT NULL DEFAULT 'legado' CHECK(setor IN ('endemias','ambiental','legado'));
CREATE INDEX idx_importacoes_setor_criado ON importacoes(setor,criado_em);

ALTER TABLE auditoria_eventos ADD COLUMN setor TEXT NOT NULL DEFAULT 'legado' CHECK(setor IN ('endemias','ambiental','legado'));
CREATE INDEX idx_auditoria_setor_criado ON auditoria_eventos(setor,criado_em);
