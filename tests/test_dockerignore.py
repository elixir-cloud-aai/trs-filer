"""Tests for the Docker build context rules."""

from pathlib import Path

DOCKERIGNORE = Path(__file__).parents[1] / ".dockerignore"


def test_local_env_files_are_excluded() -> None:
    """Local `.env` files never reach the build, also not in included paths."""
    lines = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    assert "**/.env*" in lines
    # Rules apply in order, so nothing later may include such a file again
    assert not [
        line for line in lines[lines.index("**/.env*") :] if line.startswith("!")
    ]
