"""Offline tests for updater_core (Modrinth is replaced by a fake client)."""

import hashlib
import json
import os

import pytest

import updater_core as core


def version(vid, game_versions, loaders, date, files=(), project="P1", number="1.0"):
    return {"id": vid, "project_id": project, "version_number": number, "game_versions": list(game_versions),
            "loaders": list(loaders), "date_published": date, "files": list(files)}


def file_entry(name, content=b"", primary=True):
    return {"filename": name, "url": f"https://cdn.example/{name}", "primary": primary,
            "hashes": {"sha512": hashlib.sha512(content).hexdigest()}}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def test_default_config_values(fresh_config):
    config = core.load_config()
    assert config["appearance"] == "dark"
    assert config["app_auto_update"] is True
    assert config["language"] == "system"
    assert config["profiles"][0]["game_version"] == core.AUTO


def test_v1_config_is_migrated(fresh_config):
    os.makedirs(core.CONFIG_DIR, exist_ok=True)
    with open(core.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"mod_folders": {"client": "C:/mods", "server": "D:/srv/mods"}, "current_folder": "server",
                   "game_versions": ["1.21.5"], "loaders": ["fabric"], "auto_update": True,
                   "backup_mods": False, "check_interval_days": 7, "last_check": None}, f)
    config = core.load_config()
    assert [p["name"] for p in config["profiles"]] == ["client", "server"]
    assert config["profiles"][1]["path"] == "D:/srv/mods"
    assert all(p["game_version"] == core.AUTO and p["loader"] == core.AUTO for p in config["profiles"])
    assert config["current_profile"] == "server"
    assert config["backup_mods"] is False
    assert "check_interval_days" not in config


def test_corrupt_config_falls_back_to_defaults(fresh_config):
    os.makedirs(core.CONFIG_DIR, exist_ok=True)
    with open(core.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert core.load_config()["profiles"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def test_sort_loaders_puts_common_loaders_first():
    assert core.sort_loaders(["quilt", "babric", "forge", "fabric", "neoforge"]) == \
        ["fabric", "neoforge", "forge", "quilt", "babric"]


def test_quilt_also_accepts_fabric_mods():
    assert core.query_loaders("quilt") == ["quilt", "fabric"]
    assert core.query_loaders("fabric") == ["fabric"]


def test_primary_file_falls_back_to_first():
    v = {"files": [{"filename": "a.jar"}, {"filename": "b.jar"}]}
    assert core.primary_file(v)["filename"] == "a.jar"
    v["files"][1]["primary"] = True
    assert core.primary_file(v)["filename"] == "b.jar"
    assert core.primary_file({"files": []}) is None


def test_mod_files_include_disabled_jars(tmp_path):
    for name in ("a.jar", "b.jar.disabled", "notes.txt", "c.zip"):
        (tmp_path / name).write_bytes(b"x")
    names = [os.path.basename(p) for p in core.get_mod_files(str(tmp_path))]
    assert names == ["a.jar", "b.jar.disabled"]
    assert core.get_mod_files(str(tmp_path / "missing")) == []


# --------------------------------------------------------------------------- #
# Update decision (works with any versioning scheme)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("current, latest, target, expected", [
    # same version id -> up to date
    (version("A", ["26.3"], ["fabric"], "2026-01-01"), version("A", ["26.3"], ["fabric"], "2026-01-01"),
     "26.3", core.STATUS_UP_TO_DATE),
    # newer release for the same game version
    (version("A", ["26.3"], ["fabric"], "2026-01-01"), version("B", ["26.3"], ["fabric"], "2026-02-01"),
     "26.3", core.STATUS_UPDATE),
    # installed file is for an old game version -> switch even if the target build is older
    (version("A", ["1.21.4"], ["fabric"], "2026-05-01"), version("B", ["26.3"], ["fabric"], "2026-01-01"),
     "26.3", core.STATUS_UPDATE),
    # installed file already valid for the target and newer than Modrinth's pick -> keep it
    (version("A", ["26.3"], ["fabric"], "2026-05-01"), version("B", ["26.3"], ["fabric"], "2026-01-01"),
     "26.3", core.STATUS_UP_TO_DATE),
    # new year-based snapshot names are treated like any other version
    (version("A", ["26.4-snapshot-1"], ["fabric"], "2026-09-01"),
     version("B", ["26.4-snapshot-2"], ["fabric"], "2026-09-30"), "26.4-snapshot-2", core.STATUS_UPDATE),
])
def test_determine_status(current, latest, target, expected):
    mod = core.ModInfo(path="x.jar", sha512="abc", current=current, latest=latest)
    assert core.determine_status(mod, target, ["fabric"]) == expected


def test_status_without_modrinth_data():
    assert core.determine_status(core.ModInfo(path="x.jar"), "26.3", ["fabric"]) == core.STATUS_NOT_FOUND
    mod = core.ModInfo(path="x.jar", current=version("A", ["1.20"], ["forge"], "2024-01-01"))
    assert core.determine_status(mod, "26.3", ["fabric"]) == core.STATUS_NO_COMPATIBLE


def test_same_file_hash_counts_as_up_to_date():
    content = b"jar"
    mod = core.ModInfo(path="x.jar", sha512=hashlib.sha512(content).hexdigest(),
                       current=version("A", ["26.3"], ["fabric"], "2026-01-01"),
                       latest=version("B", ["26.3"], ["fabric"], "2026-02-01", [file_entry("x.jar", content)]))
    assert core.determine_status(mod, "26.3", ["fabric"]) == core.STATUS_UP_TO_DATE


