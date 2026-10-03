"""Modrinth modpacks (.mrpack): export, import and safety; comparing two profiles."""

import json
import os
import zipfile

import pytest
from test_core import FakeClient, file_entry, sha, version

import modpack


def modrinth_with_sodium():
    sodium = version("S1", ["26.3"], ["fabric"], "2026-09-01", project="sodium", number="0.9",
                     files=[file_entry("sodium-0.9.jar", b"sodium")])
    sodium["files"][0]["url"] = "https://cdn.modrinth.com/data/sodium-0.9.jar"
    return FakeClient({sha(b"sodium"): sodium}, {},
                      {"sodium": {"title": "Sodium", "client_side": "required", "server_side": "unsupported"}},
                      {"https://cdn.modrinth.com/data/sodium-0.9.jar": b"sodium"})


def test_export_and_import_a_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(modpack, "loader_version", lambda loader, game: "0.19.5")
    folder = tmp_path / "mods"
    folder.mkdir()
    (folder / "sodium-0.9.jar").write_bytes(b"sodium")
    (folder / "private.jar").write_bytes(b"mine")
    (folder / "off.jar.disabled").write_bytes(b"off")
    client = modrinth_with_sodium()
    out = tmp_path / "pack.mrpack"
    assert modpack.export_mrpack(client, str(folder), "mods", "26.3", "fabric", "My pack", str(out)) == \
        {"downloads": 1, "overrides": 1}
    with zipfile.ZipFile(out) as z:
        index = json.loads(z.read("modrinth.index.json"))
        assert z.namelist() == ["modrinth.index.json", "overrides/mods/private.jar"]
    assert index["dependencies"] == {"minecraft": "26.3", "fabric-loader": "0.19.5"}
    entry = index["files"][0]
    assert entry["path"] == "mods/sodium-0.9.jar" and entry["env"] == {"client": "required", "server": "unsupported"}
    assert set(entry["hashes"]) == {"sha1", "sha512"}

    pack = modpack.read_mrpack(str(out))
    assert (pack.name, pack.game_version, pack.loader, pack.loader_version) == ("My pack", "26.3", "fabric", "0.19.5")
    game = tmp_path / "instance"
    modpack.install_mrpack(client, pack, str(game), lambda f, m: None)
    assert sorted(os.listdir(game / "mods")) == ["private.jar", "sodium-0.9.jar"]
    assert modpack.compare_folders(client, str(folder), str(game / "mods"))[0].kind == modpack.SAME


def write_pack(path, files, overrides=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("modrinth.index.json", json.dumps({"formatVersion": 1, "game": "minecraft", "name": "x",
                                                      "files": files, "dependencies": {"minecraft": "26.3"}}))
        for name, data in (overrides or {}).items():
            z.writestr(name, data)
    return str(path)


def install(path, game):
    modpack.install_mrpack(FakeClient({}, {}), modpack.read_mrpack(path), str(game), lambda f, m: None)


@pytest.mark.parametrize("bad", ["../evil.jar", "/etc/evil", "C:/Windows/evil.dll", "mods/../../evil.jar"])
def test_unsafe_paths_are_refused(tmp_path, bad):
    path = write_pack(tmp_path / "bad.mrpack", [{"path": bad, "downloads": ["https://cdn.modrinth.com/x"],
                                                 "hashes": {}}])
    with pytest.raises(modpack.ModpackError):
        install(path, tmp_path / "game")
    assert not (tmp_path / "evil.jar").exists()


def test_unsafe_overrides_and_hosts_are_refused(tmp_path):
    path = write_pack(tmp_path / "o.mrpack", [], {"overrides/../evil.txt": "x"})
    with pytest.raises(modpack.ModpackError):
        install(path, tmp_path / "game")
    assert not (tmp_path / "evil.txt").exists()
    path = write_pack(tmp_path / "h.mrpack", [{"path": "mods/a.jar", "downloads": ["https://evil.example/a.jar"],
                                               "hashes": {}}])
    with pytest.raises(modpack.ModpackError):
        install(path, tmp_path / "game")


def test_server_only_files_are_skipped_and_invalid_packs_reported(tmp_path):
    path = write_pack(tmp_path / "s.mrpack", [{"path": "mods/server.jar", "env": {"client": "unsupported"},
                                               "downloads": ["https://cdn.modrinth.com/s.jar"], "hashes": {}}])
    install(path, tmp_path / "game")
    assert not (tmp_path / "game" / "mods").exists()
    (tmp_path / "broken.mrpack").write_bytes(b"not a zip")
    with pytest.raises(modpack.ModpackError):
        modpack.read_mrpack(str(tmp_path / "broken.mrpack"))


def test_compare_client_and_server(tmp_path):
    client_dir, server_dir = tmp_path / "client", tmp_path / "server"
    client_dir.mkdir()
    server_dir.mkdir()
    (client_dir / "sodium.jar").write_bytes(b"sodium")
    (client_dir / "api-2.jar").write_bytes(b"api-2")
    (server_dir / "api-1.jar").write_bytes(b"api-1")
    (server_dir / "plugin.jar").write_bytes(b"plugin")
    client = FakeClient({sha(b"sodium"): version("S", [], [], "", project="sodium", number="0.9"),
                         sha(b"api-2"): version("A2", [], [], "", project="api", number="2"),
                         sha(b"api-1"): version("A1", [], [], "", project="api", number="1")}, {},
                        {"sodium": {"title": "Sodium", "server_side": "unsupported"}, "api": {"title": "API"}})
    diffs = {d.name: d for d in modpack.compare_folders(client, str(client_dir), str(server_dir))}
    assert diffs["API"].kind == modpack.DIFFERENT and (diffs["API"].version_a, diffs["API"].version_b) == ("2", "1")
    assert diffs["Sodium"].kind == modpack.ONLY_A and diffs["Sodium"].side == "client"
    assert diffs["plugin.jar"].kind == modpack.ONLY_B
