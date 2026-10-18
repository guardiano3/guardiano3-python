"""The version is declared twice; they must agree."""

from importlib.metadata import version

import guardiano3


def test_the_module_version_matches_the_distribution():
    assert guardiano3.__version__ == version("guardiano3")
