"""Find Minecraft instances created by other launchers, to import them as profiles."""

import os
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

HOME = os.path.expanduser("~")
APPDATA = os.getenv("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
XDG_DATA = os.getenv("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
MAC_SUPPORT = os.path.join(HOME, "Library", "Application Support")


@dataclass
class Instance:
    launcher: str
    name: str
    mods_path: str
    mod_count: int


def _launcher_roots() -> Dict[str, List[str]]:
    """Folders where each launcher keeps its instances, for the current system."""
    if sys.platform == "win32":
        return {
            "Prism Launcher": [os.path.join(APPDATA, "PrismLauncher", "instances")],
            "Modrinth App": [os.path.join(APPDATA, "ModrinthApp", "profiles"),
                             os.path.join(APPDATA, "com.modrinth.theseus", "profiles")],
            "CurseForge": [os.path.join(HOME, "curseforge", "minecraft", "Instances")],
            "ATLauncher": [os.path.join(APPDATA, "ATLauncher", "instances")],
            "MultiMC": [os.path.join(HOME, "MultiMC", "instances")],
        }
    if sys.platform == "darwin":
        return {
            "Prism Launcher": [os.path.join(MAC_SUPPORT, "PrismLauncher", "instances")],
            "Modrinth App": [os.path.join(MAC_SUPPORT, "ModrinthApp", "profiles"),
                             os.path.join(MAC_SUPPORT, "com.modrinth.theseus", "profiles")],
            "CurseForge": [os.path.join(HOME, "Documents", "curseforge", "minecraft", "Instances")],
            "ATLauncher": [os.path.join(MAC_SUPPORT, "ATLauncher", "instances")],
            "MultiMC": [os.path.join(MAC_SUPPORT, "MultiMC", "instances")],
        }
    return {
        "Prism Launcher": [os.path.join(XDG_DATA, "PrismLauncher", "instances"),
                           os.path.join(HOME, ".var", "app", "org.prismlauncher.PrismLauncher",
                                        "data", "PrismLauncher", "instances")],
        "Modrinth App": [os.path.join(XDG_DATA, "ModrinthApp", "profiles"),
                         os.path.join(XDG_DATA, "com.modrinth.theseus", "profiles")],
        "CurseForge": [os.path.join(HOME, "curseforge", "minecraft", "Instances")],
        "ATLauncher": [os.path.join(XDG_DATA, "ATLauncher", "instances"),
                       os.path.join(HOME, ".atlauncher", "instances")],
        "MultiMC": [os.path.join(XDG_DATA, "multimc", "instances")],
    }


def _instance_name(launcher: str, folder: str) -> str:
    """Prism and MultiMC keep the display name in instance.cfg; the others use the folder name."""
    if launcher in ("Prism Launcher", "MultiMC"):
        try:
            with open(os.path.join(folder, "instance.cfg"), "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("name="):
                        return line.split("=", 1)[1].strip() or os.path.basename(folder)
        except OSError:
            pass
    return os.path.basename(folder)


def _mods_folder(launcher: str, folder: str) -> Optional[str]:
    if launcher in ("Prism Launcher", "MultiMC"):
        candidates = [os.path.join(folder, ".minecraft", "mods"), os.path.join(folder, "minecraft", "mods")]
    else:
        candidates = [os.path.join(folder, "mods")]
    return next((c for c in candidates if os.path.isdir(c)), None)


def find_instances(roots: Optional[Dict[str, Iterable[str]]] = None) -> List[Instance]:
    """Every instance with a mods folder in the known launcher locations."""
    found = []
    seen = set()
    for launcher, paths in (roots or _launcher_roots()).items():
        for root in paths:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root), key=str.lower):
                folder = os.path.join(root, entry)
                if not os.path.isdir(folder) or entry.startswith("."):
                    continue
                mods = _mods_folder(launcher, folder)
                if not mods or os.path.normcase(os.path.abspath(mods)) in seen:
                    continue
                seen.add(os.path.normcase(os.path.abspath(mods)))
                count = sum(1 for f in os.listdir(mods) if f.lower().endswith((".jar", ".jar.disabled")))
                found.append(Instance(launcher, _instance_name(launcher, folder), mods, count))
    return found
