"""Identifying jars Modrinth does not know by hash, from the metadata inside them, and icons from jars."""

import io
import json
import zipfile

from PIL import Image
from test_core import FakeClient, file_entry, version

import updater_core as core

NO_PROGRESS = lambda f, m: None  # noqa: E731


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (16, 16), (200, 50, 50, 255)).save(out, "PNG")
    return out.getvalue()


def make_jar(path, files):
    with zipfile.ZipFile(path, "w") as jar:
        for name, data in files.items():
            jar.writestr(name, data)
    return path


def fabric_jar(path, mod_id, name, number, icon=None):
    meta = {"schemaVersion": 1, "id": mod_id, "name": name, "version": number}
    files = {}
    if icon:
        meta["icon"] = f"assets/{mod_id}/icon.png"
        files[meta["icon"]] = icon
    files["fabric.mod.json"] = json.dumps(meta)
    return make_jar(path, files)


def jade_modrinth():
    """Jade on Modrinth: 26.3.3 and 26.3.5, but not the 26.3.4 that is installed."""
    client = FakeClient({}, {}, {"jade": {"id": "nvQzSEkH", "slug": "jade", "title": "Jade 🔍",
                                          "icon_url": "https://cdn.example/jade.png", "project_type": "mod"}})
    client.all_versions = [
        version("J3", ["26.3"], ["fabric"], "2026-09-29T00:00:00Z", project="nvQzSEkH", number="26.3.3+fabric",
                files=[file_entry("Jade-26.3.3.jar", b"j3")]),
        version("J5", ["26.3"], ["fabric"], "2026-10-02T00:00:00Z", project="nvQzSEkH", number="26.3.5+fabric",
                files=[file_entry("Jade-26.3.5.jar", b"j5")]),
    ]
    for v in client.all_versions:
        v["version_type"] = "release"
    return client


def test_reads_fabric_forge_and_quilt_metadata(tmp_path):
    fabric = read = core.read_jar_metadata(str(fabric_jar(tmp_path / "a.jar", "jade", "Jade", "26.3.4+fabric", png())))
    assert (fabric["id"], fabric["name"], fabric["version"], fabric["icon"]) == \
        ("jade", "Jade", "26.3.4+fabric", "assets/jade/icon.png")
    forge = core.read_jar_metadata(str(make_jar(tmp_path / "b.jar", {
        "META-INF/neoforge.mods.toml": 'modLoader="javafml"\nlogoFile="logo.png"\n[[mods]]\nmodId="jei"\n'
                                       'version="${file.jarVersion}"\ndisplayName="Just Enough Items"\n',
        "META-INF/MANIFEST.MF": "Manifest-Version: 1.0\nImplementation-Version: 19.0.1\n",
        "logo.png": png()})))
    assert (forge["id"], forge["name"], forge["version"], forge["icon"]) == \
        ("jei", "Just Enough Items", "19.0.1", "logo.png")
    quilt = core.read_jar_metadata(str(make_jar(tmp_path / "c.jar", {"quilt.mod.json": json.dumps(
        {"quilt_loader": {"id": "qsl", "version": "1.0", "metadata": {"name": "QSL"}}})})))
    assert (quilt["id"], quilt["name"], quilt["version"]) == ("qsl", "QSL", "1.0")
    assert core.read_jar_metadata(str(tmp_path / "missing.jar"))["id"] == ""
    assert read["icon"]  # icons that exist in the jar are kept


def test_jar_not_on_modrinth_is_found_by_its_mod_id(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    fabric_jar(mods / "Jade-mc26.3-Fabric-26.3.4.jar", "jade", "Jade", "26.3.4+fabric")
    result = core.scan_mods(jade_modrinth(), str(mods), "26.3", "fabric", False, NO_PROGRESS)
    jade = result.mods[0]
    assert jade.display_name == "Jade 🔍" and jade.page_url == "https://modrinth.com/mod/jade"
    assert (jade.current_version, jade.latest_version, jade.status) == \
        ("26.3.4+fabric", "26.3.5+fabric", core.STATUS_UPDATE)
    assert jade.actionable
    # changelogs start after the newest Modrinth version that is not newer than the file
    assert jade.current["date_published"] == "2026-09-29T00:00:00Z"


def test_jar_newer_than_modrinth_is_up_to_date(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    fabric_jar(mods / "Jade-26.3.6.jar", "jade", "Jade", "26.3.6+fabric")
    jade = core.scan_mods(jade_modrinth(), str(mods), "26.3", "fabric", False, NO_PROGRESS).mods[0]
    assert jade.status == core.STATUS_UP_TO_DATE


def test_mod_id_of_an_unrelated_project_is_not_trusted(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    fabric_jar(mods / "tweaks.jar", "tweaks", "My Private Tweaks", "1.0")
    client = jade_modrinth()
    client._projects["tweaks"] = {"id": "T1", "slug": "tweaks", "title": "Tweaks Plus"}
    mod = core.scan_mods(client, str(mods), "26.3", "fabric", False, NO_PROGRESS).mods[0]
    assert mod.status == core.STATUS_NOT_FOUND and mod.display_name == "tweaks.jar"


def test_first_listing_finds_jars_by_mod_id_and_uses_jar_icons(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    fabric_jar(mods / "Jade-26.3.4.jar", "jade", "Jade", "26.3.4+fabric")
    fabric_jar(mods / "local.jar", "secret", "Secret", "1.0", icon=png())
    listed = {m.filename: m for m in core.identify_local_mods(jade_modrinth(), core.list_local_mods(str(mods)))}
    assert listed["Jade-26.3.4.jar"].display_name == "Jade 🔍"
    assert listed["Jade-26.3.4.jar"].current_version == "26.3.4+fabric"
    assert listed["local.jar"].icon_url.startswith(core.JAR_ICON_PREFIX)
    assert {m.status for m in listed.values()} == {core.STATUS_UNCHECKED}


def test_jar_icons_are_loaded_from_inside_the_jar(tmp_path):
    import mod_icons
    jar = fabric_jar(tmp_path / "a.jar", "a", "A", "1.0", icon=png())
    url = core.jar_icon_url(str(jar))
    cache = mod_icons.IconCache()
    assert cache.missing([url]) == [url]
    cache.download([url])
    assert cache.get(url) is not None
