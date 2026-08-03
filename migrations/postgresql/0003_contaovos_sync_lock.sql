ALTER TABLE contaovos_sync_cursor
    ADD COLUMN IF NOT EXISTS em_execucao_desde text;

ALTER TABLE contaovos_sync_cursor
    ADD COLUMN IF NOT EXISTS execucao_token text;
