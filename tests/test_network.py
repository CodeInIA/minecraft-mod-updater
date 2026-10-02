"""End-to-end checks against the real Modrinth and GitHub APIs."""

import os

import pytest

import app_updater
import updater_core as core

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def client():
    return core.ModrinthClient()


def test_modrinth_lists_game_versions_and_loaders(client):
    tags = core.fetch_tags(client)
    releases = [v for v in tags["game_versions"] if v["version_type"] == "release"]
    assert releases, "Modrinth returned no Minecraft releases"
    assert tags["loaders"][:2] == ["fabric", "neoforge"]


def test_old_mod_is_detected_and_updated(client, tmp_path):
    """Download an old Fabric API build for 1.21.4, then let the app detect and update it."""
    versions = client._request("GET", "/project/fabric-api/version",
                               params={"loaders": '["fabric"]', "game_versions": '["1.21.4"]'})
    oldest = versions[-1]
    file_info = core.primary_file(oldest)
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    client.download(file_info["url"], str(mods_dir / file_info["filename"]), file_info["hashes"]["sha512"])

    result = core.scan_mods(client, str(mods_dir), core.AUTO, core.AUTO, False, lambda f, m: None)
    assert (result.game_version, result.loader) == ("1.21.4", "fabric")
    mod = result.mods[0]
    assert mod.title == "Fabric API"
    assert mod.status == core.STATUS_UPDATE

    core.update_mods(client, [mod], str(mods_dir), False, lambda f, m: None)
    assert mod.status == core.STATUS_UPDATED, mod.error
    rescan = core.scan_mods(client, str(mods_dir), core.AUTO, core.AUTO, False, lambda f, m: None)
    assert rescan.mods[0].status == core.STATUS_UP_TO_DATE
    assert os.listdir(mods_dir) == [mod.filename]


def test_github_latest_release_has_all_installers():
    release = app_updater.fetch_latest()
    assert app_updater.parse_version(release.version)
    assert release.asset_url and release.sha256
