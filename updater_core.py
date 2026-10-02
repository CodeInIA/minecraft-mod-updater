"""Core logic for Minecraft Mod Updater (no UI code).

Mods are identified on Modrinth by the SHA-512 hash of their file. Whether a
mod needs updating is decided from Modrinth's version metadata (version id,
publish date and supported game versions/loaders), never by parsing version
strings, so it works with any versioning scheme: old ones like 1.21.5 and the
new year-based ones like 26.3 or 26.4-snapshot-1.
"""

import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple

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
DEFAULT_MINECRAFT_MODS = os.path.join(MINECRAFT_DIR, "mods")

MODRINTH_API_URL = "https://api.modrinth.com/v2"
USER_AGENT = f"CodeInIA/minecraft-mod-updater/{APP_VERSION} ({REPO_URL})"
REQUEST_TIMEOUT = 30
HASH_BATCH_SIZE = 200

# Loaders shown first in the UI; any other loader Modrinth knows comes after.
PREFERRED_LOADERS = ["fabric", "neoforge", "forge", "quilt"]
# Loaders whose mods can also be used by another loader.
COMPATIBLE_LOADERS = {"quilt": ["fabric"]}
# Loaders that are not jar-based mods and make no sense in a mods folder.
IGNORED_LOADERS = {"datapack", "minecraft", "iris", "optifine", "canvas", "vanilla"}

MOD_EXTENSIONS = (".jar", ".jar.disabled")
# Profile value meaning "detect from the mods in the folder".
AUTO = "auto"
MAX_PROFILES = 20

