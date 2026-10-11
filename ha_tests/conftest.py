import pytest
from pathlib import Path
from shutil import copytree, ignore_patterns


@pytest.fixture
def hass_config_dir(tmp_path):
    # HA mounts its config directory before importing custom_components. Install
    # the real package there rather than loading the test plugin's sample package.
    copytree(Path(__file__).resolve().parents[1]/"custom_components",
             tmp_path/"custom_components",ignore=ignore_patterns("__pycache__"))
    return str(tmp_path)


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    yield
