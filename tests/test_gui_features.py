"""Window behaviour of dependencies, ignored mods, changelogs, backups, launcher import and content types."""

import pytest
from test_gui import app, window  # noqa: F401 - shared window fixtures

import launchers
import updater_core as core

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


def test_keyboard_shortcuts(app, tmp_path):
    from test_gui import fake_scan
    app._on_scan_done(fake_scan(tmp_path))
    app.update()
    assert len(app.checked) == 2
    app._run_shortcut(type("E", (), {"widget": app.tree})(), app._shortcut_select_all)
    assert app.checked == set()  # Ctrl+A toggles the selection
    app._focus_filter()
    app.search_entry.insert(0, "Mod 1")
    app._fill_tree()
    assert len(app.tree.get_children()) == 1
    app._clear_filter()
    assert len(app.tree.get_children()) == 5
    keys = [keys for keys, _text in app.shortcut_list()]
    assert "F1" in keys and all(text for _keys, text in app.shortcut_list())


def test_switching_profiles_with_the_keyboard(app, tmp_path):
    app.config_data["profiles"] = [{"name": n, "path": str(tmp_path), "game_version": core.AUTO,
                                    "loader": core.AUTO} for n in ("one", "two")]
    app.config_data["current_profile"] = "one"
    app.refresh_profiles()
    app._switch_profile(1)
    assert app.config_data["current_profile"] == "two"
    app._switch_profile(1)
    assert app.config_data["current_profile"] == "one"  # wraps around


def test_update_waits_until_the_game_is_closed(app, tmp_path, monkeypatch):
    import mod_updater
    running = [True, True, False]
    monkeypatch.setattr(core, "game_running", lambda _folder: running.pop(0))
    asked = []
    monkeypatch.setattr(mod_updater.messagebox, "askretrycancel", lambda *a, **k: asked.append(1) or True)
    assert app.confirm_game_closed(str(tmp_path)) is True
    assert len(asked) == 2  # asked again until the game was closed
    monkeypatch.setattr(core, "game_running", lambda _folder: True)
    monkeypatch.setattr(mod_updater.messagebox, "askretrycancel", lambda *a, **k: False)
    assert app.confirm_game_closed(str(tmp_path)) is False  # the user cancelled


def test_disable_a_mod_from_the_table(app, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "game_running", lambda _folder: False)
    jar = tmp_path / "sodium.jar"
    jar.write_bytes(b"x")
    mod = core.ModInfo(path=str(jar), title="Sodium", status=core.STATUS_UP_TO_DATE)
    app.mods = [mod]
    app._fill_tree()
    app.set_enabled(mod, False)
    assert (tmp_path / "sodium.jar.disabled").exists()
    assert app.tree.get_children() == (str(jar) + ".disabled",)
    assert "Disabled" in app.tree.item(str(jar) + ".disabled", "text") or mod.disabled
    app.set_enabled(mod, True)
    assert jar.exists() and not mod.disabled


def test_choose_a_version_and_pin_it(app, tmp_path, monkeypatch):
    import time

    import mod_updater
    monkeypatch.setattr(core, "game_running", lambda _folder: False)
    app.config_data["profiles"] = [{"name": "p", "path": str(tmp_path), "game_version": "26.3", "loader": "fabric",
                                    "ignored": [], "pinned": {}}]
    app.config_data["current_profile"] = "p"
    app.refresh_profiles()
    app._on_scan_done(scan_with_dependency(tmp_path))
    sodium = app.mods[0]
    older = {"id": "S0", "version_number": "0.5", "project_id": "sodium", "version_type": "beta",
             "date_published": "2026-01-01", "files": []}
    monkeypatch.setattr(core, "available_versions", lambda *a: [older])
    dialog = mod_updater.VersionPickerDialog(app, sodium)
    end = time.time() + 5
    while time.time() < end and not dialog.versions:
        app.update()
        time.sleep(0.02)
    assert list(dialog.versions) == ["S0"]

    def fake_update(client, mods, folder, backup, progress):
        mods[0].status = core.STATUS_UPDATED
        return None
    monkeypatch.setattr(core, "update_mods", fake_update)
    dialog.choice.set("S0")
    dialog._install()
    end = time.time() + 5
    while time.time() < end and app.busy:
        app.update()
        time.sleep(0.02)
    assert app.current_profile()["pinned"] == {"sodium": "S0"}
    assert sodium.status == core.STATUS_PINNED and sodium.latest is older
    app.last_scan = scan_with_dependency(tmp_path)
    app.unpin(sodium)
    assert app.current_profile()["pinned"] == {}


def test_problems_are_shown_in_the_status_column(app, tmp_path):
    from ui_common import mod_warnings, row_status
    mod = core.ModInfo(path=str(tmp_path / "a.jar"), title="A", status=core.STATUS_UP_TO_DATE,
                       other_versions=["a-old.jar"], incompatible_with=["B"])
    assert row_status(mod).count("⚠") == 2
    assert "a-old.jar" in mod_warnings(mod, detailed=True)[0] and "B" in mod_warnings(mod, detailed=True)[1]
    app.mods = [mod]
    app._update_summary()
    assert "Problems: 1" in app.summary_label.cget("text")


