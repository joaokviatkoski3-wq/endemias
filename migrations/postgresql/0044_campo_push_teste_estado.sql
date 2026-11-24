ALTER TABLE campo_push_aparelhos ADD COLUMN teste_estado text NOT NULL DEFAULT 'nenhum'
    CHECK (teste_estado IN ('nenhum','agendado','aceito','expirado'));

UPDATE campo_push_aparelhos SET teste_estado='agendado' WHERE teste_em>0;
