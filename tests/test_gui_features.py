"""Window behaviour of dependencies, ignored mods, changelogs, backups, launcher import and content types."""

import pytest

import launchers
import updater_core as core
from test_gui import app, window  # noqa: F401 - shared window fixtures

pytestmark = pytest.mark.gui


def scan_with_dependency(tmp_path):
    mods = [
        core.ModInfo(path=str(tmp_path / "sodium.jar"), title="Sodium", status=core.STATUS_UPDATE,
                     current={"id": "S1", "version_number": "0.6", "project_id": "sodium",
                              "date_published": "2025-01-01"},
                     latest={"id": "S2", "version_number": "0.9", "project_id": "sodium", "date_published": "2026-09-01",
                             "game_versions": ["26.3"], "loaders": ["fabric"]},
                     side_warning=core.SIDE_CLIENT_ONLY),
        core.ModInfo(path=str(tmp_path / "fabric-api.jar"), title="Fabric API", status=core.STATUS_MISSING_DEP,
                     latest={"version_number": "0.161", "project_id": "fabric-api"}, required_by=["Mod Menu"]),
    ]
    return core.ScanResult(mods=mods, game_version="26.3", loader="fabric", loaders=["fabric"])


def test_missing_dependency_row(app, tmp_path):
    app._on_scan_done(scan_with_dependency(tmp_path))
    app.update()
    dep_row = str(tmp_path / "fabric-api.jar")
    assert dep_row in app.checked  # offered and pre-selected
    installed, available, status = app.tree.item(dep_row, "values")
    assert "Mod Menu" in installed and available == "0.161"
    sodium_status = app.tree.item(str(tmp_path / "sodium.jar"), "values")[2]
    assert "⚠" in sodium_status  # client/server warning shown next to the status
    assert "(2)" in app.update_btn.cget("text")


def test_ignore_and_unignore_a_mod(app, tmp_path):
    app._on_scan_done(scan_with_dependency(tmp_path))
    sodium = next(m for m in app.mods if m.title == "Sodium")
    app.set_ignored(sodium, True)
    assert sodium.status == core.STATUS_IGNORED and sodium.path not in app.checked
    assert "sodium" in core.load_config()["profiles"][0]["ignored"]
    app.set_ignored(sodium, False)
    assert sodium.status == core.STATUS_UPDATE and sodium.path in app.checked
    assert core.load_config()["profiles"][0]["ignored"] == []


def test_changelog_dialog(app, tmp_path, monkeypatch):
    import mod_updater
    monkeypatch.setattr(core, "changelog_entries", lambda *a: [
        {"version": "0.9", "date": "2026-09-01", "type": "release", "changelog": "Fixed [#1](https://x) crash"}])
    app._on_scan_done(scan_with_dependency(tmp_path))
    import time
    dialog = mod_updater.ChangelogDialog(app, app.mods[0], "26.3", ["fabric"])
    end = time.time() + 5  # the changelog is loaded in the background and picked up every 50 ms
    while time.time() < end and "Fixed" not in dialog.text.get("1.0", "end"):
        app.update()
        time.sleep(0.02)
    text = dialog.text.get("1.0", "end")
    assert "0.9" in text and "Fixed #1 crash" in text  # markdown links shown as plain text
    dialog.destroy()


def test_backups_and_import_dialogs(app, tmp_path, monkeypatch):
    import mod_updater
    instance = launchers.Instance("Prism Launcher", "Pack 26.3", str(tmp_path / "pack" / "mods"), 12)
    monkeypatch.setattr(launchers, "find_instances", lambda: [instance])
    backups = mod_updater.BackupsDialog(app)
    backups.update()
    backups.destroy()
    dialog = mod_updater.ImportDialog(app)
    dialog.update()
    assert "(1)" in dialog.import_btn.cget("text")
    dialog._import()
    assert dialog.result == [instance]


def test_import_creates_profiles(app, tmp_path, monkeypatch):
    import mod_updater
    instances = [launchers.Instance("Prism Launcher", "client", str(tmp_path / "a"), 3),
                 launchers.Instance("CurseForge", "A very long modpack name that goes on and on", str(tmp_path / "b"), 5)]

    class FakeImport:
        def __init__(self, _app):
            self.result = instances

    monkeypatch.setattr(mod_updater, "ImportDialog", FakeImport)
    monkeypatch.setattr(app, "wait_window", lambda _d: None)
    before = len(app.config_data["profiles"])
    app.import_profiles()
    added = app.config_data["profiles"][before:]
    assert [p["path"] for p in added] == [str(tmp_path / "a"), str(tmp_path / "b")]
    assert added[0]["name"] != "client"  # renamed: "client" already exists
    assert all(len(p["name"]) <= core.MAX_PROFILE_NAME for p in added)
    assert len({p["color"] for p in app.config_data["profiles"]}) == len(app.config_data["profiles"])


def test_resource_pack_profile_has_no_loader(app):
    profile = app.current_profile()
    profile["content"] = "resourcepacks"
    app.refresh_profiles()
    assert app.loader_menu.cget("state") == "disabled" and app.loader_var.get() == "—"
    profile["content"] = core.CONTENT_MODS
    app.refresh_profiles()
    assert app.loader_menu.cget("state") == "normal"


def test_selecting_a_profile_lists_its_files(app, tmp_path):
    import time
    folder = tmp_path / "pack-mods"
    folder.mkdir()
    for name in ("a.jar", "b.jar.disabled", "readme.txt"):
        (folder / name).write_bytes(name.encode())
    app.config_data["profiles"].append({"name": "listing", "path": str(folder), "game_version": core.AUTO,
                                       "loader": core.AUTO, "color": core.PROFILE_COLORS[3],
                                       "content": core.CONTENT_MODS, "server": False, "ignored": []})
    app.select_profile("listing")
    end = time.time() + 5
    while time.time() < end and len(app.tree.get_children()) < 2:
        app.update()
        time.sleep(0.02)
    rows = [app.tree.item(i, "text").strip() for i in app.tree.get_children()]
    assert rows == ["a.jar", "b.jar.disabled  " + __import__("i18n").t("disabled_suffix")]
    assert not app.checked and app.update_btn.cget("state") == "disabled"  # nothing to update before a check
