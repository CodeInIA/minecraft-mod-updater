"""Smoke tests of the window: it must build in every language and handle a scan result.

A single window is shared by all tests: creating a new Tk interpreter after
destroying one can crash Tk on macOS, and the real app only ever creates one.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.gui

import i18n  # noqa: E402
import updater_core as core  # noqa: E402


@pytest.fixture(scope="module")
def window():
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("no display available")
    if os.path.exists(core.CONFIG_FILE):
        os.remove(core.CONFIG_FILE)
    import mod_updater
    app = mod_updater.App(offline=True)
    app.update()
    yield app
    app.destroy()
    i18n.set_language("en")


@pytest.fixture
def app(window):
    window.config_data["language"] = "en"
    window.rebuild_ui()
    window._clear_results()
    window.update()
    return window


def fake_scan(tmp_path):
    mods = []
    for i, status in enumerate([core.STATUS_UPDATE, core.STATUS_UPDATE, core.STATUS_UP_TO_DATE,
                                core.STATUS_NOT_FOUND, core.STATUS_NO_COMPATIBLE]):
        mods.append(core.ModInfo(path=str(tmp_path / f"mod{i}.jar"), title=f"Mod {i}", status=status,
                                 current={"version_number": "1.0"}, latest={"version_number": "2.0"},
                                 page_url=f"https://modrinth.com/mod/mod{i}"))
    return core.ScanResult(mods=mods, game_version="26.3", loader="fabric", detected=True)


def test_window_builds_and_shows_results(app, tmp_path):
    app._on_scan_done(fake_scan(tmp_path))
    app.update()
    assert len(app.tree.get_children()) == 5
    assert len(app.checked) == 2  # updatable mods are pre-selected
    assert app.select_all_var.get() is True
    assert "(2)" in app.update_btn.cget("text")


def test_select_all_toggles(app, tmp_path):
    app._on_scan_done(fake_scan(tmp_path))
    app.select_all_box.toggle()
    assert not app.checked
    app.select_all_box.toggle()
    assert len(app.checked) == 2


@pytest.mark.parametrize("lang", sorted(i18n.LANGUAGES))
def test_every_language_renders(app, tmp_path, lang):
    app._on_scan_done(fake_scan(tmp_path))
    app.config_data["language"] = lang
    app.rebuild_ui()
    app.update()
    assert i18n.current_language() == lang
    assert len(app.tree.get_children()) == 5  # results survive the rebuild
    assert app.tree.heading("#0", "text") == i18n.STRINGS[lang]["col_mod"]


def test_dialogs_open(app):
    import mod_updater
    for dialog in (mod_updater.SettingsDialog(app), mod_updater.ProfileDialog(app),
                   mod_updater.ProfileDialog(app, app.current_profile())):
        dialog.update()
        dialog.destroy()


def test_click_on_name_opens_modrinth_and_checkbox_toggles(app, tmp_path, monkeypatch):
    import mod_icons
    import mod_updater
    opened = []
    monkeypatch.setattr(mod_updater.webbrowser, "open", opened.append)
    app._on_scan_done(fake_scan(tmp_path))
    app.update()
    first = app.tree.get_children()[0]
    mod = next(m for m in app.mods if m.path == first)
    x0, y0, _w, h = app.tree.bbox(first, "#0")
    y = y0 + h // 2
    checkbox_x = x0 + mod_updater.TREE_ITEM_PADDING + mod_icons.BOX // 2
    name_x = x0 + mod_updater.TREE_ITEM_PADDING + mod_icons.BOX + mod_icons.GAP + mod_icons.ICON + 15

    was_checked = mod.path in app.checked
    app.tree.event_generate("<Button-1>", x=checkbox_x, y=y)
    assert (mod.path in app.checked) != was_checked and not opened

    app.tree.event_generate("<Button-1>", x=name_x, y=y)
    assert opened == [mod.page_url]
    assert (mod.path in app.checked) != was_checked  # opening the link does not toggle the row


def test_profiles_can_be_reordered(app):
    app.config_data["profiles"] = [{"name": n, "path": "x", "game_version": core.AUTO, "loader": core.AUTO,
                                    "color": c} for n, c in zip("abc", core.PROFILE_COLORS)]
    app.config_data["current_profile"] = "a"
    app.refresh_profiles()
    app.move_profile(0, 2)
    assert [p["name"] for p in app.config_data["profiles"]] == ["b", "c", "a"]
    assert [r.profile_name for r in app.profile_rows] == ["b", "c", "a"]
    assert [p["name"] for p in core.load_config()["profiles"]] == ["b", "c", "a"]  # saved


def test_profile_dialog_returns_color(app):
    import mod_updater
    dialog = mod_updater.ProfileDialog(app, app.current_profile())
    dialog._set_color("#123456")
    dialog._save()
    assert dialog.result["color"] == "#123456"


def test_profile_name_is_limited(app):
    import mod_updater
    dialog = mod_updater.ProfileDialog(app)
    dialog.name_var.set("x" * (core.MAX_PROFILE_NAME + 10))
    assert len(dialog.name_var.get()) == core.MAX_PROFILE_NAME
    dialog.destroy()


def test_sidebar_width_follows_longest_name(app):
    import mod_updater
    base = {"path": "x", "game_version": core.AUTO, "loader": core.AUTO, "color": core.PROFILE_COLORS[0]}
    app.config_data["profiles"] = [dict(base, name="a"), dict(base, name="b")]
    app.config_data["current_profile"] = "a"
    app.refresh_profiles()
    assert app.sidebar.cget("width") == mod_updater.SIDEBAR_MIN_WIDTH
    app.config_data["profiles"].append(dict(base, name="ScriptKiddies-server-mods-26.3"))
    app.refresh_profiles()
    assert mod_updater.SIDEBAR_MIN_WIDTH < app.sidebar.cget("width") <= mod_updater.SIDEBAR_MAX_WIDTH
    app.config_data["profiles"].append(dict(base, name="W" * 40))
    app.refresh_profiles()
    assert app.sidebar.cget("width") <= mod_updater.SIDEBAR_MAX_WIDTH


def test_dragging_a_profile_reorders_and_animates_into_place(app):
    import time
    import mod_updater
    base = {"path": "x", "game_version": core.AUTO, "loader": core.AUTO, "color": core.PROFILE_COLORS[0]}
    app.config_data["profiles"] = [dict(base, name=n) for n in ("a", "b", "c", "d")]
    app.config_data["current_profile"] = "a"
    app.refresh_profiles()
    app.update()
    row = app.profile_rows[0]
    label = [w for w in row.winfo_children() if isinstance(w, mod_updater.ctk.CTkLabel)][0]._label
    rx, ry = label.winfo_rootx() + 5, label.winfo_rooty()
    distance = int(mod_updater.PROFILE_SLOT * 2.2)  # a bit more than two rows down
    label.event_generate("<ButtonPress-1>", x=5, y=5, rootx=rx, rooty=ry + 5)
    for dy in range(5, distance, 7):
        label.event_generate("<B1-Motion>", x=5, y=dy, rootx=rx, rooty=ry + dy)
        app.update()
    label.event_generate("<ButtonRelease-1>", x=5, y=distance, rootx=rx, rooty=ry + distance)
    end = time.time() + 2
    while time.time() < end and app._anim_job is not None:
        app.update()
    assert [p["name"] for p in core.load_config()["profiles"]] == ["b", "c", "a", "d"]
    assert [r.slot_y for r in app.profile_rows] == [i * mod_updater.PROFILE_SLOT for i in range(4)]
    assert app.config_data["current_profile"] == "a"  # dragging does not select
