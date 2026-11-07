from urllib.parse import urlsplit

import pytest

from apps.roblox_mcp_server import downloads
from apps.roblox_mcp_server.downloads import DOWNLOAD_LIFETIME, PlaceDownloads


def test_link_is_readable_until_expiry_and_capacity_preserves_existing_links(monkeypatch):
    now = 100
    monkeypatch.setattr(downloads.time, "monotonic", lambda: now)
    monkeypatch.setattr(downloads, "_MAX_BYTES", 4)
    store = PlaceDownloads("https://games.example.com/")
    url = urlsplit(store.issue(b"abcd"))
    assert url.netloc == "games.example.com"
    assert store.read(url.path) == b"abcd"
    assert store.read(url.path + "?x") is None
    with pytest.raises(ValueError, match="full"):
        store.issue(b"x")
    now += DOWNLOAD_LIFETIME
    assert store.read(url.path) is None
    assert store.read(urlsplit(store.issue(b"game")).path) == b"game"


@pytest.mark.parametrize(
    "origin",
    ["http://public.example", "https://user@public.example", "https://public.example/untrusted"],
)
def test_download_authority_is_fixed(origin):
    with pytest.raises(ValueError):
        PlaceDownloads(origin)
