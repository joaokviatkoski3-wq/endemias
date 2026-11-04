-- Presenca aproximada: ultimo sinal persistente e sessoes recentes.
CREATE TABLE IF NOT EXISTS usuarios_presenca (
    usuario_id BIGINT PRIMARY KEY REFERENCES usuarios(id_usuario),
    ultima_presenca BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios_presenca_sessoes (
    sessao_hash TEXT PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id_usuario),
    senha_vinculo TEXT NOT NULL,
    ultima_presenca BIGINT NOT NULL,
    encerrada_em BIGINT
);
CREATE INDEX IF NOT EXISTS idx_presenca_sessoes_ultima ON usuarios_presenca_sessoes(ultima_presenca);
