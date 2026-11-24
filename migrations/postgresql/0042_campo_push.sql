CREATE TABLE campo_push_aparelhos (
    id_usuario bigint PRIMARY KEY REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_agente bigint NOT NULL REFERENCES agentes(id_agente) ON DELETE CASCADE,
    sessao_hash text NOT NULL,
    senha_vinculo text NOT NULL,
    endpoint text NOT NULL,
    inscrito_em text NOT NULL,
    ultimo_teste bigint NOT NULL DEFAULT 0,
    teste_em bigint NOT NULL DEFAULT 0
);

CREATE TABLE campo_push_entregas (
    id_usuario bigint NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_agente bigint NOT NULL REFERENCES agentes(id_agente) ON DELETE CASCADE,
    id_resultado bigint NOT NULL,
    versao text NOT NULL,
    PRIMARY KEY (id_usuario, id_agente, id_resultado)
);
