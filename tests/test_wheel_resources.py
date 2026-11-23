from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tools.check_wheel_resources import REQUIRED_RESOURCES, check_wheel

ROOT = Path(__file__).resolve().parents[1]


def _wheel(path: Path, members: set[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, b"resource")
    return path


def test_check_wheel_accepts_all_required_runtime_resources(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "complete.whl", REQUIRED_RESOURCES)

    check_wheel(wheel)


def test_check_wheel_reports_omitted_runtime_resources(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "incomplete.whl", REQUIRED_RESOURCES - {"apps/web/app.js"})

    with pytest.raises(ValueError, match=r"apps/web/app\.js"):
        check_wheel(wheel)


def test_wheel_audit_requires_every_core_skillpack_and_schema() -> None:
    skillpack_files = {
        f"core/skillpacks/{path.relative_to(ROOT / 'packages/core/skillpacks').as_posix()}"
        for path in (ROOT / "packages/core/skillpacks").rglob("*.md")
    }
    schema_files = {
        f"core/schemas/{path.name}" for path in (ROOT / "packages/core/schemas").glob("*.json")
    }

    assert skillpack_files <= REQUIRED_RESOURCES
    assert schema_files <= REQUIRED_RESOURCES


@pytest.mark.parametrize("payload", [b"not a wheel", b"PK\x03\x04broken"])
def test_check_wheel_rejects_unreadable_archives(tmp_path: Path, payload: bytes) -> None:
    wheel = tmp_path / "invalid.whl"
    wheel.write_bytes(payload)

    with pytest.raises(ValueError, match="not a readable wheel archive"):
        check_wheel(wheel)