DEFAULT_CONFIG = {
    "config_version": 2,
    "profiles": [
        {"name": "client", "path": DEFAULT_MINECRAFT_MODS, "game_version": AUTO, "loader": AUTO},
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
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    if "profiles" not in config:
        config = _migrate_v1(config)
        save_config(config)

    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, json.loads(json.dumps(value)))
    for profile in config["profiles"]:
        profile["game_version"] = profile.get("game_version") or AUTO
        profile["loader"] = profile.get("loader") or AUTO
    return config


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


class ModrinthClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(method, f"{MODRINTH_API_URL}{path}",
                                            timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise ModrinthError(t("err_connect", error=e)) from e
        if response.status_code == 429:
            raise ModrinthError(t("err_rate_limit"))
        if response.status_code >= 400:
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

    def game_versions(self) -> List[Dict]:
        versions = self._request("GET", "/tag/game_version")
        return sorted(versions, key=lambda v: v.get("date", ""), reverse=True)

    def loaders(self) -> List[str]:
        names = [l["name"] for l in self._request("GET", "/tag/loader")
                 if "mod" in l.get("supported_project_types", []) and l["name"] not in IGNORED_LOADERS]
        return sort_loaders(names)

    def download(self, url: str, destination: str, expected_sha512: Optional[str]) -> None:
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
            raise ModrinthError(t("err_download", error=e)) from e
        if expected_sha512 and h.hexdigest() != expected_sha512:
            _silent_remove(destination)
            raise ModrinthError(t("err_corrupt"))


def sort_loaders(names: Iterable[str]) -> List[str]:
    names = list(dict.fromkeys(names))
    preferred = [l for l in PREFERRED_LOADERS if l in names]
    return preferred + sorted(n for n in names if n not in preferred)


def load_tag_cache() -> Dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
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


def get_mod_files(mod_folder: str) -> List[str]:
    if not os.path.isdir(mod_folder):
        return []
    return sorted(
        os.path.join(mod_folder, f) for f in os.listdir(mod_folder)
        if f.lower().endswith(MOD_EXTENSIONS) and os.path.isfile(os.path.join(mod_folder, f))
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
                          and any(l in mod.current.get("loaders", []) for l in loaders))
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


def _hash_folder(mod_folder: str, progress: ProgressFn) -> Tuple[List[ModInfo], Dict[str, ModInfo]]:
    files = get_mod_files(mod_folder)
    mods: List[ModInfo] = []
    by_hash: Dict[str, ModInfo] = {}
    for i, path in enumerate(files):
        progress(0.6 * i / max(len(files), 1), t("prog_hashing", file=os.path.basename(path)))
        mod = ModInfo(path=path)
        try:
            mod.sha512 = calculate_hash(path)
        except OSError as e:
            mod.error = str(e)
            mods.append(mod)
            continue
        if mod.sha512 in by_hash:
            by_hash[mod.sha512].duplicates.append(path)
            continue
        by_hash[mod.sha512] = mod
        mods.append(mod)
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
        candidates = [l for l, c in loader_counter.items() if c == best]
        result["loader"] = sort_loaders(candidates)[0]
    return result


def scan_mods(client: ModrinthClient, mod_folder: str, game_version: str, loader: str,
              allow_beta: bool, progress: ProgressFn) -> ScanResult:
    """Hash every mod in the folder and look up installed/latest versions on Modrinth.

    `game_version` and `loader` may be AUTO, in which case they are detected
    from the mods already installed in the folder.
    """
    mods, by_hash = _hash_folder(mod_folder, progress)
    result = ScanResult(mods=mods, game_version=None if game_version == AUTO else game_version,
                        loader=None if loader == AUTO else loader)
    if not by_hash:
        return result

    hashes = list(by_hash.keys())
    progress(0.65, t("prog_identifying"))
    current = client.versions_from_hashes(hashes)

    if result.game_version is None or result.loader is None:
        detected = detect_from_versions(current.values())
        result.game_version = result.game_version or detected.get("game_version")
        result.loader = result.loader or detected.get("loader")
        result.detected = True

    latest: Dict[str, Dict] = {}
    loaders = query_loaders(result.loader) if result.loader else []
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
        if mod.current:
            project = projects.get(mod.current.get("project_id"), {})
            mod.title = project.get("title", "")
            mod.icon_url = project.get("icon_url") or ""
            mod.page_url = modrinth_page_url(project, mod.current.get("project_id", ""))
        mod.status = determine_status(mod, result.game_version or "", loaders)

    progress(1.0, t("ready"))
    mods.sort(key=lambda m: (m.status != STATUS_UPDATE, m.display_name.lower()))
    return result


def detect_target(client: ModrinthClient, mod_folder: str) -> Dict[str, str]:
    """Guess the game version and loader a mods folder is built for."""
    _mods, by_hash = _hash_folder(mod_folder, lambda _f, _m: None)
    if not by_hash:
        return {}
    return detect_from_versions(client.versions_from_hashes(list(by_hash.keys())).values())


def backup_root(mod_folder: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(mod_folder)), "mod_updater_backups")


def update_mods(client: ModrinthClient, mods: List[ModInfo], mod_folder: str, backup: bool,
                progress: ProgressFn) -> Optional[str]:
    """Download and install the latest version of each given mod.

    Old files are moved to a timestamped backup folder outside the mods folder
    (so the game does not load them) or deleted when backups are disabled.
    Returns the backup folder used, if any.
    """
    backup_dir = None
    if backup and mods:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(backup_root(mod_folder), stamp)
        os.makedirs(backup_dir, exist_ok=True)

    for i, mod in enumerate(mods):
        progress(i / len(mods), t("prog_updating", mod=mod.display_name))
        file_info = primary_file(mod.latest or {})
        if not file_info:
            mod.status, mod.error = STATUS_FAILED, t("err_no_files")
            continue
        new_name = file_info["filename"] + (".disabled" if mod.disabled else "")
        final_path = os.path.join(mod_folder, new_name)
        part_path = final_path + ".part"
        try:
            client.download(file_info["url"], part_path, file_info.get("hashes", {}).get("sha512"))
            for old in [mod.path] + mod.duplicates:
                if backup_dir:
                    shutil.move(old, os.path.join(backup_dir, os.path.basename(old)))
                else:
                    os.remove(old)
            os.replace(part_path, final_path)
            mod.path = final_path
            mod.duplicates = []
            mod.current = mod.latest
            mod.status = STATUS_UPDATED
        except (ModrinthError, OSError) as e:
            _silent_remove(part_path)
            mod.status, mod.error = STATUS_FAILED, str(e)

    progress(1.0, t("ready"))
    return backup_dir


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
