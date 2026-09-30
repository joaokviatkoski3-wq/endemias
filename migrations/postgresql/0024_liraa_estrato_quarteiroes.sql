-- Uma localidade pode ser repartida entre estratos de um mesmo ciclo.
-- A tabela de localidades da 0023 permanece para leitura de planos antigos;
-- ao editar um estrato antigo, seus vínculos passam para esta tabela.
CREATE TABLE liraa_estrato_quarteiroes (
    id_estrato bigint NOT NULL REFERENCES liraa_estratos(id_estrato) ON DELETE CASCADE,
    id_ciclo bigint NOT NULL REFERENCES liraa_ciclos(id_ciclo) ON DELETE CASCADE,
    id_localidade bigint NOT NULL REFERENCES localidades(id_localidade),
    quarteirao text NOT NULL,
    PRIMARY KEY (id_estrato, id_localidade, quarteirao),
    CONSTRAINT uq_liraa_ciclo_quarteirao UNIQUE (id_ciclo, id_localidade, quarteirao)
);
