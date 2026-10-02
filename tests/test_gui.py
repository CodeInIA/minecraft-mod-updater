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
