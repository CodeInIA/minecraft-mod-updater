"""Colors, sizes and small helpers shared by the windows of the app."""

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from typing import List, Union

import customtkinter as ctk

import updater_core as core
from i18n import t

ACCENT = ("#2E9E5B", "#2E9E5B")
ACCENT_HOVER = ("#247C48", "#3DB56C")
DANGER = ("#C94141", "#B83A3A")
DANGER_HOVER = ("#A83535", "#D04848")
SIDEBAR_BG = ("#E6E9EC", "#1A1C1E")
CARD_BG = ("#F5F6F7", "#232629")
MUTED = ("#5F6670", "#9AA1A9")

SIDEBAR_MIN_WIDTH = 230
PROFILE_ROW_HEIGHT = 38
PROFILE_SLOT = PROFILE_ROW_HEIGHT + 4  # row + gap in the sidebar list
SIDEBAR_MAX_WIDTH = 380  # only reached by unusually wide 32-character names
# Space around a profile name in the sidebar: color square, paddings and the scrollbar
SIDEBAR_ROW_EXTRA = 100
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")  # [text](url) -> text in changelogs
TREE_ITEM_PADDING = 10  # left padding of rows in the mod table (see _style_tree)

# Display order of statuses in the table
STATUS_ORDER = [core.STATUS_MISSING_DEP, core.STATUS_UPDATE, core.STATUS_UP_TO_DATE, core.STATUS_PINNED,
                core.STATUS_IGNORED,
                core.STATUS_NOT_FOUND, core.STATUS_NO_COMPATIBLE, core.STATUS_INSTALLED, core.STATUS_UPDATED,
                core.STATUS_FAILED, core.STATUS_UNCHECKED]
# (light, dark) foreground per status
STATUS_COLORS = {
    core.STATUS_UPDATE: ("#B26A00", "#F0B44C"),
    core.STATUS_UP_TO_DATE: ("#2E7D4F", "#5FCB8A"),
    core.STATUS_NOT_FOUND: ("#7A8088", "#8A9099"),
    core.STATUS_NO_COMPATIBLE: ("#B0413E", "#E57373"),
    core.STATUS_UPDATED: ("#1F8A4C", "#7BE0A3"),
    core.STATUS_FAILED: ("#C62828", "#FF6B6B"),
    core.STATUS_MISSING_DEP: ("#6D28D9", "#B79CFF"),
    core.STATUS_INSTALLED: ("#1F8A4C", "#7BE0A3"),
    core.STATUS_IGNORED: ("#7A8088", "#8A9099"),
    core.STATUS_PINNED: ("#0E7490", "#5CC8E0"),
    core.STATUS_UNCHECKED: ("#5F6670", "#B4BAC1"),
}
CONTENT_ORDER = ["mods", "resourcepacks", "shaderpacks", "datapacks"]


def status_label(status: str) -> str:
    return t(f"status_{status}")


def row_status(mod: core.ModInfo) -> str:
    """Status column text, with the warnings of the mod (client/server, duplicated, incompatible)."""
    text = status_label(mod.status)
    for warning in mod_warnings(mod):
        text += "  ·  ⚠ " + warning
    return text


def mod_warnings(mod: core.ModInfo, detailed: bool = False) -> List[str]:
    """Short warnings for the status column, or full sentences for its tooltip."""
    warnings = []
    if mod.side_warning:
        warnings.append(t(f"side_{mod.side_warning}"))
    if mod.other_versions:
        warnings.append(t("problem_duplicate_long", files=", ".join(mod.other_versions)) if detailed
                        else t("problem_duplicate"))
    if mod.incompatible_with:
        warnings.append(t("problem_incompatible_long", mods=", ".join(mod.incompatible_with)) if detailed
                        else t("problem_incompatible"))
    return warnings


def content_label(content: str) -> str:
    return t(f"content_{content}")


def to_label(value: str) -> str:
    return t("auto") if not value or value == core.AUTO else value


def from_label(label: str) -> str:
    label = label.strip()
    return core.AUTO if not label or label == t("auto") else label


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


_WINDOW_ICONS: List[tk.PhotoImage] = []


def set_window_icon(window: Union[tk.Tk, tk.Toplevel]) -> None:
    try:
        if sys.platform == "win32":
            icon = resource_path("updater-logo.ico")
            if os.path.exists(icon):
                window.iconbitmap(icon)
                # CustomTkinter sets its own icon shortly after creating a window.
                window.after(250, lambda: window.iconbitmap(icon))
        elif sys.platform != "darwin":  # macOS takes the icon from the .app bundle
            png = resource_path("updater-logo.png")
            if os.path.exists(png):
                photo = tk.PhotoImage(file=png)
                _WINDOW_ICONS.append(photo)  # Tk drops images nothing in Python refers to
                window.iconphoto(True, photo)
    except tk.TclError:
        pass


def ui_font_family() -> str:
    return tkfont.nametofont("TkDefaultFont").actual("family")


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def pick(color) -> str:
    return color[1] if is_dark() else color[0]


def compact_number(n: int) -> str:
    """1234 -> 1.2K, 235049829 -> 235M."""
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            value = n / limit
            return (f"{value:.1f}".rstrip("0").rstrip(".") if value < 10 else f"{value:.0f}") + suffix
    return str(n)


def shorten_path(path: str, limit: int = 80) -> str:
    if len(path) <= limit:
        return path
    keep = (limit - 1) // 2
    return path[:keep] + "…" + path[-keep:]


def open_folder(path: str) -> None:
    """Open a folder (or a file, with its default app) in the system's file manager."""
    if not os.path.exists(path):
        return
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class Dialog(ctk.CTkToplevel):
    def __init__(self, master, title: str, width: int, height: int):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        set_window_icon(self)
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 3
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.after(10, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass
