import pytest


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    yield
