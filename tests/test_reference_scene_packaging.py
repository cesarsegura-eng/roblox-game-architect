from pathlib import Path

from tools.package_reference_scenes import render, write_output


def test_reference_scene_packager_writes_stable_lf_bytes(tmp_path: Path) -> None:
    output = tmp_path / "reference_scenes.json"

    write_output(output)

    content = output.read_bytes()
    assert b"\r\n" not in content
    assert content.decode("utf-8") == render()
