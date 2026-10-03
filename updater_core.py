"""Core logic for Minecraft Mod Updater (no UI code).

Mods are identified on Modrinth by the SHA-512 hash of their file. Whether a
mod needs updating is decided from Modrinth's version metadata (version id,
publish date and supported game versions/loaders), never by parsing version
strings, so it works with any versioning scheme: old ones like 1.21.5 and the
new year-based ones like 26.3 or 26.4-snapshot-1.
"""

import hashlib
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

from i18n import t

try:
    # Use the operating system's certificate store so HTTPS keeps working
    # behind antivirus/proxy TLS inspection.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

try:
    from app_version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "dev"

APP_NAME = "Minecraft Mod Updater"
REPO_URL = "https://github.com/CodeInIA/minecraft-mod-updater"

HOME = os.path.expanduser("~")
if sys.platform == "win32":
    APPDATA = os.getenv("APPDATA") or HOME
    CONFIG_DIR = os.path.join(APPDATA, "minecraft_mod_updater")
    MINECRAFT_DIR = os.path.join(APPDATA, ".minecraft")
elif sys.platform == "darwin":
    CONFIG_DIR = os.path.join(HOME, "Library", "Application Support", "minecraft_mod_updater")
    MINECRAFT_DIR = os.path.join(HOME, "Library", "Application Support", "minecraft")
