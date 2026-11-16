CREATE TABLE IF NOT EXISTS amostra_animais_anexos (
    id_anexo TEXT PRIMARY KEY,
    id_amostra TEXT NOT NULL REFERENCES amostras_animais(id_amostra) ON DELETE CASCADE,
    nome_original TEXT NOT NULL,
    caminho_rel TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    criado_em TEXT NOT NULL,
    criado_por TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_amostra_animais_anexos_amostra ON amostra_animais_anexos(id_amostra);
