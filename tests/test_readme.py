"""The README's Python samples must keep working against this SDK.

A sample that imports a renamed symbol is the most likely way documentation
goes stale, and ruff cannot see it: an imported name is a defined name as far
as a linter knows. So every ```python block in the README is parsed, and every
`from guardiano3 import X` is checked against the package's `__all__`.

The samples are not executed -- they need an API key and a live server.
"""

import ast
import re
from pathlib import Path

import pytest

import guardiano3

README = Path(__file__).resolve().parents[1] / "README.md"
FENCE = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)

SAMPLES = FENCE.findall(README.read_text(encoding="utf-8"))


def test_the_readme_has_python_samples():
    assert len(SAMPLES) >= 5


@pytest.mark.parametrize("code", SAMPLES, ids=[f"sample-{i}" for i in range(len(SAMPLES))])
def test_sample_parses_and_imports_only_exported_names(code):
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "guardiano3":
            for alias in node.names:
                assert alias.name in guardiano3.__all__, (
                    f"README sample imports {alias.name!r} from guardiano3, "
                    "which does not export it"
                )
