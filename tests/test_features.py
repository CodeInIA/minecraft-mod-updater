"""Dependencies, ignored mods, client/server side, changelogs, backups, content types and the hash cache."""

import json
import os

from test_core import FakeClient, fake_modrinth, file_entry, make_mods_folder, sha, version

import updater_core as core

NO_PROGRESS = lambda f, m: None  # noqa: E731


def dependency_setup(tmp_path):
    """Sodium's update requires 'fabric-api', which is not installed."""
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    client.latest[sha(b"sodium-old")]["dependencies"] = [
        {"project_id": "fabric-api", "dependency_type": "required"},
        {"project_id": "modmenu", "dependency_type": "optional"},
    ]
    api_payload = b"fabric-api-jar"
    client.all_versions = [
        version("API1", ["26.3"], ["fabric"], "2026-08-01", project="fabric-api", number="0.160",
                files=[file_entry("fabric-api-0.160.jar", b"older")]),
        version("API2", ["26.3"], ["fabric"], "2026-09-01", project="fabric-api", number="0.161",
                files=[file_entry("fabric-api-0.161.jar", api_payload)]),
    ]
    for v in client.all_versions:
        v["version_type"] = "release"
    client._projects["fabric-api"] = {"title": "Fabric API", "slug": "fabric-api", "project_type": "mod"}
    client.payloads["https://cdn.example/fabric-api-0.161.jar"] = api_payload
    return mods_dir, client


def test_missing_required_dependency_is_offered(tmp_path):
    mods_dir, client = dependency_setup(tmp_path)
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    deps = [m for m in result.mods if m.status == core.STATUS_MISSING_DEP]
    assert [d.display_name for d in deps] == ["Fabric API"]
    dep = deps[0]
    assert dep.latest_version == "0.161" and dep.required_by == ["Sodium"] and dep.actionable
    assert result.mods[0] is dep  # missing dependencies are listed first
    assert dep.page_url == "https://modrinth.com/mod/fabric-api"


def test_dependency_already_installed_is_not_offered(tmp_path):
    mods_dir, client = dependency_setup(tmp_path)
    client.latest[sha(b"sodium-old")]["dependencies"] = [{"project_id": "lithium", "dependency_type": "required"}]
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    assert not [m for m in result.mods if m.status == core.STATUS_MISSING_DEP]


def test_installing_a_dependency_and_undoing_it(tmp_path):
    mods_dir, client = dependency_setup(tmp_path)
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    todo = [m for m in result.mods if m.actionable]
    backup_dir = core.update_mods(client, todo, str(mods_dir), True, NO_PROGRESS)
    assert sorted(os.listdir(mods_dir)) == ["fabric-api-0.161.jar", "lithium-0.26.jar.disabled",
                                            "local.jar", "sodium-0.9.jar"]
    assert {m.display_name: m.status for m in todo}["Fabric API"] == core.STATUS_INSTALLED

    backups = core.list_backups(str(mods_dir))
    assert [b.path for b in backups] == [backup_dir]
    assert core.restore_backup(backups[0]) == []
    assert sorted(os.listdir(mods_dir)) == ["lithium-old.jar.disabled", "local.jar", "sodium-old.jar"]
    assert not os.path.exists(backup_dir) and core.list_backups(str(mods_dir)) == []


