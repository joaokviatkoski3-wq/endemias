CREATE TABLE avisos_campo_lidos (
    id_usuario bigint NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_agente bigint NOT NULL REFERENCES agentes(id_agente) ON DELETE CASCADE,
    id_resultado bigint NOT NULL,
    versao text NOT NULL,
    PRIMARY KEY (id_usuario, id_agente, id_resultado)
);