def test_detect_target_picks_most_common_version_and_loader():
    versions = [
        version("1", ["1.21.4"], ["fabric", "quilt"], "x"),
        version("2", ["1.21.4", "1.21.5"], ["fabric"], "x"),
        version("3", ["1.21.4"], ["fabric"], "x"),
    ]
    assert core.detect_from_versions(versions) == {"game_version": "1.21.4", "loader": "fabric"}


def test_detect_target_tie_prefers_known_loader_order():
    versions = [version("1", ["26.3"], ["neoforge", "forge"], "x")]
    assert core.detect_from_versions(versions)["loader"] == "neoforge"


# --------------------------------------------------------------------------- #
# Scanning and updating with a fake Modrinth client
# --------------------------------------------------------------------------- #

class FakeClient:
    def __init__(self, current, latest, projects=None, payloads=None):
        self.current, self.latest = current, latest
        self._projects = projects or {}
        self.payloads = payloads or {}
        self.latest_calls = []

    def versions_from_hashes(self, hashes):
        return {h: self.current[h] for h in hashes if h in self.current}

    def latest_versions(self, hashes, loaders, game_versions, version_types):
        self.latest_calls.append((tuple(loaders), tuple(game_versions)))
        return {h: self.latest[h] for h in hashes if h in self.latest}

    def projects(self, ids):
        return {i: self._projects[i] for i in ids if i in self._projects}

    def download(self, url, destination, expected_sha512):
        with open(destination, "wb") as f:
            f.write(self.payloads[url])


def make_mods_folder(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "sodium-old.jar").write_bytes(b"sodium-old")
    (mods / "lithium-old.jar.disabled").write_bytes(b"lithium-old")
    (mods / "local.jar").write_bytes(b"not on modrinth")
    return mods


def sha(data):
    return hashlib.sha512(data).hexdigest()


def fake_modrinth():
    new_sodium, new_lithium = b"sodium-new", b"lithium-new"
    current = {
        sha(b"sodium-old"): version("S1", ["1.21.4"], ["fabric"], "2025-01-01", project="sodium"),
        sha(b"lithium-old"): version("L1", ["1.21.4"], ["fabric"], "2025-01-01", project="lithium"),
    }
    latest = {
        sha(b"sodium-old"): version("S2", ["26.3"], ["fabric"], "2026-09-01", project="sodium", number="0.9",
                                    files=[file_entry("sodium-0.9.jar", new_sodium)]),
        sha(b"lithium-old"): version("L2", ["26.3"], ["fabric"], "2026-09-01", project="lithium", number="0.26",
                                     files=[file_entry("lithium-0.26.jar", new_lithium)]),
    }
    projects = {"sodium": {"title": "Sodium", "icon_url": "https://cdn.example/sodium.png",
                           "slug": "sodium", "project_type": "mod"},
                "lithium": {"title": "Lithium", "icon_url": ""}}
    payloads = {"https://cdn.example/sodium-0.9.jar": new_sodium,
                "https://cdn.example/lithium-0.26.jar": new_lithium}
    return FakeClient(current, latest, projects, payloads)


def test_scan_auto_detects_target_and_statuses(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    result = core.scan_mods(client, str(mods_dir), core.AUTO, core.AUTO, False, lambda f, m: None)
    assert result.detected and result.game_version == "1.21.4" and result.loader == "fabric"
    by_name = {m.filename: m for m in result.mods}
    assert by_name["local.jar"].status == core.STATUS_NOT_FOUND
    assert by_name["sodium-old.jar"].title == "Sodium"
    assert by_name["sodium-old.jar"].icon_url == "https://cdn.example/sodium.png"
    assert by_name["sodium-old.jar"].page_url == "https://modrinth.com/mod/sodium"
    assert by_name["lithium-old.jar.disabled"].page_url == "https://modrinth.com/project/lithium"
    assert by_name["local.jar"].page_url == ""
    assert client.latest_calls[0] == (("fabric",), ("1.21.4",))


def test_scan_with_fixed_target_and_update(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, lambda f, m: None)
    to_update = [m for m in result.mods if m.status == core.STATUS_UPDATE]
    assert sorted(m.display_name for m in to_update) == ["Lithium", "Sodium"]

    backup = core.update_mods(client, to_update, str(mods_dir), True, lambda f, m: None)
    assert all(m.status == core.STATUS_UPDATED for m in to_update)
    assert sorted(os.listdir(mods_dir)) == ["lithium-0.26.jar.disabled", "local.jar", "sodium-0.9.jar"]
    assert sorted(os.listdir(backup)) == ["lithium-old.jar.disabled", "sodium-old.jar"]
    assert not str(backup).startswith(str(mods_dir))  # backups live outside the mods folder


def test_update_without_backup_deletes_old_files(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, lambda f, m: None)
    to_update = [m for m in result.mods if m.status == core.STATUS_UPDATE]
    assert core.update_mods(client, to_update, str(mods_dir), False, lambda f, m: None) is None
    assert "sodium-old.jar" not in os.listdir(mods_dir)


@pytest.mark.parametrize("project, project_id, expected", [
    ({"slug": "sodium", "project_type": "mod"}, "AANobbMI", "https://modrinth.com/mod/sodium"),
    ({"slug": "luckperms", "project_type": "plugin"}, "Vebnzrzj", "https://modrinth.com/plugin/luckperms"),
    ({}, "AANobbMI", "https://modrinth.com/project/AANobbMI"),
    ({}, "", ""),
])
def test_modrinth_page_url(project, project_id, expected):
    assert core.modrinth_page_url(project, project_id) == expected