def test_backups_of_other_folders_are_not_listed(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    core.update_mods(client, [m for m in result.mods if m.actionable], str(mods_dir), True, NO_PROGRESS)
    other = tmp_path / "resourcepacks"
    other.mkdir()
    assert core.list_backups(str(other)) == [] and len(core.list_backups(str(mods_dir))) == 1


def test_no_backup_folder_left_when_nothing_was_updated(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    assert core.update_mods(fake_modrinth(), [], str(mods_dir), True, NO_PROGRESS) is None
    assert not os.path.exists(core.backup_root(str(mods_dir)))


def test_ignored_mods_are_not_offered(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    result = core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS,
                            ignored=["sodium"])
    by_name = {m.display_name: m for m in result.mods}
    assert by_name["Sodium"].status == core.STATUS_IGNORED and not by_name["Sodium"].actionable
    assert by_name["Lithium"].status == core.STATUS_UPDATE


def test_side_warnings_for_client_and_server_profiles(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    client._projects["sodium"].update(client_side="required", server_side="unsupported")
    client._projects["lithium"].update(client_side="unsupported", server_side="required")
    as_server = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS, server=True)
    as_client = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS, server=False)
    warnings = lambda r: {m.display_name: m.side_warning for m in r.mods if m.side_warning}  # noqa: E731
    assert warnings(as_server) == {"Sodium": core.SIDE_CLIENT_ONLY}
    assert warnings(as_client) == {"Lithium": core.SIDE_SERVER_ONLY}


def test_changelog_lists_versions_between_installed_and_available():
    client = FakeClient({}, {})
    installed = version("V1", ["26.3"], ["fabric"], "2026-01-01", project="p", number="1.0")
    middle = version("V2", ["26.3"], ["fabric"], "2026-02-01", project="p", number="1.1")
    newest = version("V3", ["26.3"], ["fabric"], "2026-03-01", project="p", number="1.2")
    future = version("V4", ["26.3"], ["fabric"], "2026-04-01", project="p", number="1.3")
    for v, text in ((middle, "fix A"), (newest, "fix B"), (future, "beta stuff")):
        v["changelog"] = text
    client.all_versions = [installed, middle, newest, future]
    mod = core.ModInfo(path="x.jar", current=installed, latest=newest)
    entries = core.changelog_entries(client, mod, "26.3", ["fabric"])
    assert [(e["version"], e["changelog"]) for e in entries] == [("1.2", "fix B"), ("1.1", "fix A")]


def test_resource_packs_use_zip_files_and_fixed_loader(tmp_path):
    packs = tmp_path / "resourcepacks"
    packs.mkdir()
    (packs / "faithful.zip").write_bytes(b"faithful-old")
    (packs / "some-mod.jar").write_bytes(b"not a resource pack")
    pack_old = version("R1", ["1.21.4"], ["minecraft"], "2025-01-01", project="faithful")
    pack_new = version("R2", ["26.3"], ["minecraft"], "2026-09-01", project="faithful",
                       files=[file_entry("faithful-26.3.zip", b"faithful-new")])
    client = FakeClient({sha(b"faithful-old"): pack_old}, {sha(b"faithful-old"): pack_new},
                        {"faithful": {"title": "Faithful"}})
    result = core.scan_mods(client, str(packs), core.AUTO, core.AUTO, False, NO_PROGRESS, content="resourcepacks")
    assert [m.filename for m in result.mods] == ["faithful.zip"]
    assert result.game_version == "1.21.4" and result.loaders == ["minecraft"]
    assert client.latest_calls[0][0] == ("minecraft",)


def test_unchanged_files_are_not_hashed_again(tmp_path, monkeypatch):
    mods_dir = make_mods_folder(tmp_path)
    core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    calls = []
    real = core.calculate_hash
    monkeypatch.setattr(core, "calculate_hash", lambda p: calls.append(p) or real(p))
    core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    assert calls == []  # every hash came from the cache
    (mods_dir / "sodium-old.jar").write_bytes(b"changed content, different size")
    core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    assert [os.path.basename(c) for c in calls] == ["sodium-old.jar"]


def test_profiles_get_new_defaults(fresh_config):
    os.makedirs(core.CONFIG_DIR, exist_ok=True)
    with open(core.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"profiles": [{"name": "client", "path": "a"}, {"name": "ScriptKiddies server", "path": "b"}],
                   "current_profile": "client"}, f)
    profiles = core.load_config()["profiles"]
    assert [p["content"] for p in profiles] == ["mods", "mods"]
    assert [p["server"] for p in profiles] == [False, True]
    assert [p["ignored"] for p in profiles] == [[], []]


