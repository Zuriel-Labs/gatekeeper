"""Docker build version injection must produce valid package metadata."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


@pytest.mark.parametrize("supplied,expected", [("", "0.0.0"), ("1.2.3", "1.2.3")])
def test_build_version_injection(tmp_path, supplied, expected):
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname = "aigatekeeper"\ndynamic = ["version"]\n')
    script = Path(__file__).resolve().parents[1] / "scripts" / "set_version.py"
    subprocess.run(
        [sys.executable, str(script), str(project)],
        env={**os.environ, "BUILD_VERSION": supplied},
        check=True,
    )
    assert tomllib.loads(project.read_text())["project"]["version"] == expected
