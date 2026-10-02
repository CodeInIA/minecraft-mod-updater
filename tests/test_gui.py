"""Smoke tests of the window: it must build in every language and handle a scan result."""

import pytest

pytestmark = pytest.mark.gui

import i18n  # noqa: E402
import updater_core as core  # noqa: E402


@pytest.fixture
def app(fresh_config):
    tk = pytest.importorskip("tkinter")
    try:
        tk.Tk().destroy()
    except tk.TclError:
        pytest.skip("no display available")
    import mod_updater
    window = mod_updater.App(offline=True)
    window.update()
    yield window
    window.destroy()
    i18n.set_language("en")


def fake_scan(tmp_path):
    mods = []
    for i, status in enumerate([core.STATUS_UPDATE, core.STATUS_UPDATE, core.STATUS_UP_TO_DATE,
                                core.STATUS_NOT_FOUND, core.STATUS_NO_COMPATIBLE]):
        mods.append(core.ModInfo(path=str(tmp_path / f"mod{i}.jar"), title=f"Mod {i}", status=status,
                                 current={"version_number": "1.0"}, latest={"version_number": "2.0"}))
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