def test_local_listing_before_and_after_a_check(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    before = core.list_local_mods(str(mods_dir))
    assert [m.filename for m in before] == ["lithium-old.jar.disabled", "local.jar", "sodium-old.jar"]
    assert {m.status for m in before} == {core.STATUS_UNCHECKED} and not any(m.actionable for m in before)

    core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    after = {m.filename: m for m in core.list_local_mods(str(mods_dir))}
    assert after["sodium-old.jar"].display_name == "Sodium"  # remembered from the check, no network needed
    assert after["sodium-old.jar"].current_version == "1.0"
    assert after["local.jar"].display_name == "local.jar"
    assert {m.status for m in after.values()} == {core.STATUS_UNCHECKED}


def test_first_listing_identifies_files_without_checking_updates(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    listed = core.identify_local_mods(client, core.list_local_mods(str(mods_dir)))
    by_name = {m.filename: m for m in listed}
    assert by_name["sodium-old.jar"].display_name == "Sodium"
    assert by_name["sodium-old.jar"].icon_url == "https://cdn.example/sodium.png"
    assert by_name["sodium-old.jar"].current_version == "1.0"
    assert by_name["local.jar"].display_name == "local.jar"
    assert {m.status for m in listed} == {core.STATUS_UNCHECKED} and not any(m.actionable for m in listed)
    assert client.latest_calls == []  # no update check
    # remembered: the next listing needs no network
    again = {m.filename: m for m in core.list_local_mods(str(mods_dir))}
    assert again["sodium-old.jar"].display_name == "Sodium"


def test_updated_files_are_listed_with_their_names(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    core.update_mods(client, [m for m in result.mods if m.actionable], str(mods_dir), False, NO_PROGRESS)
    listed = {m.filename: m.display_name for m in core.list_local_mods(str(mods_dir))}
    assert listed["sodium-0.9.jar"] == "Sodium"


def test_mods_are_disabled_and_enabled_by_renaming(tmp_path):
    folder = tmp_path / "mods"
    folder.mkdir()
    (folder / "a.jar").write_bytes(b"a")
    (folder / "a-copy.jar").write_bytes(b"a")
    mod = core.ModInfo(path=str(folder / "a.jar"), duplicates=[str(folder / "a-copy.jar")])
    core.set_enabled(mod, False)
    assert mod.disabled and sorted(os.listdir(folder)) == ["a-copy.jar.disabled", "a.jar.disabled"]
    core.set_enabled(mod, True)
    assert not mod.disabled and sorted(os.listdir(folder)) == ["a-copy.jar", "a.jar"]


def test_disabling_never_overwrites_a_file(tmp_path):
    folder = tmp_path / "mods"
    folder.mkdir()
    (folder / "a.jar").write_bytes(b"new")
    (folder / "a.jar.disabled").write_bytes(b"old")
    mod = core.ModInfo(path=str(folder / "a.jar"))
    try:
        core.set_enabled(mod, False)
        raise AssertionError("expected an error")
    except OSError:
        pass
    assert (folder / "a.jar").read_bytes() == b"new" and (folder / "a.jar.disabled").read_bytes() == b"old"
    assert mod.path == str(folder / "a.jar")


def test_pinned_mods_are_kept(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    result = core.scan_mods(fake_modrinth(), str(mods_dir), "26.3", "fabric", False, NO_PROGRESS,
                            pinned={"sodium": "S1"})
    sodium = next(m for m in result.mods if m.filename == "sodium-old.jar")
    assert sodium.status == core.STATUS_PINNED and not sodium.actionable
    lithium = next(m for m in result.mods if m.filename == "lithium-old.jar.disabled")
    assert lithium.status == core.STATUS_UPDATE  # other mods are not affected


def test_installing_an_older_version(tmp_path):
    mods_dir = make_mods_folder(tmp_path)
    client = fake_modrinth()
    old = version("S0", ["26.3"], ["fabric"], "2026-01-01", project="sodium", number="0.5",
                  files=[file_entry("sodium-0.5.jar", b"sodium-0.5")])
    client.payloads["https://cdn.example/sodium-0.5.jar"] = b"sodium-0.5"
    client.all_versions = [old]
    result = core.scan_mods(client, str(mods_dir), "26.3", "fabric", False, NO_PROGRESS)
    sodium = next(m for m in result.mods if m.filename == "sodium-old.jar")
    assert core.available_versions(client, sodium, "26.3", ["fabric"]) == [old]
    sodium.latest = old
    core.update_mods(client, [sodium], str(mods_dir), False, NO_PROGRESS)
    assert (mods_dir / "sodium-0.5.jar").exists() and not (mods_dir / "sodium-old.jar").exists()


def test_duplicated_and_incompatible_mods_are_reported(tmp_path):
    def installed(name, project, deps=(), disabled=False):
        path = tmp_path / (name + (".disabled" if disabled else ""))
        path.write_bytes(name.encode())
        return core.ModInfo(path=str(path), title=project.title(), status=core.STATUS_UP_TO_DATE,
                            current={"id": name, "project_id": project, "dependencies": list(deps)})
    jade_old, jade_new = installed("jade-1.jar", "jade"), installed("jade-2.jar", "jade")
    jade_backup = installed("jade-0.jar", "jade", disabled=True)
    optifine = installed("optifabric.jar", "optifabric")
    sodium = installed("sodium.jar", "sodium", deps=[{"project_id": "optifabric", "dependency_type": "incompatible"}])
    missing = core.ModInfo(path=str(tmp_path / "api.jar"), status=core.STATUS_MISSING_DEP, project_hint="fabric-api")
    mods = [jade_old, jade_new, jade_backup, optifine, sodium, missing]
    core.find_problems(mods)
    assert jade_old.other_versions == ["jade-2.jar"] and jade_new.other_versions == ["jade-1.jar"]
    assert jade_backup.other_versions == []  # a disabled copy is not a problem
    assert sodium.incompatible_with == ["Optifabric"] and optifine.incompatible_with == ["Sodium"]
    assert not missing.has_problems


def test_migration_plan_and_migrate(tmp_path):
    """Moving to 26.4: Sodium has a version, Lithium does not and is disabled, local.jar is unknown."""
    mods_dir = make_mods_folder(tmp_path)
    (mods_dir / "lithium-old.jar.disabled").rename(mods_dir / "lithium-old.jar")
    client = fake_modrinth()
    del client.latest[sha(b"lithium-old")]
    plan = core.plan_migration(client, str(mods_dir), core.AUTO, "26.4", False)
    assert [m.display_name for m in plan.ready] == ["Sodium"]
    assert [m.display_name for m in plan.missing] == ["Lithium"]
    assert [m.filename for m in plan.unknown] == ["local.jar"]
    assert client.latest_calls[0] == (("fabric",), ("26.4",))
    backup_dir, failed = core.migrate(client, plan, str(mods_dir), True, True, NO_PROGRESS)
    assert failed == [] and backup_dir
    assert sorted(os.listdir(mods_dir)) == ["lithium-old.jar.disabled", "local.jar", "sodium-0.9.jar"]
