ALTER TABLE usuarios
    ADD COLUMN id_agente bigint
        REFERENCES agentes(id_agente);

CREATE INDEX idx_usuarios_agente
    ON usuarios(id_agente)
    WHERE id_agente IS NOT NULL;
