"""Preparacao comum para testes carregados como pacote."""

import os


# A API Conta Ovos nao possui sandbox. O cliente oficial recusa rede real
# durante toda a suite; testes HTTP precisam injetar um transporte falso.
os.environ["ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK"] = "1"

from ._database_isolation import TEST_DB_PATH


__all__ = ["TEST_DB_PATH"]
