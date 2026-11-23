import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_CADDYFILE = ROOT / "apps" / "remote" / "deploy" / "Caddyfile"
_COMPOSE = ROOT / "apps" / "remote" / "deploy" / "compose.yaml"
_BLENDER_DOCKERFILE = ROOT / "apps" / "blender_mcp_server" / "Dockerfile"
_ROBLOX_DOCKERFILE = ROOT / "apps" / "roblox_mcp_server" / "Dockerfile"
_CI = ROOT / ".github" / "workflows" / "ci.yml"
_PYPROJECT = ROOT / "pyproject.toml"
_BLENDER_SERVER = ROOT / "apps" / "blender_mcp_server" / "server.py"
_ROBLOX_SERVER = ROOT / "apps" / "roblox_mcp_server" / "server.py"


def _service_block(compose: str, service_name: str) -> str:
    lines = compose.splitlines()
    start = lines.index(f"  {service_name}:")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ")
            and not lines[index].startswith("    ")
            and lines[index].endswith(":")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_proxy_bounds_how_long_a_client_may_take_to_send_a_request() -> None:
    caddyfile = _CADDYFILE.read_text(encoding="utf-8")
    options = caddyfile[: caddyfile.index("{$BLENDER_DOMAIN}")]

    assert "read_header" in options
    assert "read_body" in options
    # A write timeout would cut off a Blender build or cloud validation that answers
    # only when it finishes.
    assert re.search(r"^\s*write\s+\d", options, re.MULTILINE) is None


def test_public_proxy_routes_are_limited_to_required_http_methods() -> None:
    caddyfile = _CADDYFILE.read_text(encoding="utf-8")
    expected_matchers = {
        "@blender_mcp": ("path /mcp", "method POST"),
        "@blender_artifacts": ("path /artifacts/*", "method GET"),
        "@downloads": ("path /downloads/*", "method GET"),
        "@roblox_mcp": ("path /mcp", "method POST"),
    }

    for matcher, conditions in expected_matchers.items():
        start = caddyfile.index(matcher)
        block_start = caddyfile.index("{", start)
        block_end = caddyfile.index("}", block_start)
        block = caddyfile[block_start + 1 : block_end]
        assert all(condition in block for condition in conditions), matcher

    assert "/healthz" not in caddyfile


def test_public_proxy_body_limits_cover_each_mcp_server_limit() -> None:
    caddyfile = _CADDYFILE.read_text(encoding="utf-8")

    def caddy_limit_bytes(matcher: str) -> int:
        match = re.search(
            rf"handle\s+{re.escape(matcher)}\s*\{{\s*request_body\s*\{{\s*"
            r"max_size\s+(\d+)([KMG]?B)\b",
            caddyfile,
            re.S,
        )
        assert match is not None, f"{matcher} must have an explicit request-body limit"
        amount = int(match.group(1))
        multiplier = {"B": 1, "KB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000}
        return amount * multiplier[match.group(2).upper()]

    def server_limit_bytes(path: Path) -> int:
        source = path.read_text(encoding="utf-8")
        match = re.search(r"^MAX_REQUEST_BYTES\s*=\s*([\d_]+)\s*$", source, re.M)
        assert match is not None, f"{path.name} must declare an integer request-body limit"
        return int(match.group(1).replace("_", ""))

    assert caddy_limit_bytes("@blender_mcp") >= server_limit_bytes(_BLENDER_SERVER)
    assert caddy_limit_bytes("@roblox_mcp") >= server_limit_bytes(_ROBLOX_SERVER)

    deployment_guide = (_CADDYFILE.parent / "README.md").read_text(encoding="utf-8")
    assert "`/healthz` endpoints are intentionally private" in deployment_guide


def test_only_the_tls_edge_publishes_ports_and_mcp_services_remain_hardened() -> None:
    compose = _COMPOSE.read_text(encoding="utf-8")
    edge = _service_block(compose, "edge")
    assert '"80:80"' in edge
    assert '"443:443"' in edge

    for service_name, pids_limit, memory_limit, cpu_limit in (
        ("blender-mcp", "128", "6g", "4"),
        ("roblox-mcp", "64", "512m", "1"),
    ):
        block = _service_block(compose, service_name)
        assert "    ports:" not in block
        assert "    read_only: true" in block
        assert "    cap_drop:\n      - ALL" in block
        assert "      - no-new-privileges:true" in block
        assert f"    pids_limit: {pids_limit}" in block
        assert f"    mem_limit: {memory_limit}" in block
        assert f"    cpus: {cpu_limit}" in block

    blender = _service_block(compose, "blender-mcp")
    assert "BLENDER_MCP_PUBLIC_ORIGIN: https://${BLENDER_DOMAIN" in blender


def test_remote_asset_decoder_dependency_and_runtime_smokes_stay_wired() -> None:
    assert '"Pillow==13.0.0"' in _PYPROJECT.read_text(encoding="utf-8")
    for dockerfile in (_BLENDER_DOCKERFILE, _ROBLOX_DOCKERFILE):
        assert 'pip install --no-cache-dir ".[roblox-assets]"' in dockerfile.read_text(
            encoding="utf-8"
        )

    workflow = _CI.read_text(encoding="utf-8")
    assert "--python tools/smoke_blender_extension.py" in workflow
    assert "tools/smoke_blender_cutaway_mcp.py /opt/blender/blender" in workflow
    assert "tools/smoke_blender_cutaway_mcp.py ./tools/smoke_blender_cutaway_mcp.py" in (
        _BLENDER_DOCKERFILE.read_text(encoding="utf-8")
    )
    assert "Smoke-test complete PNG and JPEG pixel decoding" in workflow
    assert "-m apps.roblox_mcp_server.smoke_assets" in workflow
    assert "RGA_ASSET_IMAGE_SMOKE_OK" in (
        ROOT / "apps" / "roblox_mcp_server" / "smoke_assets.py"
    ).read_text(encoding="utf-8")