def test_migration_dialog_and_profile_move(app, tmp_path, monkeypatch):
    import time

    import mod_updater
    monkeypatch.setattr(core, "game_running", lambda _folder: False)
    app.config_data["profiles"] = [{"name": "p", "path": str(tmp_path), "game_version": "26.3", "loader": "fabric",
                                    "ignored": [], "pinned": {}}]
    app.config_data["current_profile"] = "p"
    app.refresh_profiles()
    ready = core.ModInfo(path=str(tmp_path / "a.jar"), title="A", status=core.STATUS_UPDATE,
                         current={"version_number": "1"}, latest={"version_number": "2"})
    missing = core.ModInfo(path=str(tmp_path / "b.jar"), title="B", status=core.STATUS_NO_COMPATIBLE)
    plan = core.MigrationPlan(target="26.4", loader="fabric", ready=[ready], missing=[missing], unknown=[],
                              dependencies=[])
    monkeypatch.setattr(core, "plan_migration", lambda *a: plan)
    dialog = mod_updater.MigrationDialog(app)
    dialog.version_var.set("26.4")
    dialog._check()
    end = time.time() + 5
    while time.time() < end and dialog.plan is None:
        app.update()
        time.sleep(0.02)
    assert "1 of 2" in dialog.summary.cget("text")
    assert dialog.migrate_btn.cget("state") == "normal"

    calls = []
    monkeypatch.setattr(core, "migrate", lambda client, p, folder, backup, disable, progress:
                        calls.append((p.target, disable)) or (None, []))
    monkeypatch.setattr(mod_updater.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(app, "check_updates", lambda: None)
    dialog._migrate()
    end = time.time() + 5
    while time.time() < end and (not calls or app.busy):
        app.update()
        time.sleep(0.02)
    assert calls == [("26.4", True)]
    assert app.current_profile()["game_version"] == "26.4"


def test_search_dialog_lists_and_installs(app, tmp_path, monkeypatch):
    import time

    import mod_updater
    from ui_common import compact_number
    assert (compact_number(235049829), compact_number(1234), compact_number(999)) == ("235M", "1.2K", "999")
    monkeypatch.setattr(core, "game_running", lambda _folder: False)
    app.config_data["profiles"] = [{"name": "p", "path": str(tmp_path), "game_version": "26.3", "loader": "fabric",
                                    "ignored": [], "pinned": {}}]
    app.config_data["current_profile"] = "p"
    app.refresh_profiles()
    hits = [{"project_id": "modmenu", "slug": "modmenu", "title": "Mod Menu", "author": "Prospector",
             "downloads": 1234, "description": "Adds a mod menu", "icon_url": "", "project_type": "mod"}]
    monkeypatch.setattr(core, "search_projects", lambda *a: hits)
    installed = core.ModInfo(path=str(tmp_path / "modmenu.jar"), title="Mod Menu", status=core.STATUS_INSTALLED,
                             latest={"project_id": "modmenu"})
    monkeypatch.setattr(core, "plan_install", lambda *a: [installed])
    monkeypatch.setattr(core, "update_mods", lambda *a: None)
    dialog = mod_updater.SearchDialog(app)

    def wait(condition):
        end = time.time() + 5
        while time.time() < end and not condition():
            app.update()
            time.sleep(0.02)
    wait(lambda: dialog.rows)
    assert list(dialog.rows) == ["modmenu"] and dialog.loaders == ["fabric"]
    dialog._install("modmenu")
    wait(lambda: not app.busy and "✔" in dialog.rows["modmenu"]["button"].cget("text"))
    assert "✔" in dialog.rows["modmenu"]["button"].cget("text")
    dialog.destroy()


def test_compare_dialog_and_export(app, tmp_path, monkeypatch):
    import time

    import mod_updater
    import modpack
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    app.config_data["profiles"] = [
        {"name": "client", "path": str(a), "game_version": "26.3", "loader": "fabric", "ignored": [], "pinned": {}},
        {"name": "server", "path": str(b), "game_version": "26.3", "loader": "fabric", "ignored": [], "pinned": {}}]
    app.config_data["current_profile"] = "client"
    app.refresh_profiles()
    monkeypatch.setattr(modpack, "compare_folders", lambda *a: [
        modpack.Difference("Sodium", modpack.ONLY_A, version_a="0.9", side="client"),
        modpack.Difference("API", modpack.DIFFERENT, "2", "1"), modpack.Difference("Lib", modpack.SAME, "1", "1")])
    dialog = mod_updater.CompareDialog(app)
    assert list(dialog.others) == ["server"]
    dialog._compare()

    def wait(condition):
        end = time.time() + 5
        while time.time() < end and not condition():
            app.update()
            time.sleep(0.02)
    wait(lambda: dialog.go_btn.cget("state") == "normal")
    texts = [w.cget("text") for w in dialog.list.winfo_children() if isinstance(w, mod_updater.ctk.CTkLabel)]
    assert any("Different versions" in x for x in texts) and any("Only in client" in x for x in texts)
    assert any("The same in both: 1" in x for x in texts)
    dialog.destroy()

    out = tmp_path / "client.mrpack"
    monkeypatch.setattr(mod_updater.filedialog, "asksaveasfilename", lambda **k: str(out))
    monkeypatch.setattr(modpack, "export_mrpack", lambda *a: {"downloads": 3, "overrides": 1})
    app.export_profile()
    wait(lambda: not app.busy)
    assert "3" in app.status_label.cget("text")
