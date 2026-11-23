import pytest

from otprunner import i18n


@pytest.fixture(autouse=True)
def english():
    """Los tests comprueban los textos fuente (inglés); test_i18n prueba las traducciones."""
    i18n.setup("en")
    yield
    i18n.setup("en")
