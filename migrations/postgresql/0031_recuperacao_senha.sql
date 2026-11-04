-- Recuperacao assistida: um link corrente por conta, apenas hash no banco.
CREATE TABLE IF NOT EXISTS usuarios_recuperacao_senha (
    usuario_id BIGINT PRIMARY KEY REFERENCES usuarios(id_usuario),
    token_hash TEXT NOT NULL UNIQUE,
    senha_vinculo TEXT NOT NULL,
    criado_por BIGINT NOT NULL REFERENCES usuarios(id_usuario),
    criado_em TEXT NOT NULL,
    expira_em BIGINT NOT NULL,
    usado_em TEXT
);
