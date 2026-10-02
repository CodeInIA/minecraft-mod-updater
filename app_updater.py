"""Self-update: check GitHub releases and install a newer version of the app.

Windows runs the Inno Setup installer silently (it relaunches the app).
macOS and Linux replace the app folder with a small helper script that waits
for this process to exit and then starts the new version.
"""

import hashlib
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import requests

from i18n import t
from updater_core import APP_VERSION, REPO_URL, USER_AGENT

LATEST_RELEASE_API = "https://api.github.com/repos/CodeInIA/minecraft-mod-updater/releases/latest"
RELEASES_PAGE = f"{REPO_URL}/releases/latest"
ASSET_NAMES = {
    "win32": "MinecraftModUpdater_Setup.exe",
    "darwin": "MinecraftModUpdater_macOS.dmg",
    "linux": "MinecraftModUpdater_Linux.tar.gz",
}
TIMEOUT = 30


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    page_url: str
    asset_url: Optional[str]
    asset_name: Optional[str]
    sha256: Optional[str]


def parse_version(value: str) -> Optional[Tuple[int, ...]]:
    try:
        return tuple(int(part) for part in value.strip().lstrip("vV").split("."))
    except (AttributeError, ValueError):
        return None


def is_frozen() -> bool:
    """True when running the packaged app (not from source)."""
    return bool(getattr(sys, "frozen", False))


def _platform_key() -> str:
    return "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"


def fetch_latest() -> Release:
    try:
        response = requests.get(LATEST_RELEASE_API, timeout=TIMEOUT,
                                headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        raise UpdateError(t("app_update_check_failed", error=e)) from e

    wanted = ASSET_NAMES[_platform_key()]
    asset = next((a for a in data.get("assets", []) if a.get("name") == wanted), None)
    digest = (asset or {}).get("digest") or ""
    return Release(
        version=data.get("tag_name", "").lstrip("vV"),
        page_url=data.get("html_url") or RELEASES_PAGE,
        asset_url=asset.get("browser_download_url") if asset else None,
        asset_name=wanted if asset else None,
        sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else None,
    )


def is_newer(release: Release) -> bool:
    latest, current = parse_version(release.version), parse_version(APP_VERSION)
    return bool(latest and current and latest > current)


def check_for_update() -> Optional[Release]:
    """Return the latest release if it is newer than the running version."""
    release = fetch_latest()
    return release if is_newer(release) else None


def download(release: Release, progress: Callable[[float], None]) -> str:
    if not release.asset_url:
        raise UpdateError(t("err_update_asset"))
    folder = tempfile.mkdtemp(prefix="mmu-update-")
    path = os.path.join(folder, release.asset_name)
    sha = hashlib.sha256()
    try:
        with requests.get(release.asset_url, stream=True, timeout=TIMEOUT,
                          headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            done = 0
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if total:
                        progress(done / total)
    except (requests.RequestException, OSError) as e:
        raise UpdateError(t("err_download", error=e)) from e
    if release.sha256 and sha.hexdigest() != release.sha256:
        raise UpdateError(t("err_corrupt"))
    return path


def _spawn_helper(script: str) -> None:
    fd, path = tempfile.mkstemp(prefix="mmu-update-", suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    subprocess.Popen(["/bin/sh", path], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def _mac_app_bundle() -> Optional[str]:
    # sys.executable = .../Minecraft Mod Updater.app/Contents/MacOS/mod_updater
    bundle = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
    if bundle.endswith(".app") and os.path.isdir(os.path.join(bundle, "Contents", "MacOS")):
        return bundle
    return None


def _linux_app_dir() -> Optional[str]:
    # sys.executable = .../mod_updater/mod_updater, next to the _internal folder
    folder = os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(sys.executable) == "mod_updater" and os.path.isdir(os.path.join(folder, "_internal")):
        return folder
    return None


def install(path: str) -> None:
    """Start installing the downloaded update. The caller must exit the app right after."""
    pid = os.getpid()
    if sys.platform == "win32":
        # ShellExecute so Windows can ask for admin rights (the installer requires them).
        os.startfile(path, "open", "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS")
        return

    if sys.platform == "darwin":
        bundle = _mac_app_bundle()
        if not bundle or not os.access(os.path.dirname(bundle), os.W_OK):
            subprocess.Popen(["open", path])  # let the user drag the new app manually
            return
        q = shlex.quote
        _spawn_helper(f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
MNT=$(mktemp -d)
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" {q(path)} >/dev/null || {{ open {q(path)}; exit 1; }}
rm -rf {q(bundle + '.new')}
if cp -R "$MNT/Minecraft Mod Updater.app" {q(bundle + '.new')}; then
    rm -rf {q(bundle)} && mv {q(bundle + '.new')} {q(bundle)}
fi
hdiutil detach "$MNT" >/dev/null 2>&1
xattr -dr com.apple.quarantine {q(bundle)} 2>/dev/null
open {q(bundle)}
""")
        return

    folder = _linux_app_dir()
    if not folder or not os.access(os.path.dirname(folder), os.W_OK):
        raise UpdateError(t("err_update_location"))
    q = shlex.quote
    _spawn_helper(f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
TMP=$(mktemp -d)
if tar -xzf {q(path)} -C "$TMP" && [ -x "$TMP/MinecraftModUpdater/mod_updater/mod_updater" ]; then
    rm -rf {q(folder + '.new')}
    cp -R "$TMP/MinecraftModUpdater/mod_updater" {q(folder + '.new')} && rm -rf {q(folder)} && mv {q(folder + '.new')} {q(folder)}
fi
rm -rf "$TMP"
nohup {q(os.path.join(folder, 'mod_updater'))} >/dev/null 2>&1 &
""")