else:
    CONFIG_DIR = os.path.join(os.getenv("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "minecraft_mod_updater")
    MINECRAFT_DIR = os.path.join(HOME, ".minecraft")
CONFIG_FILE = os.path.join(CONFIG_DIR, "mod_updater_config.json")
CACHE_FILE = os.path.join(CONFIG_DIR, "modrinth_tags_cache.json")
# SHA-512 of every scanned file with its size and modification time, so unchanged files are not hashed again
HASH_CACHE_FILE = os.path.join(CONFIG_DIR, "hash_cache.json")
# What the last scans learned about each file (by hash): name, icon, page and installed version,
# so a profile's files can be listed with their names before checking for updates
MOD_INFO_CACHE_FILE = os.path.join(CONFIG_DIR, "mod_info_cache.json")
DEFAULT_MINECRAFT_MODS = os.path.join(MINECRAFT_DIR, "mods")
# What the app did and what went wrong, to diagnose problems (rotated, at most ~3 MB)
LOG_FILE = os.path.join(CONFIG_DIR, "mod_updater.log")

log = logging.getLogger("mod_updater")

MODRINTH_API_URL = "https://api.modrinth.com/v2"
USER_AGENT = f"CodeInIA/minecraft-mod-updater/{APP_VERSION} ({REPO_URL})"
REQUEST_TIMEOUT = 30
RETRIES = 3                                  # extra attempts after a failed request
RETRY_STATUSES = {429, 500, 502, 503, 504}   # rate limited or temporary server problems
MAX_RETRY_WAIT = 30                          # seconds
HASH_BATCH_SIZE = 200

# Loaders shown first in the UI; any other loader Modrinth knows comes after.
PREFERRED_LOADERS = ["fabric", "neoforge", "forge", "quilt"]
# Loaders whose mods can also be used by another loader.
COMPATIBLE_LOADERS = {"quilt": ["fabric"]}
# Loaders that are not jar-based mods and make no sense in a mods folder.
IGNORED_LOADERS = {"datapack", "minecraft", "iris", "optifine", "canvas", "vanilla"}

MOD_EXTENSIONS = (".jar", ".jar.disabled")

# What a profile folder contains. Resource packs, shaders and data packs are on
# Modrinth too and are identified and updated exactly like mods; they use fixed
# "loaders" instead of a mod loader.
CONTENT_MODS = "mods"
CONTENT_TYPES: Dict[str, Dict[str, Any]] = {
    "mods": {"extensions": MOD_EXTENSIONS, "loaders": None},
    "resourcepacks": {"extensions": (".zip", ".zip.disabled"), "loaders": ["minecraft"]},
    "shaderpacks": {"extensions": (".zip", ".zip.disabled"), "loaders": ["iris", "optifine", "canvas", "vanilla"]},
    "datapacks": {"extensions": (".zip", ".zip.disabled"), "loaders": ["datapack"]},
}
# Profile value meaning "detect from the mods in the folder".
AUTO = "auto"
MAX_PROFILES = 20
MAX_PROFILE_NAME = 32  # characters; keeps the sidebar a sensible width
# Colors offered for profiles (and given automatically to profiles without one)
PROFILE_COLORS = ["#2E9E5B", "#3B82F6", "#F59E0B", "#EF4444", "#8B5CF6",
                  "#EC4899", "#14B8A6", "#F97316", "#84CC16", "#64748B"]

DEFAULT_CONFIG = {
    "config_version": 2,
    "profiles": [
        {"name": "client", "path": DEFAULT_MINECRAFT_MODS, "game_version": AUTO, "loader": AUTO,
         "color": PROFILE_COLORS[0], "content": CONTENT_MODS, "server": False, "ignored": []},
    ],
    "current_profile": "client",
    "backup_mods": True,
    "allow_beta": False,
    "show_snapshots": False,
    "appearance": "dark",
    "language": "system",
    # Install new versions of this app automatically at startup (otherwise only notify)
    "app_auto_update": True,
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def _migrate_v1(old: Dict) -> Dict:
    """Convert the original config format (mod_folders + global versions) to v2."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    profiles = []
    for name, path in (old.get("mod_folders") or {}).items():
        profiles.append({
            "name": name,
            "path": path,
            "game_version": AUTO,
            "loader": AUTO,
        })
    if profiles:
        config["profiles"] = profiles
    config["current_profile"] = old.get("current_folder", profiles[0]["name"] if profiles else "client")
    config["backup_mods"] = old.get("backup_mods", True)
    return config


def load_config() -> Dict:
    """Load the configuration, migrating old formats and filling missing keys."""
    if not os.path.exists(CONFIG_FILE):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    if not isinstance(config, dict):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    if "profiles" not in config:
        config = _migrate_v1(config)
        save_config(config)

    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, json.loads(json.dumps(value)))
    for profile in config["profiles"]:
        profile["game_version"] = profile.get("game_version") or AUTO
        profile["loader"] = profile.get("loader") or AUTO
        if not profile.get("color"):
            # Avoid the colors of every other profile, including the ones listed after this one
            profile["color"] = next_profile_color(config["profiles"])
        if profile.get("content") not in CONTENT_TYPES:
            profile["content"] = CONTENT_MODS
        if "server" not in profile:  # older configs: guess from the name
            profile["server"] = any(w in profile.get("name", "").lower() for w in ("server", "servidor", "serveur"))
        if not isinstance(profile.get("ignored"), list):
            profile["ignored"] = []
    return config


def content_folder(content: str) -> str:
    """Default folder of the official launcher for a content type."""
    return os.path.join(MINECRAFT_DIR, content)


def next_profile_color(profiles: List[Dict]) -> str:
    """First palette color not used by the given profiles (cycling when all are taken)."""
    used = {p.get("color") for p in profiles}
    for color in PROFILE_COLORS:
        if color not in used:
            return color
    return PROFILE_COLORS[len(profiles) % len(PROFILE_COLORS)]


def save_config(config: Dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)


def reset_config() -> Dict:
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    return load_config()


# --------------------------------------------------------------------------- #
# Modrinth API
# --------------------------------------------------------------------------- #

class ModrinthError(Exception):
    pass


def setup_logging() -> None:
    """Write the app's log to LOG_FILE (called once by the app, not by the tests)."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2,
                                                       encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.info("%s %s started on %s", APP_NAME, APP_VERSION, sys.platform)


def retry_wait(attempt: int, response: Optional[requests.Response] = None) -> float:
    """Seconds to wait before retrying: what Modrinth asks for when rate limited, otherwise 1, 2, 4..."""
    if response is not None and response.status_code == 429:
        try:
            return min(MAX_RETRY_WAIT, max(1.0, float(response.headers.get("X-Ratelimit-Reset", ""))))
        except ValueError:
            pass
    return min(MAX_RETRY_WAIT, float(2 ** attempt))


class ModrinthClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.sleep: Callable[[float], None] = time.sleep  # replaced by the tests

    def _request(self, method: str, path: str, **kwargs):
        url = f"{MODRINTH_API_URL}{path}"
        for attempt in range(RETRIES + 1):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            except requests.RequestException as e:
                if attempt < RETRIES:
                    log.warning("%s %s failed (%s), retrying", method, path, e)
                    self.sleep(retry_wait(attempt))
                    continue
                log.error("%s %s failed: %s", method, path, e)
                raise ModrinthError(t("err_connect", error=e)) from e
            if response.status_code in RETRY_STATUSES and attempt < RETRIES:
                wait = retry_wait(attempt, response)
                log.warning("%s %s answered %s, retrying in %.0f s", method, path, response.status_code, wait)
                self.sleep(wait)
                continue
            break
        if response.status_code == 429:
            log.error("%s %s: rate limited", method, path)
            raise ModrinthError(t("err_rate_limit"))
        if response.status_code >= 400:
            log.error("%s %s answered %s: %s", method, path, response.status_code, response.text[:200])
            raise ModrinthError(t("err_http", code=response.status_code, text=response.text[:200]))
        return response.json()

    @staticmethod
    def _batches(items: List[str]) -> Iterable[List[str]]:
        for i in range(0, len(items), HASH_BATCH_SIZE):
            yield items[i:i + HASH_BATCH_SIZE]

    def versions_from_hashes(self, hashes: List[str]) -> Dict[str, Dict]:
        result = {}
        for batch in self._batches(hashes):
            result.update(self._request("POST", "/version_files",
                                        json={"hashes": batch, "algorithm": "sha512"}))
        return result

    def latest_versions(self, hashes: List[str], loaders: List[str], game_versions: List[str],
                        version_types: List[str]) -> Dict[str, Dict]:
        result = {}
        for batch in self._batches(hashes):
            result.update(self._request("POST", "/version_files/update", json={
                "hashes": batch,
                "algorithm": "sha512",
                "loaders": loaders,
                "game_versions": game_versions,
                "version_types": version_types,
            }))
        return result

    def projects(self, project_ids: List[str]) -> Dict[str, Dict]:
        result = {}
        ids = sorted(set(project_ids))
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            for project in self._request("GET", "/projects", params={"ids": json.dumps(batch)}):
                result[project["id"]] = project
        return result

    def versions(self, version_ids: List[str]) -> List[Dict]:
        result = []
        ids = sorted(set(version_ids))
        for i in range(0, len(ids), 100):
            result += self._request("GET", "/versions", params={"ids": json.dumps(ids[i:i + 100])})
        return result

    def project_versions(self, project_id: str, loaders: List[str], game_versions: List[str]) -> List[Dict]:
        """Versions of a project for the given loaders and game versions, newest first."""
        versions = self._request("GET", f"/project/{project_id}/version",
                                 params={"loaders": json.dumps(loaders), "game_versions": json.dumps(game_versions)})
        return sorted(versions, key=lambda v: v.get("date_published", ""), reverse=True)

    def game_versions(self) -> List[Dict]:
        versions = self._request("GET", "/tag/game_version")
        return sorted(versions, key=lambda v: v.get("date", ""), reverse=True)

    def loaders(self) -> List[str]:
        names = [tag["name"] for tag in self._request("GET", "/tag/loader")
                 if "mod" in tag.get("supported_project_types", []) and tag["name"] not in IGNORED_LOADERS]
        return sort_loaders(names)

    def download(self, url: str, destination: str, expected_sha512: Optional[str]) -> None:
        """Download a file, retrying failed or corrupted downloads."""
        for attempt in range(RETRIES + 1):
            last = attempt == RETRIES
            h = hashlib.sha512()
            try:
                with self.session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as response:
                    response.raise_for_status()
                    with open(destination, "wb") as f:
                        for chunk in response.iter_content(chunk_size=65536):
                            f.write(chunk)
                            h.update(chunk)
            except (requests.RequestException, OSError) as e:
                _silent_remove(destination)
                status = getattr(getattr(e, "response", None), "status_code", None)
                if not last and (status is None or status in RETRY_STATUSES):
                    log.warning("download of %s failed (%s), retrying", url, e)
                    self.sleep(retry_wait(attempt))
                    continue
                log.error("download of %s failed: %s", url, e)
                raise ModrinthError(t("err_download", error=e)) from e
            if expected_sha512 and h.hexdigest() != expected_sha512:
                _silent_remove(destination)
                if not last:
                    log.warning("download of %s is corrupted, retrying", url)
                    continue
                log.error("download of %s is corrupted", url)
                raise ModrinthError(t("err_corrupt"))
            return


def sort_loaders(names: Iterable[str]) -> List[str]:
    names = list(dict.fromkeys(names))
    preferred = [name for name in PREFERRED_LOADERS if name in names]
    return preferred + sorted(n for n in names if n not in preferred)


def load_tag_cache() -> Dict:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fetch_tags(client: ModrinthClient) -> Dict:
    """Fetch the game version and loader lists from Modrinth, caching them for offline use."""
    tags = {"game_versions": client.game_versions(), "loaders": client.loaders()}
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(tags, f)
    except OSError:
        pass
    return tags


# --------------------------------------------------------------------------- #
# Mods
# --------------------------------------------------------------------------- #

STATUS_UP_TO_DATE = "up_to_date"
STATUS_UPDATE = "update"
STATUS_NOT_FOUND = "not_found"
STATUS_NO_COMPATIBLE = "no_compatible"
STATUS_UPDATED = "updated"
STATUS_FAILED = "failed"
STATUS_MISSING_DEP = "missing_dependency"  # required by another mod but not installed
STATUS_INSTALLED = "installed"             # a missing dependency that was just installed
STATUS_IGNORED = "ignored"                 # the user chose not to update this mod
STATUS_UNCHECKED = "unchecked"             # listed from the folder, not checked on Modrinth yet

# Statuses whose rows can be ticked and updated/installed
ACTIONABLE_STATUSES = (STATUS_UPDATE, STATUS_MISSING_DEP)

SIDE_CLIENT_ONLY = "client_only"  # in a server profile: the mod does nothing on a server
SIDE_SERVER_ONLY = "server_only"  # in a client profile: the mod only works on servers


@dataclass
class ModInfo:
    path: str
    sha512: str = ""
    current: Optional[Dict] = None
    latest: Optional[Dict] = None
    title: str = ""
    icon_url: str = ""
    page_url: str = ""
    status: str = STATUS_NOT_FOUND
    error: str = ""
    duplicates: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)  # for missing dependencies
    side_warning: str = ""                                 # SIDE_CLIENT_ONLY / SIDE_SERVER_ONLY
    project_hint: str = ""                                 # project id when there is no version data

    @property
    def project_id(self) -> str:
        return (self.current or self.latest or {}).get("project_id") or self.project_hint

    @property
    def actionable(self) -> bool:
        return self.status in ACTIONABLE_STATUSES and self.latest is not None

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def disabled(self) -> bool:
        return self.path.lower().endswith(".disabled")

    @property
    def display_name(self) -> str:
        return self.title or self.filename

    @property
    def current_version(self) -> str:
        return self.current.get("version_number", "?") if self.current else "—"

    @property
    def latest_version(self) -> str:
        return self.latest.get("version_number", "?") if self.latest else "—"


def modrinth_page_url(project: Dict, project_id: str) -> str:
    """Public Modrinth page of a project, e.g. https://modrinth.com/mod/sodium."""
    slug = project.get("slug") or project_id
    if not slug:
        return ""
    return f"https://modrinth.com/{project.get('project_type') or 'project'}/{slug}"


def calculate_hash(file_path: str) -> str:
    h = hashlib.sha512()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_mod_files(mod_folder: str, extensions=MOD_EXTENSIONS) -> List[str]:
    if not os.path.isdir(mod_folder):
        return []
    return sorted(
        os.path.join(mod_folder, f) for f in os.listdir(mod_folder)
        if f.lower().endswith(extensions) and os.path.isfile(os.path.join(mod_folder, f))
    )


def query_loaders(loader: str) -> List[str]:
    return [loader] + COMPATIBLE_LOADERS.get(loader, [])


def primary_file(version: Dict) -> Optional[Dict]:
    files = version.get("files") or []
    for f in files:
        if f.get("primary"):
            return f
    return files[0] if files else None


def _parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return datetime.min


def determine_status(mod: ModInfo, game_version: str, loaders: List[str]) -> str:
    if mod.current is None:
        return STATUS_NOT_FOUND
    if mod.latest is None:
        return STATUS_NO_COMPATIBLE
    if mod.latest.get("id") == mod.current.get("id"):
        return STATUS_UP_TO_DATE
    if any(f.get("hashes", {}).get("sha512") == mod.sha512 for f in mod.latest.get("files", [])):
        return STATUS_UP_TO_DATE

    current_compatible = (game_version in mod.current.get("game_versions", [])
                          and any(name in mod.current.get("loaders", []) for name in loaders))
    if current_compatible and (_parse_date(mod.latest.get("date_published", ""))
                               <= _parse_date(mod.current.get("date_published", ""))):
        # Installed file is already valid for the target and is not older.
        return STATUS_UP_TO_DATE
    # Either a newer release, or the installed file targets another game
    # version/loader and Modrinth has one for the selected target.
    return STATUS_UPDATE


ProgressFn = Callable[[float, str], None]


@dataclass
class ScanResult:
    mods: List[ModInfo]
    game_version: Optional[str]  # target actually used (detected when the profile is on "auto")
    loader: Optional[str]
    detected: bool = False
    loaders: List[str] = field(default_factory=list)  # loaders sent to Modrinth for this scan
    content: str = CONTENT_MODS


def _load_hash_cache() -> Dict[str, Dict]:
    try:
        with open(HASH_CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_json(path: str) -> Dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_json(path: str, data: Dict) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        pass


def _remember_mod_info(mods: Iterable[ModInfo]) -> None:
    """Keep what a scan learned about each file for list_local_mods()."""
    cache = _load_json(MOD_INFO_CACHE_FILE)
    changed = False
    for mod in mods:
        if mod.sha512 and mod.current:
            info = {"title": mod.title, "icon_url": mod.icon_url, "page_url": mod.page_url,
                    "version_number": mod.current.get("version_number", ""),
                    "project_id": mod.current.get("project_id", "")}
            if cache.get(mod.sha512) != info:
                cache[mod.sha512] = info
                changed = True
    if changed:
        _save_json(MOD_INFO_CACHE_FILE, cache)


# ----- identifying files by the metadata inside the jar -------------------- #
# Some files are not on Modrinth byte for byte (for example a version only
# published on CurseForge), so their hash is unknown. Their mod ID usually is
# the project's slug on Modrinth, which still tells which project they belong to.

JAR_ICON_PREFIX = "jar:"  # icon_url of an icon inside a jar: "jar:<jar path>!<member>"
NO_DATE = "1970-01-01T00:00:00Z"


def _toml_value(text: str, key: str) -> str:
    match = re.search(rf'^\s*{key}\s*=\s*["\']([^"\']*)["\']', text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def read_jar_metadata(path: str) -> Dict[str, str]:
    """Mod ID, name, version, icon and links declared inside a mod jar (Fabric, Quilt, (Neo)Forge)."""
    meta = {"id": "", "name": "", "version": "", "icon": "", "links": ""}
    try:
        with zipfile.ZipFile(path) as jar:
            names = set(jar.namelist())

            def read(member: str) -> str:
                return jar.read(member).decode("utf-8", "replace")

            if "fabric.mod.json" in names or "quilt.mod.json" in names:
                if "fabric.mod.json" in names:
                    info = extra = json.loads(read("fabric.mod.json"), strict=False)
                else:
                    info = json.loads(read("quilt.mod.json"), strict=False).get("quilt_loader", {})
                    extra = info.get("metadata", {})
                icon = extra.get("icon") or ""
                if isinstance(icon, dict):  # {"16": "a.png", "128": "b.png"}: take the largest
                    sizes = sorted(icon, key=lambda k: int(k) if str(k).isdigit() else 0)
                    icon = icon[sizes[-1]] if sizes else ""
                contact = extra.get("contact") or {}
                meta.update(id=str(info.get("id") or ""), name=str(extra.get("name") or ""),
                            version=str(info.get("version") or ""), icon=str(icon).lstrip("/"),
                            links=" ".join(str(v) for v in contact.values()) if isinstance(contact, dict) else "")
            else:
                toml = next((m for m in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml") if m in names), None)
                if toml:
                    text = read(toml)
                    meta.update(id=_toml_value(text, "modId"), name=_toml_value(text, "displayName"),
                                version=_toml_value(text, "version"), icon=_toml_value(text, "logoFile"),
                                links=" ".join(_toml_value(text, k) for k in ("displayURL", "issueTrackerURL")))
            if "${" in meta["version"]:
                found = None
                if "META-INF/MANIFEST.MF" in names:
                    found = re.search(r"^Implementation-Version:\s*(\S+)", read("META-INF/MANIFEST.MF"), re.MULTILINE)
                meta["version"] = found.group(1) if found else ""
            if meta["icon"] and meta["icon"] not in names:
                meta["icon"] = ""
    except (OSError, zipfile.BadZipFile, ValueError, AttributeError, KeyError, TypeError):
        pass
    return meta


def jar_icon_url(path: str, meta: Optional[Dict[str, str]] = None) -> str:
    meta = meta if meta is not None else read_jar_metadata(path)
    return f"{JAR_ICON_PREFIX}{os.path.abspath(path)}!{meta['icon']}" if meta.get("icon") else ""


def _simple_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _version_key(number: str) -> Tuple[int, ...]:
    """Numeric part of a version number ("26.3.4+fabric" -> (26, 3, 4)); empty if there is none."""
    parts = []
    for piece in re.split(r"[.\-]", number.split("+")[0].lstrip("vV")):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts)


def _projects_for_metadata(client: "ModrinthClient", metas: Dict[str, Dict[str, str]]) -> Dict[str, Dict]:
    """Modrinth project of each file (by hash) whose mod ID is a project slug with the same name."""
    ids = sorted({m["id"].lower() for m in metas.values() if m.get("id")})
    if not ids:
        return {}
    try:
        projects = list(client.projects(ids).values())
    except ModrinthError:
        return {}
    by_slug = {(p.get("slug") or "").lower(): p for p in projects}
    found = {}
    for h, meta in metas.items():
        project = by_slug.get(meta.get("id", "").lower())
        if not project:
            continue
        title = _simple_name(project.get("title", ""))
        names = {_simple_name(meta.get("name", "")), _simple_name(meta.get("id", ""))} - {""}
        linked = f"modrinth.com/mod/{project.get('slug', '')}".lower() in meta.get("links", "").lower()
        if linked or title in names:
            found[h] = project
    return found


def _version_from_metadata(project: Dict, meta: Dict[str, str], candidates: List[Dict]) -> Dict:
    """Version data for a jar Modrinth does not know, from what the jar declares.

    Uses the Modrinth version with the same number when there is one; otherwise
    dates the file like the newest Modrinth version that is not newer than it,
    so changelogs start after it.
    """
    number = meta.get("version", "")
    for v in candidates:
        if number and v.get("version_number") == number:
            return v
    mine = _version_key(number)
    older = [v for v in candidates if mine and _version_key(v.get("version_number", "")) <= mine]
    date = max((v.get("date_published", "") for v in older), default="") or NO_DATE
    return {"id": "", "project_id": project["id"], "version_number": number or "?",
            "date_published": date, "game_versions": [], "loaders": [], "files": [], "from_metadata": True}


def _status_from_metadata(mod: ModInfo, meta: Dict[str, str]) -> str:
    if mod.latest is None:
        return STATUS_NO_COMPATIBLE
    if mod.latest is mod.current:
        return STATUS_UP_TO_DATE
    mine, theirs = _version_key(meta.get("version", "")), _version_key(mod.latest.get("version_number", ""))
    if mine and theirs:
        return STATUS_UP_TO_DATE if theirs <= mine else STATUS_UPDATE
    return STATUS_UP_TO_DATE if mod.latest.get("version_number") == meta.get("version") else STATUS_UPDATE


def _identify_by_metadata(client: "ModrinthClient", mods: Dict[str, ModInfo]) -> Dict[str, Tuple[Dict, Dict]]:
    """(project, jar metadata) of each unknown jar (by hash) found on Modrinth by its mod ID."""
    metas = {h: read_jar_metadata(m.path) for h, m in mods.items() if ".jar" in m.filename.lower()}
    projects = _projects_for_metadata(client, metas)
    return {h: (project, metas[h]) for h, project in projects.items()}


def _fill_icons_from_jars(mods: Iterable[ModInfo]) -> None:
    """Use the icon inside the jar for mods without an icon on Modrinth (or not on Modrinth)."""
    for mod in mods:
        if not mod.icon_url and ".jar" in mod.filename.lower() and os.path.isfile(mod.path):
            mod.icon_url = jar_icon_url(mod.path)


def list_local_mods(mod_folder: str, content: str = CONTENT_MODS) -> List[ModInfo]:
    """The files of a profile folder, without going online.

    Names, icons and installed versions come from earlier scans when the file
    was seen before; everything is marked as not checked yet.
    """
    spec = CONTENT_TYPES.get(content, CONTENT_TYPES[CONTENT_MODS])
    mods, _by_hash = _hash_folder(mod_folder, lambda _f, _m: None, spec["extensions"])
    cache = _load_json(MOD_INFO_CACHE_FILE)
    for mod in mods:
        mod.status = STATUS_UNCHECKED
        info = cache.get(mod.sha512)
        if info:
            mod.title = info.get("title", "")
            mod.icon_url = info.get("icon_url", "")
            mod.page_url = info.get("page_url", "")
            mod.current = {"version_number": info.get("version_number", "?"),
                           "project_id": info.get("project_id", "")}
    _fill_icons_from_jars(mods)
    return sorted(mods, key=lambda m: m.display_name.lower())


def identify_local_mods(client: ModrinthClient, mods: List[ModInfo]) -> List[ModInfo]:
    """Fill in the name, icon, page and installed version of listed files never seen before.

    Only asks Modrinth which version each file is (no update check), so the
    list looks complete the first time a profile is opened.
    """
    unknown = {m.sha512: m for m in mods if m.sha512 and not m.current}
    if not unknown:
        return mods
    current = client.versions_from_hashes(list(unknown))
    project_ids = [v["project_id"] for v in current.values() if v.get("project_id")]
    try:
        projects = client.projects(project_ids) if project_ids else {}
    except ModrinthError:
        projects = {}
    for h, version in current.items():
        mod = unknown.get(h)
        if not mod:
            continue
        project = projects.get(version.get("project_id", ""), {})
        mod.current = version
        mod.title = project.get("title", "")
        mod.icon_url = project.get("icon_url") or ""
        mod.page_url = modrinth_page_url(project, version.get("project_id", ""))
    still_unknown = {h: m for h, m in unknown.items() if not m.current}
    for h, (project, meta) in _identify_by_metadata(client, still_unknown).items():
        mod = still_unknown[h]
        mod.current = _version_from_metadata(project, meta, [])
        mod.title = project.get("title", "")
        mod.icon_url = project.get("icon_url") or ""
        mod.page_url = modrinth_page_url(project, project["id"])
    _fill_icons_from_jars(unknown.values())
    _remember_mod_info(unknown.values())
    return sorted(mods, key=lambda m: m.display_name.lower())


def _save_hash_cache(cache: Dict[str, Dict]) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = HASH_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, HASH_CACHE_FILE)
    except OSError:
        pass


def _hash_folder(mod_folder: str, progress: ProgressFn,
                 extensions=MOD_EXTENSIONS) -> Tuple[List[ModInfo], Dict[str, ModInfo]]:
    """Hash every file of the folder, reusing cached hashes of files that did not change."""
    files = get_mod_files(mod_folder, extensions)
    cache = _load_hash_cache()
    changed = False
    mods: List[ModInfo] = []
    by_hash: Dict[str, ModInfo] = {}
    for i, path in enumerate(files):
        progress(0.6 * i / max(len(files), 1), t("prog_hashing", file=os.path.basename(path)))
        mod = ModInfo(path=path)
        key = os.path.abspath(path)
        try:
            stat = os.stat(path)
            entry = cache.get(key)
            if entry and entry.get("size") == stat.st_size and entry.get("mtime") == stat.st_mtime_ns:
                mod.sha512 = entry["sha512"]
            else:
                mod.sha512 = calculate_hash(path)
                cache[key] = {"size": stat.st_size, "mtime": stat.st_mtime_ns, "sha512": mod.sha512}
                changed = True
        except OSError as e:
            mod.error = str(e)
            mods.append(mod)
            continue
        if mod.sha512 in by_hash:
            by_hash[mod.sha512].duplicates.append(path)
            continue
        by_hash[mod.sha512] = mod
        mods.append(mod)
    # Forget files of this folder that no longer exist
    prefix = os.path.join(os.path.abspath(mod_folder), "")
    present = {os.path.abspath(p) for p in files}
    for key in [k for k in cache if k.startswith(prefix) and k not in present]:
        del cache[key]
        changed = True
    if changed:
        _save_hash_cache(cache)
    return mods, by_hash


def detect_from_versions(versions: Iterable[Dict]) -> Dict[str, str]:
    """Guess the game version and loader from the installed versions of the mods.

    Picks the game version supported by the most mods (newest on ties) and the
    most common loader (fabric > neoforge > forge > quilt on ties).
    """
    game_counter: Counter = Counter()
    loader_counter: Counter = Counter()
    for v in versions:
        game_counter.update(set(v.get("game_versions", [])))
        loader_counter.update(set(v.get("loaders", [])) - IGNORED_LOADERS)
    result = {}
    if game_counter:
        best = max(game_counter.values())
        candidates = {g for g, c in game_counter.items() if c == best}
        order = [g["version"] for g in load_tag_cache().get("game_versions", [])]
        ranked = [g for g in order if g in candidates]
        result["game_version"] = ranked[0] if ranked else sorted(candidates)[-1]
    if loader_counter:
        best = max(loader_counter.values())
        top_loaders = [name for name, c in loader_counter.items() if c == best]
        result["loader"] = sort_loaders(top_loaders)[0]
    return result


def scan_mods(client: ModrinthClient, mod_folder: str, game_version: str, loader: str,
              allow_beta: bool, progress: ProgressFn, content: str = CONTENT_MODS,
              ignored: Iterable[str] = (), server: bool = False) -> ScanResult:
    """Hash every file in the folder and look up installed/latest versions on Modrinth.

    `game_version` and `loader` may be AUTO, in which case they are detected
    from the files already in the folder. Mods whose project is in `ignored`
    are never offered for update. For mod folders, required dependencies that
    are not installed are added to the result.
    """
    spec = CONTENT_TYPES.get(content, CONTENT_TYPES[CONTENT_MODS])
    fixed_loaders = spec["loaders"]
    ignored = set(ignored)
    mods, by_hash = _hash_folder(mod_folder, progress, spec["extensions"])
    result = ScanResult(mods=mods, game_version=None if game_version == AUTO else game_version,
                        loader=None if (loader == AUTO or fixed_loaders) else loader, content=content)
    if not by_hash:
        return result

    hashes = list(by_hash.keys())
    progress(0.65, t("prog_identifying"))
    current = client.versions_from_hashes(hashes)

    if result.game_version is None or (result.loader is None and not fixed_loaders):
        detected = detect_from_versions(current.values())
        result.game_version = result.game_version or detected.get("game_version")
        if not fixed_loaders:
            result.loader = result.loader or detected.get("loader")
        result.detected = True

    latest: Dict[str, Dict] = {}
    loaders = list(fixed_loaders) if fixed_loaders else (query_loaders(result.loader) if result.loader else [])
    result.loaders = loaders
    if result.game_version and loaders:
        version_types = ["release", "beta", "alpha"] if allow_beta else ["release"]
        progress(0.75, t("prog_checking"))
        latest = client.latest_versions(hashes, loaders, [result.game_version], version_types)
        if not allow_beta:
            # Mods that only publish betas would otherwise show as "no compatible".
            missing = [h for h in hashes if h in current and h not in latest]
            if missing:
                latest.update(client.latest_versions(missing, loaders, [result.game_version],
                                                     ["release", "beta", "alpha"]))

    progress(0.85, t("prog_names"))
    project_ids = [v["project_id"] for v in current.values() if v.get("project_id")]
    try:
        projects = client.projects(project_ids) if project_ids else {}
    except ModrinthError:
        projects = {}

    for h, mod in by_hash.items():
        mod.current = current.get(h)
        mod.latest = latest.get(h)
        mod.status = determine_status(mod, result.game_version or "", loaders)
        if mod.current:
            project = projects.get(mod.current.get("project_id", ""), {})
            mod.title = project.get("title", "")
            mod.icon_url = project.get("icon_url") or ""
            mod.page_url = modrinth_page_url(project, mod.current.get("project_id", ""))
            if mod.project_id in ignored:
                mod.status = STATUS_IGNORED
            if project.get("server_side" if server else "client_side") == "unsupported":
                mod.side_warning = SIDE_CLIENT_ONLY if server else SIDE_SERVER_ONLY

    unknown = {h: m for h, m in by_hash.items() if m.current is None}
    if content == CONTENT_MODS and unknown:
        for h, (project, meta) in _identify_by_metadata(client, unknown).items():
            mod = unknown[h]
            candidates: List[Dict] = []
            if result.game_version and loaders:
                try:
                    candidates = client.project_versions(project["id"], loaders, [result.game_version])
                except ModrinthError:
                    pass
            stable = [v for v in candidates if v.get("version_type") == "release"]
            picked = candidates if allow_beta else (stable or candidates)
            mod.current = _version_from_metadata(project, meta, candidates)
            mod.latest = picked[0] if picked else None
            mod.status = _status_from_metadata(mod, meta)
            mod.title = project.get("title", "")
            mod.icon_url = project.get("icon_url") or ""
            mod.page_url = modrinth_page_url(project, project["id"])
            if mod.project_id in ignored:
                mod.status = STATUS_IGNORED
            if project.get("server_side" if server else "client_side") == "unsupported":
                mod.side_warning = SIDE_CLIENT_ONLY if server else SIDE_SERVER_ONLY
    _fill_icons_from_jars(by_hash.values())

    if content == CONTENT_MODS and result.game_version and loaders:
        progress(0.92, t("prog_dependencies"))
        try:
            mods.extend(find_missing_dependencies(client, list(by_hash.values()), mod_folder,
                                                  result.game_version, loaders, allow_beta))
        except ModrinthError:
            pass  # dependencies are a bonus; the scan itself succeeded

    _remember_mod_info(by_hash.values())
    log.info("scanned %s (%s, %s %s): %s", mod_folder, content, result.game_version, result.loader,
             dict(Counter(m.status for m in mods)))
    progress(1.0, t("ready"))
    first = (STATUS_MISSING_DEP, STATUS_UPDATE)
    mods.sort(key=lambda m: (m.status not in first, m.status != STATUS_MISSING_DEP, m.display_name.lower()))
    return result


def find_missing_dependencies(client: ModrinthClient, mods: List[ModInfo], mod_folder: str,
                              game_version: str, loaders: List[str], allow_beta: bool) -> List[ModInfo]:
    """Required dependencies of the installed mods (or of their updates) that are not installed."""
    installed = {m.project_id for m in mods if m.project_id}
    required: Dict[str, List[str]] = {}
    by_version: Dict[str, List[str]] = {}
    for mod in mods:
        version = mod.latest if mod.status == STATUS_UPDATE else mod.current
        for dep in (version or {}).get("dependencies") or []:
            if dep.get("dependency_type") != "required":
                continue
            if dep.get("project_id"):
                required.setdefault(dep["project_id"], []).append(mod.display_name)
            elif dep.get("version_id"):
                by_version.setdefault(dep["version_id"], []).append(mod.display_name)
    if by_version:
        for v in client.versions(list(by_version)):
            required.setdefault(v["project_id"], []).extend(by_version.get(v["id"], []))

    missing = {pid: names for pid, names in required.items() if pid not in installed}
    if not missing:
        return []
    projects = client.projects(list(missing))
    found = []
    for pid, names in missing.items():
        candidates = client.project_versions(pid, loaders, [game_version])
        stable = [v for v in candidates if v.get("version_type") == "release"]
        picked = (candidates if allow_beta else (stable or candidates))[:1]
        version = picked[0] if picked else None
        file_info = primary_file(version) if version else None
        project = projects.get(pid, {})
        filename = file_info["filename"] if file_info else f"{project.get('slug') or pid}.jar"
        found.append(ModInfo(
            path=os.path.join(mod_folder, filename), latest=version, status=STATUS_MISSING_DEP,
            title=project.get("title", ""), icon_url=project.get("icon_url") or "",
            page_url=modrinth_page_url(project, pid), required_by=sorted(set(names)), project_hint=pid))
    return sorted(found, key=lambda m: m.display_name.lower())


def changelog_entries(client: ModrinthClient, mod: ModInfo, game_version: str,
                      loaders: List[str]) -> List[Dict]:
    """Changelogs of every version between the installed one and the available one, newest first."""
    target = mod.latest
    if not target:
        return []
    since = _parse_date(mod.current.get("date_published", "")) if mod.current else datetime.min
    until = _parse_date(target.get("date_published", ""))
    versions = []
    if mod.project_id and game_version and loaders:
        versions = client.project_versions(mod.project_id, loaders, [game_version])
    picked = [v for v in versions if since < _parse_date(v.get("date_published", "")) <= until]
    if not any(v.get("id") == target.get("id") for v in picked):
        picked.append(target)
    picked.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    return [{"version": v.get("version_number", "?"), "date": (v.get("date_published") or "")[:10],
             "type": v.get("version_type", "release"), "changelog": (v.get("changelog") or "").strip()}
            for v in picked]


def detect_target(client: ModrinthClient, mod_folder: str, content: str = CONTENT_MODS) -> Dict[str, str]:
    """Guess the game version and loader a folder is built for."""
    spec = CONTENT_TYPES.get(content, CONTENT_TYPES[CONTENT_MODS])
    _mods, by_hash = _hash_folder(mod_folder, lambda _f, _m: None, spec["extensions"])
    if not by_hash:
        return {}
    return detect_from_versions(client.versions_from_hashes(list(by_hash.keys())).values())


def backup_root(mod_folder: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(mod_folder)), "mod_updater_backups")


BACKUP_MANIFEST = "manifest.json"


def update_mods(client: ModrinthClient, mods: List[ModInfo], mod_folder: str, backup: bool,
                progress: ProgressFn) -> Optional[str]:
    """Download and install the latest version of each given mod (or the missing dependency).

    Old files are moved to a timestamped backup folder outside the mods folder
    (so the game does not load them) or deleted when backups are disabled. The
    backup folder gets a manifest so the update can be undone with
    restore_backup(). Returns the backup folder used, if any.
    """
    backup_dir = None
    if backup and mods:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(backup_root(mod_folder), stamp)
        suffix = 1
        while os.path.exists(backup_dir):  # two updates in the same second
            suffix += 1
            backup_dir = os.path.join(backup_root(mod_folder), f"{stamp}_{suffix}")
        os.makedirs(backup_dir)
    entries = []

    for i, mod in enumerate(mods):
        progress(i / len(mods), t("prog_updating", mod=mod.display_name))
        is_new = mod.current is None
        file_info = primary_file(mod.latest or {})
        if not file_info:
            mod.status, mod.error = STATUS_FAILED, t("err_no_files")
            continue
        new_name = file_info["filename"] + (".disabled" if mod.disabled and not is_new else "")
        final_path = os.path.join(mod_folder, new_name)
        part_path = final_path + ".part"
        old_files = [] if is_new else [mod.path] + mod.duplicates
        try:
            client.download(file_info["url"], part_path, file_info.get("hashes", {}).get("sha512"))
            for old in old_files:
                if backup_dir:
                    shutil.move(old, os.path.join(backup_dir, os.path.basename(old)))
                else:
                    os.remove(old)
            os.replace(part_path, final_path)
            entries.append({"title": mod.display_name, "old": [os.path.basename(o) for o in old_files],
                            "new": new_name})
            mod.path = final_path
            mod.duplicates = []
            mod.current = mod.latest
            mod.sha512 = file_info.get("hashes", {}).get("sha512", "")
            mod.status = STATUS_INSTALLED if is_new else STATUS_UPDATED
            log.info("%s %s: %s -> %s", "installed" if is_new else "updated", mod.display_name,
                     ", ".join(os.path.basename(o) for o in old_files) or "-", new_name)
        except (ModrinthError, OSError) as e:
            _silent_remove(part_path)
            mod.status, mod.error = STATUS_FAILED, str(e)
            log.error("could not update %s: %s", mod.display_name, e)

    # So the new files show their names when the profile is listed again
    _remember_mod_info(m for m in mods if m.status in (STATUS_UPDATED, STATUS_INSTALLED))

    if backup_dir:
        if entries:
            with open(os.path.join(backup_dir, BACKUP_MANIFEST), "w", encoding="utf-8") as f:
                json.dump({"folder": os.path.abspath(mod_folder), "created": datetime.now().isoformat(),
                           "entries": entries}, f, indent=2, ensure_ascii=False)
        else:
            shutil.rmtree(backup_dir, ignore_errors=True)
            backup_dir = None
    progress(1.0, t("ready"))
    return backup_dir


@dataclass
class Backup:
    path: str
    created: datetime
    folder: str
    entries: List[Dict]


def list_backups(mod_folder: str) -> List[Backup]:
    """Backups made by update_mods() for this folder, newest first."""
    root = backup_root(mod_folder)
    folder = os.path.normcase(os.path.abspath(mod_folder))
    backups: List[Backup] = []
    if not os.path.isdir(root):
        return backups
    for name in os.listdir(root):
        manifest = os.path.join(root, name, BACKUP_MANIFEST)
        try:
            with open(manifest, encoding="utf-8") as f:
                data = json.load(f)
            if os.path.normcase(os.path.abspath(data["folder"])) != folder:
                continue
            backups.append(Backup(path=os.path.join(root, name), created=datetime.fromisoformat(data["created"]),
                                  folder=data["folder"], entries=data.get("entries", [])))
        except (OSError, ValueError, KeyError, TypeError):
            continue  # not a backup of this folder (or made by an older version without manifest)
    return sorted(backups, key=lambda b: b.created, reverse=True)


def restore_backup(backup: Backup) -> List[str]:
    """Undo an update: remove the files it installed and put the old ones back.

    Returns the problems found (empty when everything was restored). The
    backup folder is deleted once it has been fully restored.
    """
    errors = []
    for entry in backup.entries:
        try:
            new_path = os.path.join(backup.folder, entry["new"])
            if entry.get("new") and os.path.exists(new_path):
                os.remove(new_path)
            for old in entry.get("old") or []:
                shutil.move(os.path.join(backup.path, old), os.path.join(backup.folder, old))
        except (OSError, KeyError) as e:
            errors.append(f"{entry.get('title', '?')}: {e}")
    if not errors:
        shutil.rmtree(backup.path, ignore_errors=True)
    return errors


def delete_backup(backup: Backup) -> None:
    shutil.rmtree(backup.path, ignore_errors=True)


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
