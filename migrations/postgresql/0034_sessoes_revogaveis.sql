CREATE TABLE usuarios_sessoes (
    sessao_hash TEXT PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id_usuario),
    senha_vinculo TEXT NOT NULL,
    criada_em BIGINT NOT NULL,
    expira_em BIGINT NOT NULL,
    revogada_em BIGINT
);
CREATE INDEX idx_usuarios_sessoes_expira ON usuarios_sessoes(expira_em);
