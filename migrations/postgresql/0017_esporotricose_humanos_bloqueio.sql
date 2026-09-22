ALTER TABLE esporotricose_pacientes_humanos
    ADD COLUMN bloqueio text
    CONSTRAINT ck_esporo_paciente_bloqueio
    CHECK (bloqueio IS NULL OR bloqueio IN ('Realizado', 'Não realizado'));
