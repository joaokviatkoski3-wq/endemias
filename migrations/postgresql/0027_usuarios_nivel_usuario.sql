-- Adiciona o nivel de acesso 'usuario' (somente leitura, com a identidade dos
-- demais agentes ocultada) ao CHECK de nivel das contas.
ALTER TABLE usuarios
    DROP CONSTRAINT ck_usuarios_01;

ALTER TABLE usuarios
    ADD CONSTRAINT ck_usuarios_01
        CHECK (nivel IN ('admin','operador','visualizador','usuario'));
