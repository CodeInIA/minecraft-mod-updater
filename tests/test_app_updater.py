"""Self-update logic, with GitHub replaced by fake responses."""

import hashlib
import sys

import pytest

import app_updater


class FakeResponse:
    def __init__(self, json_data=None, content=b""):
        self._json, self._content = json_data, content
        self.headers = {"content-length": str(len(content))}

    def raise_for_status(self):
        pass

    def json(self):
        return self._json

    def iter_content(self, chunk_size):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def release_json(tag, digest="sha256:" + "0" * 64):
    return {"tag_name": tag, "html_url": f"https://github.com/x/releases/tag/{tag}", "assets": [
        {"name": name, "browser_download_url": f"https://github.com/x/{name}", "digest": digest}
        for name in app_updater.ASSET_NAMES.values()]}


@pytest.mark.parametrize("value, expected", [
    ("2.1.0", (2, 1, 0)), ("v2.0.10", (2, 0, 10)), ("V3.0", (3, 0)), ("dev", None), ("", None),
])
def test_parse_version(value, expected):
    assert app_updater.parse_version(value) == expected


def test_newer_versions_compare_numerically(monkeypatch):
    monkeypatch.setattr(app_updater, "APP_VERSION", "2.0.9")
    newer = app_updater.Release("2.0.10", "", None, None, None)
    older = app_updater.Release("2.0.8", "", None, None, None)
    assert app_updater.is_newer(newer) and not app_updater.is_newer(older)


def test_dev_build_never_updates(monkeypatch):
    monkeypatch.setattr(app_updater, "APP_VERSION", "dev")
    assert not app_updater.is_newer(app_updater.Release("99.0.0", "", None, None, None))


def test_fetch_latest_picks_the_asset_for_this_system(monkeypatch):
    monkeypatch.setattr(app_updater.requests, "get", lambda *a, **k: FakeResponse(release_json("v2.2.0")))
    release = app_updater.fetch_latest()
    assert release.version == "2.2.0"
    assert release.asset_name == app_updater.ASSET_NAMES[app_updater._platform_key()]
    assert release.sha256 == "0" * 64


def test_download_verifies_sha256(monkeypatch, tmp_path):
    payload = b"installer bytes" * 1000
    good = app_updater.Release("2.2.0", "", "https://x/file", "file.bin", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(app_updater.requests, "get", lambda *a, **k: FakeResponse(content=payload))
    progress = []
    path = app_updater.download(good, progress.append)
    assert open(path, "rb").read() == payload and progress[-1] == 1.0

    bad = app_updater.Release("2.2.0", "", "https://x/file", "file.bin", "f" * 64)
    with pytest.raises(app_updater.UpdateError):
        app_updater.download(bad, lambda f: None)


def test_release_without_asset_cannot_be_downloaded():
    with pytest.raises(app_updater.UpdateError):
        app_updater.download(app_updater.Release("2.2.0", "", None, None, None), lambda f: None)


def test_linux_replacement_only_targets_a_real_app_folder(monkeypatch, tmp_path):
    app_dir = tmp_path / "mod_updater"
    app_dir.mkdir()
    monkeypatch.setattr(sys, "executable", str(app_dir / "mod_updater"))
    assert app_updater._linux_app_dir() is None  # no _internal folder: refuse to touch it
    (app_dir / "_internal").mkdir()
    assert app_updater._linux_app_dir() == str(app_dir)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python3"))
    assert app_updater._linux_app_dir() is None


def test_mac_replacement_only_targets_an_app_bundle(monkeypatch, tmp_path):
    macos = tmp_path / "Minecraft Mod Updater.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(macos / "mod_updater"))
    assert app_updater._mac_app_bundle().endswith("Minecraft Mod Updater.app")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python3"))
    assert app_updater._mac_app_bundle() is None
