import os

import launchers


def make_instance(root, folder, minecraft_dir, mods=("a.jar", "b.jar.disabled", "notes.txt"), cfg_name=None):
    base = root / folder
    mods_dir = base / minecraft_dir / "mods" if minecraft_dir else base / "mods"
    mods_dir.mkdir(parents=True)
    for m in mods:
        (mods_dir / m).write_bytes(b"x")
    if cfg_name:
        (base / "instance.cfg").write_text(f"InstanceType=OneSix\nname={cfg_name}\n", encoding="utf-8")
    return mods_dir


def test_finds_instances_of_each_launcher(tmp_path):
    prism = tmp_path / "prism"
    modrinth = tmp_path / "modrinth"
    curse = tmp_path / "curse"
    prism_mods = make_instance(prism, "1.21.4-fabric", ".minecraft", cfg_name="Mi modpack 1.21")
    modrinth_mods = make_instance(modrinth, "Survival 26.3", None)
    make_instance(curse, "Empty pack", None, mods=())
    (prism / "not-an-instance").mkdir()
    found = launchers.find_instances({"Prism Launcher": [str(prism)], "Modrinth App": [str(modrinth)],
                                      "CurseForge": [str(curse)], "MultiMC": [str(tmp_path / "missing")]})
    summary = [(i.launcher, i.name, i.mods_path, i.mod_count) for i in found]
    assert summary == [
        ("Prism Launcher", "Mi modpack 1.21", str(prism_mods), 2),
        ("Modrinth App", "Survival 26.3", str(modrinth_mods), 2),
        ("CurseForge", "Empty pack", str(curse / "Empty pack" / "mods"), 0),
    ]


def test_same_folder_is_reported_once(tmp_path):
    root = tmp_path / "profiles"
    make_instance(root, "pack", None)
    found = launchers.find_instances({"Modrinth App": [str(root), str(root)]})
    assert len(found) == 1


def test_known_locations_exist_for_this_system():
    roots = launchers._launcher_roots()
    assert {"Prism Launcher", "Modrinth App", "CurseForge"} <= set(roots)
    assert all(os.path.isabs(p) for paths in roots.values() for p in paths)
