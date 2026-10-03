"""Modrinth modpacks (.mrpack) and comparing two profiles.

An .mrpack is a zip with a modrinth.index.json that lists every file with its
download URL and hashes, plus an overrides/ folder with files that are not on
Modrinth. Prism Launcher, Modrinth App, ATLauncher and others can import it.
See https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack
"""

import hashlib
import json
import os
import posixpath
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests

import updater_core as core
from i18n import t

INDEX = "modrinth.index.json"
OVERRIDES = ("overrides/", "client-overrides/")
# Hosts the format allows downloads from (anything else is refused when importing)
ALLOWED_HOSTS = {"cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com"}
# Keys of the "dependencies" section for each loader
LOADER_KEYS = {"fabric": "fabric-loader", "quilt": "quilt-loader", "neoforge": "neoforge", "forge": "forge"}
LOADER_META = {
    "fabric": "https://meta.fabricmc.net/v2/versions/loader/{game}",
    "quilt": "https://meta.quiltmc.org/v3/versions/loader/{game}",
}
NEOFORGE_META = "https://maven.neoforged.net/api/maven/latest/version/releases/net/neoforged/neoforge"


class ModpackError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def loader_version(loader: Optional[str], game_version: str) -> Optional[str]:
    """Latest stable version of a loader for a Minecraft version (None if unknown)."""
    try:
        session = requests.Session()
        session.headers["User-Agent"] = core.USER_AGENT
        if loader in LOADER_META:
            entries = session.get(LOADER_META[loader].format(game=game_version), timeout=20).json()
            versions = [e["loader"] for e in entries if isinstance(e, dict) and "loader" in e]
            stable = [v for v in versions if v.get("stable", "beta" not in v.get("version", ""))]
            picked = (stable or versions)[:1]
            return picked[0]["version"] if picked else None
        if loader == "neoforge":
            data = session.get(NEOFORGE_META, params={"filter": game_version}, timeout=20).json()
            return data.get("version") or None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return None


def _env(project: Dict) -> Dict[str, str]:
    def side(value: Optional[str]) -> str:
        return value if value in ("required", "optional", "unsupported") else "required"
    return {"client": side(project.get("client_side")), "server": side(project.get("server_side"))}


def export_mrpack(client: core.ModrinthClient, folder: str, content: str, game_version: str, loader: Optional[str],
                  name: str, destination: str) -> Dict[str, int]:
    """Write the enabled files of a profile as an .mrpack. Returns how many are downloads and overrides."""
    spec = core.CONTENT_TYPES.get(content, core.CONTENT_TYPES[core.CONTENT_MODS])
    files = [p for p in core.get_mod_files(folder, spec["extensions"]) if not p.lower().endswith(".disabled")]
    hashes: Dict[str, Dict[str, str]] = {}
    for path in files:
        sha1, sha512 = hashlib.sha1(), hashlib.sha512()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha1.update(chunk)
                sha512.update(chunk)
        hashes[path] = {"sha1": sha1.hexdigest(), "sha512": sha512.hexdigest()}
    versions = client.versions_from_hashes([h["sha512"] for h in hashes.values()]) if hashes else {}
    project_ids = [v["project_id"] for v in versions.values() if v.get("project_id")]
    projects = client.projects(project_ids) if project_ids else {}

    index_files, overrides = [], []
    for path, h in hashes.items():
        version = versions.get(h["sha512"])
        entry = next((f for f in (version or {}).get("files", [])
                      if f.get("hashes", {}).get("sha512") == h["sha512"]), None)
        relative = f"{content}/{os.path.basename(path)}"
        if version and entry and entry.get("url"):
            index_files.append({"path": relative, "hashes": h, "downloads": [entry["url"]],
                                "fileSize": os.path.getsize(path),
                                "env": _env(projects.get(version.get("project_id", ""), {}))})
        else:
            overrides.append((path, "overrides/" + relative))

    dependencies = {"minecraft": game_version}
    loader_key = LOADER_KEYS.get(loader or "")
    found = loader_version(loader, game_version) if loader_key else None
    if loader_key and found:
        dependencies[loader_key] = found
    index = {"formatVersion": 1, "game": "minecraft", "versionId": "1.0.0", "name": name,
             "summary": t("mrpack_summary", app=core.APP_NAME), "files": index_files,
             "dependencies": dependencies}
    tmp = destination + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr(INDEX, json.dumps(index, indent=2, ensure_ascii=False))
        for path, arcname in overrides:
            pack.write(path, arcname)
    os.replace(tmp, destination)
    core.log.info("exported %s: %d downloads, %d overrides", destination, len(index_files), len(overrides))
    return {"downloads": len(index_files), "overrides": len(overrides)}


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

@dataclass
class Modpack:
    name: str
    game_version: str
    loader: Optional[str]
    loader_version: Optional[str]
    files: List[Dict]
    path: str


