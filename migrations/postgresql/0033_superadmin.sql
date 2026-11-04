-- Amplia somente o CHECK; a conta pessoal e promovida na janela controlada.
ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_01;
ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_01
    CHECK (nivel IN ('superadmin','admin','operador','visualizador','usuario'));
CREATE UNIQUE INDEX idx_usuarios_superadmin_unico ON usuarios(nivel) WHERE nivel='superadmin';
