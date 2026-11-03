-- Registro duravel e independente da limpeza de auditoria.
-- Somente aplicar em producao na janela autorizada, depois de backup validado.
CREATE TABLE IF NOT EXISTS usuarios_termos (
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id_usuario),
    termo_hash TEXT NOT NULL,
    versao TEXT NOT NULL,
    texto_termo TEXT NOT NULL,
    aceito_em TEXT NOT NULL,
    ip TEXT NOT NULL,
    PRIMARY KEY (usuario_id, termo_hash)
);