def _safe_relative(path: str) -> str:
    """A path inside the pack that cannot escape the destination folder."""
    normal = posixpath.normpath(path.replace("\\", "/"))
    if not normal or normal.startswith(("/", "../")) or normal == ".." or ":" in normal:
        raise ModpackError(t("mrpack_bad_path", path=path))
    return normal


def read_mrpack(path: str) -> Modpack:
    try:
        with zipfile.ZipFile(path) as pack:
            index = json.loads(pack.read(INDEX).decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise ModpackError(t("mrpack_invalid", error=e)) from e
    if index.get("game") != "minecraft" or index.get("formatVersion") != 1:
        raise ModpackError(t("mrpack_invalid", error=f"format {index.get('formatVersion')}"))
    deps = index.get("dependencies", {})
    loader = next((name for name, key in LOADER_KEYS.items() if key in deps), None)
    return Modpack(name=index.get("name") or os.path.splitext(os.path.basename(path))[0],
                   game_version=deps.get("minecraft", core.AUTO), loader=loader,
                   loader_version=deps.get(LOADER_KEYS[loader]) if loader else None,
                   files=index.get("files", []), path=path)


def install_mrpack(client: core.ModrinthClient, pack: Modpack, game_dir: str,
                   progress: Callable[[float, str], None]) -> None:
    """Download the pack's client files into game_dir and extract its overrides."""
    files = [f for f in pack.files if (f.get("env") or {}).get("client") != "unsupported"]
    for i, entry in enumerate(files):
        relative = _safe_relative(entry.get("path", ""))
        progress(i / max(len(files), 1), t("prog_updating", mod=os.path.basename(relative)))
        urls = [u for u in entry.get("downloads", []) if urlparse(u).hostname in ALLOWED_HOSTS]
        if not urls:
            raise ModpackError(t("mrpack_bad_url", file=relative))
        destination = os.path.join(game_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        client.download(urls[0], destination, (entry.get("hashes") or {}).get("sha512"))
    with zipfile.ZipFile(pack.path) as archive:
        for info in archive.infolist():
            prefix = next((p for p in OVERRIDES if info.filename.startswith(p)), None)
            if not prefix or info.is_dir():
                continue
            relative = _safe_relative(info.filename[len(prefix):])
            destination = os.path.join(game_dir, *relative.split("/"))
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with archive.open(info) as source, open(destination, "wb") as target:
                target.write(source.read())
    progress(1.0, t("ready"))
    core.log.info("installed modpack %s into %s", pack.name, game_dir)


# --------------------------------------------------------------------------- #
# Comparing two profiles
# --------------------------------------------------------------------------- #

ONLY_A, ONLY_B, DIFFERENT, SAME = "only_a", "only_b", "different", "same"


@dataclass
class Difference:
    name: str
    kind: str                    # ONLY_A, ONLY_B, DIFFERENT or SAME
    version_a: str = ""
    version_b: str = ""
    side: str = ""               # "client" / "server" when the mod only works there
    notes: List[str] = field(default_factory=list)


def _folder_projects(client: core.ModrinthClient, folder: str, content: str) -> Dict[str, Dict]:
    """project id (or file name for files not on Modrinth) -> version data of an enabled file."""
    spec = core.CONTENT_TYPES.get(content, core.CONTENT_TYPES[core.CONTENT_MODS])
    mods, by_hash = core._hash_folder(folder, lambda _f, _m: None, spec["extensions"])
    versions = client.versions_from_hashes(list(by_hash)) if by_hash else {}
    found: Dict[str, Dict] = {}
    for h, mod in by_hash.items():
        if mod.disabled:
            continue
        version = versions.get(h)
        key = version["project_id"] if version and version.get("project_id") else "file:" + mod.filename.lower()
        found[key] = version or {"version_number": mod.filename, "file": mod.filename}
    return found


def compare_folders(client: core.ModrinthClient, folder_a: str, folder_b: str,
                    content: str = core.CONTENT_MODS) -> List[Difference]:
    """What one profile has and the other does not, and the mods whose versions differ."""
    a, b = _folder_projects(client, folder_a, content), _folder_projects(client, folder_b, content)
    ids = [k for k in set(a) | set(b) if not k.startswith("file:")]
    projects = client.projects(ids) if ids else {}
    result = []
    for key in set(a) | set(b):
        project = projects.get(key, {})
        name = project.get("title") or (a.get(key) or b.get(key) or {}).get("file") or key
        side = ""
        if project.get("server_side") == "unsupported":
            side = "client"
        elif project.get("client_side") == "unsupported":
            side = "server"
        va, vb = (a.get(key) or {}).get("version_number", ""), (b.get(key) or {}).get("version_number", "")
        if key not in b:
            kind = ONLY_A
        elif key not in a:
            kind = ONLY_B
        else:
            kind = SAME if va == vb else DIFFERENT
        result.append(Difference(name=name, kind=kind, version_a=va, version_b=vb, side=side))
    order = {DIFFERENT: 0, ONLY_A: 1, ONLY_B: 2, SAME: 3}
    return sorted(result, key=lambda d: (order[d.kind], d.name.lower()))
