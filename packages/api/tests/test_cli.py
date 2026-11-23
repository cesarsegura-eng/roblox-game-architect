"""The operator command line: queue, approve, attest and status, against a temp data dir."""

import json
import shutil
from pathlib import Path

import pytest

from api import cli

ACTION = Path(__file__).resolve().parents[3] / "tools" / "examples" / "create-platform.json"
TOKEN = "cli-only-token-with-at-least-32-printable-characters"  # noqa: S105 - local test credential


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PLUGIN_AUTH_TOKEN", TOKEN)


def _status(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    capsys.readouterr()
    cli.main(["status"])
    return json.loads(capsys.readouterr().out)


def test_a_queued_item_is_unapproved_until_the_operator_approves_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["queue", str(ACTION)])
    assert "queued a-0001" in capsys.readouterr().out
    assert _status(capsys)["work"]["a-0001"]["state"] == "queued"  # type: ignore[index]

    cli.main(["approve", "a-0001"])

    assert _status(capsys)["work"]["a-0001"]["state"] == "approved"  # type: ignore[index]


def test_approving_an_unknown_item_exits_with_the_reason() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["approve", "a-9999"])

    assert raised.value.code
    assert TOKEN not in str(raised.value.code)


def test_a_missing_token_stops_before_touching_any_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PLUGIN_AUTH_TOKEN")

    with pytest.raises(SystemExit, match="PLUGIN_AUTH_TOKEN"):
        cli.main(["status"])
    assert not any(tmp_path.iterdir())


def test_an_attestation_needs_an_engaged_lock_and_prints_the_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="not engaged"):
        cli.main(["attest", "--actor", "operator"])

    assert cli.ATTESTATION_WARNING in capsys.readouterr().out


def test_an_actor_is_required_to_attest() -> None:
    with pytest.raises(SystemExit):
        cli.main(["attest"])


def test_the_data_directory_never_holds_the_credential(tmp_path: Path) -> None:
    cli.main(["queue", str(ACTION)])

    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert TOKEN.encode() not in path.read_bytes()


def test_a_queue_file_that_is_not_json_is_a_clean_exit(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    shutil.copy(ACTION, broken)
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        cli.main(["queue", str(broken)])

    assert raised.value.code
