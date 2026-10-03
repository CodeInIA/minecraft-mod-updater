"""Minecraft Mod Updater - graphical interface."""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

import app_updater
import i18n
import launchers
import updater_core as core
import mod_icons
from mod_icons import IconCache
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
STATUS_ORDER = [core.STATUS_MISSING_DEP, core.STATUS_UPDATE, core.STATUS_UP_TO_DATE, core.STATUS_IGNORED,
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
    core.STATUS_UNCHECKED: ("#5F6670", "#B4BAC1"),
}
CONTENT_ORDER = ["mods", "resourcepacks", "shaderpacks", "datapacks"]


def status_label(status: str) -> str:
    return t(f"status_{status}")


def row_status(mod: core.ModInfo) -> str:
    """Status column text, with the client/server warning when there is one."""
    text = status_label(mod.status)
    if mod.side_warning:
        text += "  ·  ⚠ " + t(f"side_{mod.side_warning}")
    return text


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


def set_window_icon(window: tk.Misc) -> None:
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
                window._icon_image = tk.PhotoImage(file=png)
                window.iconphoto(True, window._icon_image)
    except tk.TclError:
        pass


def ui_font_family() -> str:
    return tkfont.nametofont("TkDefaultFont").actual("family")


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def pick(color) -> str:
    return color[1] if is_dark() else color[0]


# --------------------------------------------------------------------------- #
# Dialogs
# --------------------------------------------------------------------------- #

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


class ProfileDialog(Dialog):
    """Create or edit a profile. `self.result` holds the profile dict on save."""

    def __init__(self, app: "App", profile: Optional[Dict] = None):
        super().__init__(app, t("edit_profile") if profile else t("new_profile"), 600, 540)
        self.app = app
        self.original = profile
        self.result: Optional[Dict] = None
        profile = profile or {
            "name": "",
            "path": core.DEFAULT_MINECRAFT_MODS if not app.config_data["profiles"] else "",
            "game_version": core.AUTO,
            "loader": core.AUTO,
            "color": core.next_profile_color(app.config_data["profiles"]),
            "content": core.CONTENT_MODS,
            "server": False,
        }
        self.color = profile.get("color") or core.PROFILE_COLORS[0]
        self.content = profile.get("content", core.CONTENT_MODS)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(0, minsize=110)  # room for the longest label

        ctk.CTkLabel(body, text=t("new_profile") if not self.original else t("edit_profile"),
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ctk.CTkLabel(body, text=t("name")).grid(row=1, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar(value=profile["name"][:core.MAX_PROFILE_NAME])
        self.name_var.trace_add("write", lambda *_: self._limit_name())
        ctk.CTkEntry(body, textvariable=self.name_var, placeholder_text=t("name_placeholder")).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=6)

        ctk.CTkLabel(body, text=t("content")).grid(row=2, column=0, sticky="w", pady=6)
        self.content_names = {content_label(c): c for c in CONTENT_ORDER}
        self.content_var = tk.StringVar(value=content_label(self.content))
        ctk.CTkOptionMenu(body, variable=self.content_var, values=list(self.content_names),
                          command=lambda _v: self._content_changed()).grid(row=2, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(body, text=t("folder")).grid(row=3, column=0, sticky="w", pady=6, padx=(0, 12))
        self.path_var = tk.StringVar(value=profile["path"])
        ctk.CTkEntry(body, textvariable=self.path_var).grid(row=3, column=1, sticky="ew", pady=6)
        ctk.CTkButton(body, text=t("browse"), width=96, command=self._browse).grid(row=3, column=2, padx=(8, 0), pady=6)

        ctk.CTkLabel(body, text="Minecraft").grid(row=4, column=0, sticky="w", pady=6)
        self.version_var = tk.StringVar(value=to_label(profile["game_version"]))
        ctk.CTkComboBox(body, variable=self.version_var, values=app.version_choices()).grid(
            row=4, column=1, sticky="ew", pady=6)
        self.detect_btn = ctk.CTkButton(body, text=t("detect"), width=96, fg_color="transparent", border_width=1,
                                        text_color=("gray10", "gray90"), command=self._detect)
        self.detect_btn.grid(row=4, column=2, padx=(8, 0), pady=6)

        ctk.CTkLabel(body, text=t("loader")).grid(row=5, column=0, sticky="w", pady=6)
        self.loader_var = tk.StringVar(value=to_label(profile["loader"]))
        self.loader_menu = ctk.CTkOptionMenu(body, variable=self.loader_var, values=app.loader_choices())
        self.loader_menu.grid(row=5, column=1, sticky="ew", pady=6)

        self.server_var = tk.BooleanVar(value=bool(profile.get("server")))
        ctk.CTkSwitch(body, text=t("server_profile"), variable=self.server_var, progress_color=ACCENT).grid(
            row=6, column=1, columnspan=2, sticky="w", pady=6)

        ctk.CTkLabel(body, text=t("color")).grid(row=7, column=0, sticky="w", pady=6)
        swatches = ctk.CTkFrame(body, fg_color="transparent")
        swatches.grid(row=7, column=1, columnspan=2, sticky="w", pady=6)
        self.swatches: Dict[str, ctk.CTkFrame] = {}
        for color in core.PROFILE_COLORS:
            swatch = ctk.CTkFrame(swatches, width=24, height=24, corner_radius=6, fg_color=color,
                                  border_width=2, cursor="hand2")
            swatch.pack(side="left", padx=(0, 6))
            swatch.bind("<Button-1>", lambda _e, c=color: self._set_color(c))
            self.swatches[color] = swatch
        self.custom_btn = ctk.CTkButton(swatches, text="…", width=32, height=24, corner_radius=6,
                                        fg_color="transparent", border_width=2,
                                        text_color=("gray10", "gray90"), command=self._pick_custom_color)
        self.custom_btn.pack(side="left")
        self._set_color(self.color)

        self.hint = ctk.CTkLabel(body, text=t("profile_hint"), text_color=MUTED, wraplength=540, justify="left")
        self.hint.grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self._content_changed(initial=True)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(0, 20))
        ctk.CTkButton(buttons, text=t("save"), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._save).pack(side="right")
        ctk.CTkButton(buttons, text=t("cancel"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        if os.path.isdir(self.path_var.get()):
            self.after(300, self._detect)

    def _content_changed(self, initial: bool = False):
        """Mods use a loader; resource packs, shaders and data packs do not. Suggest the matching folder."""
        new = self.content_names[self.content_var.get()]
        is_mods = new == core.CONTENT_MODS
        self.loader_menu.configure(state="normal" if is_mods else "disabled")
        if not is_mods:
            self.loader_var.set(t("auto"))
        if not initial and new != self.content:
            defaults = {os.path.normcase(core.content_folder(c)) for c in CONTENT_ORDER}
            if not self.path_var.get().strip() or os.path.normcase(self.path_var.get().strip()) in defaults:
                self.path_var.set(core.content_folder(new))
        self.content = new

    def _limit_name(self):
        name = self.name_var.get()
        if len(name) > core.MAX_PROFILE_NAME:
            self.name_var.set(name[:core.MAX_PROFILE_NAME])
            self.hint.configure(text=t("err_name_too_long", max=core.MAX_PROFILE_NAME), text_color=DANGER)

    def _set_color(self, color: str):
        self.color = color
        for value, swatch in self.swatches.items():
            swatch.configure(border_color=("gray10", "gray95") if value == color else value)
        custom = color not in self.swatches
        self.custom_btn.configure(fg_color=color if custom else "transparent",
                                  border_color=("gray10", "gray95") if custom else ("gray60", "gray40"))

    def _pick_custom_color(self):
        picked = colorchooser.askcolor(color=self.color, parent=self, title=t("custom_color"))[1]
        if picked:
            self._set_color(picked.upper())

    def _browse(self):
        initial = self.path_var.get() if os.path.isdir(self.path_var.get()) else os.path.dirname(core.DEFAULT_MINECRAFT_MODS)
        folder = filedialog.askdirectory(parent=self, initialdir=initial, title=t("select_mods_folder"))
        if folder:
            self.path_var.set(os.path.normpath(folder))
            self._detect()

    def _detect(self):
        path = self.path_var.get().strip()
        if not os.path.isdir(path):
            self.hint.configure(text=t("pick_existing_folder"), text_color=DANGER)
            return
        self.detect_btn.configure(state="disabled", text="…")
        self.hint.configure(text=t("analyzing"), text_color=MUTED)

        def done(result: Dict):
            if not self.winfo_exists():
                return
            self.detect_btn.configure(state="normal", text=t("detect"))
            if not result:
                self.hint.configure(text=t("no_mod_recognized"), text_color=DANGER)
                return
            self.hint.configure(text=t("detected_hint", version=result.get("game_version", "?"),
                                       loader=result.get("loader", "?")),
                                text_color=ACCENT)

        def failed(err: Exception):
            if self.winfo_exists():
                self.detect_btn.configure(state="normal", text=t("detect"))
                self.hint.configure(text=str(err), text_color=DANGER)

        content = self.content
        self.app.run_task(lambda: core.detect_target(self.app.client, path, content), done, failed)

    def _save(self):
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        game_version = self.version_var.get().strip()
        if not name:
            return self._error(t("err_name_required"))
        if len(name) > core.MAX_PROFILE_NAME:
            return self._error(t("err_name_too_long", max=core.MAX_PROFILE_NAME))
        others = [p["name"] for p in self.app.config_data["profiles"] if p is not self.original]
        if name in others:
            return self._error(t("err_name_exists", name=name))
        if not path:
            return self._error(t("err_folder_required"))
        if not game_version:
            return self._error(t("err_version_required"))
        self.result = {"name": name, "path": path, "game_version": from_label(game_version),
                       "loader": from_label(self.loader_var.get()), "color": self.color,
                       "content": self.content, "server": bool(self.server_var.get())}
        self.destroy()

    def _error(self, text: str):
        self.hint.configure(text=text, text_color=DANGER)


class ChangelogDialog(Dialog):
    """Notes of every version between the installed one and the one that would be installed."""

    def __init__(self, app: "App", mod: core.ModInfo, game_version: str, loaders: List[str]):
        super().__init__(app, t("changelog_title", mod=mod.display_name), 640, 520)
        ctk.CTkLabel(self, text=t("changelog_title", mod=mod.display_name),
                     font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(self, text=f"{mod.current_version}  →  {mod.latest_version}", text_color=MUTED,
                     anchor="w").pack(fill="x", padx=20)
        self.text = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(size=13))
        self.text.pack(fill="both", expand=True, padx=20, pady=12)
        self.text.insert("end", t("changelog_loading"))
        self.text.configure(state="disabled")
        ctk.CTkButton(self, text=t("close"), width=110, command=self.destroy).pack(pady=(0, 16))
        self.bind("<Escape>", lambda _e: self.destroy())
        app.run_task(lambda: core.changelog_entries(app.client, mod, game_version, loaders),
                     self._show, lambda e: self._set_text(t("changelog_failed", error=e)))

    def _set_text(self, text: str):
        if not self.winfo_exists():
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", text)
        self.text.configure(state="disabled")

    def _show(self, entries: List[Dict]):
        blocks = []
        for e in entries:
            kind = "" if e["type"] == "release" else f"  [{e['type']}]"
            notes = MARKDOWN_LINK.sub(r"\1", e["changelog"]) or t("changelog_empty")
            blocks.append(f"{e['version']}  ·  {e['date']}{kind}\n{'─' * 40}\n{notes}")
        self._set_text("\n\n".join(blocks) or t("changelog_empty"))


class BackupsDialog(Dialog):
    """List the backups of the current profile and undo the latest update."""

    def __init__(self, app: "App"):
        super().__init__(app, t("backups_title"), 620, 500)
        self.app = app
        self.folder = app.current_profile()["path"]
        ctk.CTkLabel(self, text=t("backups_title"), font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text=t("backups_hint"), text_color=MUTED, wraplength=570, justify="left",
                     anchor="w").pack(fill="x", padx=22)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=22, pady=12)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(0, 18))
        ctk.CTkButton(buttons, text=t("close"), width=110, command=self.destroy).pack(side="right")
        ctk.CTkButton(buttons, text=t("open_backups_folder"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"),
                      command=lambda: open_folder(core.backup_root(self.folder))).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        self._fill()

    def _fill(self):
        for child in self.list.winfo_children():
            child.destroy()
        backups = core.list_backups(self.folder)
        if not backups:
            ctk.CTkLabel(self.list, text=t("backups_none"), text_color=MUTED, wraplength=520,
                         justify="left").pack(padx=12, pady=16, anchor="w")
            return
        for index, backup in enumerate(backups):
            row = ctk.CTkFrame(self.list, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=6)
            when = backup.created.strftime("%Y-%m-%d %H:%M")
            names = ", ".join(e.get("title", "?") for e in backup.entries[:4])
            if len(backup.entries) > 4:
                names += ", …"
            text_box = ctk.CTkFrame(row, fg_color="transparent")
            text_box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(text_box, text=t("backup_item", date=when, n=len(backup.entries)),
                         font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(text_box, text=names, text_color=MUTED, anchor="w", wraplength=360,
                         justify="left").pack(fill="x")
            ctk.CTkButton(row, text=t("delete_backup"), width=80, fg_color="transparent", border_width=1,
                          border_color=DANGER, text_color=DANGER, hover_color=("#F6DADA", "#3A2222"),
                          command=lambda b=backup, w=when: self._delete(b, w)).pack(side="right", padx=(6, 0))
            # Updates are undone from the newest one backwards
            ctk.CTkButton(row, text=t("restore"), width=100, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                          state="normal" if index == 0 else "disabled",
                          command=lambda b=backup, w=when: self._restore(b, w)).pack(side="right")

    def _restore(self, backup: core.Backup, when: str):
        if self.app.busy or not messagebox.askyesno(
                t("backups_title"), t("restore_confirm", date=when, n=len(backup.entries)), parent=self):
            return
        errors = core.restore_backup(backup)
        self.app.show_local_mods(status=None if errors else t("restore_done", n=len(backup.entries)))
        if errors:
            messagebox.showwarning(t("backups_title"), t("restore_failed", details="\n".join(errors[:15])),
                                   parent=self)
        self._fill()

    def _delete(self, backup: core.Backup, when: str):
        if messagebox.askyesno(t("backups_title"), t("delete_backup_confirm", date=when), icon="warning",
                               parent=self):
            core.delete_backup(backup)
            self._fill()


class ImportDialog(Dialog):
    """Create profiles from the instances of other launchers."""

    def __init__(self, app: "App"):
        super().__init__(app, t("import_title"), 640, 520)
        self.app = app
        self.result: List[launchers.Instance] = []
        ctk.CTkLabel(self, text=t("import_title"), font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text=t("import_hint"), text_color=MUTED, wraplength=590, justify="left",
                     anchor="w").pack(fill="x", padx=22)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=22, pady=12)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(0, 18))
        self.import_btn = ctk.CTkButton(buttons, text=t("import_selected", n=0), fg_color=ACCENT,
                                        hover_color=ACCENT_HOVER, command=self._import)
        self.import_btn.pack(side="right")
        ctk.CTkButton(buttons, text=t("cancel"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())

        existing = {os.path.normcase(os.path.abspath(p["path"])) for p in app.config_data["profiles"]}
        self.choices: List[Tuple[tk.BooleanVar, launchers.Instance]] = []
        instances = launchers.find_instances()
        if not instances:
            ctk.CTkLabel(self.list, text=t("import_none"), text_color=MUTED, wraplength=540,
                         justify="left").pack(padx=12, pady=16, anchor="w")
        for inst in instances:
            added = os.path.normcase(os.path.abspath(inst.mods_path)) in existing
            var = tk.BooleanVar(value=not added)
            row = ctk.CTkFrame(self.list, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=5)
            label = t("instance_item", name=inst.name, launcher=inst.launcher, n=inst.mod_count)
            if added:
                label += f"  ({t('import_already')})"
            ctk.CTkCheckBox(row, text=label, variable=var, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            state="disabled" if added else "normal",
                            command=self._refresh_button).pack(anchor="w")
            ctk.CTkLabel(row, text=shorten_path(inst.mods_path, 70), text_color=MUTED,
                         font=ctk.CTkFont(size=11), anchor="w").pack(anchor="w", padx=(28, 0))
            if not added:
                self.choices.append((var, inst))
        self._refresh_button()

    def _refresh_button(self):
        n = sum(1 for var, _inst in self.choices if var.get())
        self.import_btn.configure(text=t("import_selected", n=n), state="normal" if n else "disabled")

    def _import(self):
        self.result = [inst for var, inst in self.choices if var.get()]
        self.destroy()


class SettingsDialog(Dialog):
    def __init__(self, app: "App"):
        super().__init__(app, t("settings"), 600, 570)
        self.app = app
        cfg = app.config_data

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(body, text=t("settings"), font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 14))

        self.backup_var = tk.BooleanVar(value=cfg["backup_mods"])
        ctk.CTkSwitch(body, text=t("opt_backup"), variable=self.backup_var,
                      progress_color=ACCENT).pack(anchor="w", pady=6)
        self.beta_var = tk.BooleanVar(value=cfg["allow_beta"])
        ctk.CTkSwitch(body, text=t("opt_beta"), variable=self.beta_var,
                      progress_color=ACCENT).pack(anchor="w", pady=6)
        self.snap_var = tk.BooleanVar(value=cfg["show_snapshots"])
        ctk.CTkSwitch(body, text=t("opt_snapshots"), variable=self.snap_var,
                      progress_color=ACCENT).pack(anchor="w", pady=6)

        ctk.CTkLabel(body, text=t("theme")).pack(anchor="w", pady=(14, 4))
        names = {"dark": t("theme_dark"), "light": t("theme_light"), "system": t("theme_system")}
        self.theme_names = {v: k for k, v in names.items()}
        self.theme = ctk.CTkSegmentedButton(body, values=list(names.values()), selected_color=ACCENT,
                                            selected_hover_color=ACCENT_HOVER)
        self.theme.set(names.get(cfg["appearance"], names["dark"]))
        self.theme.pack(anchor="w")

        ctk.CTkLabel(body, text=t("language")).pack(anchor="w", pady=(14, 4))
        languages = {i18n.SYSTEM: t("language_system"), **i18n.LANGUAGES}
        self.language_codes = {v: k for k, v in languages.items()}
        self.language_var = tk.StringVar(value=languages.get(cfg.get("language"), languages[i18n.SYSTEM]))
        ctk.CTkOptionMenu(body, variable=self.language_var, values=list(languages.values()),
                          width=220).pack(anchor="w")

        ctk.CTkLabel(body, text=t("app_updates_section")).pack(anchor="w", pady=(14, 4))
        self.app_auto_update_var = tk.BooleanVar(value=cfg.get("app_auto_update", True))
        ctk.CTkSwitch(body, text=t("opt_auto_update_app"), variable=self.app_auto_update_var,
                      progress_color=ACCENT).pack(anchor="w", pady=(0, 6))
        check_row = ctk.CTkFrame(body, fg_color="transparent")
        check_row.pack(anchor="w", fill="x")
        self.check_app_btn = ctk.CTkButton(check_row, text=t("check_app_update_now"), fg_color="transparent",
                                           border_width=1, text_color=("gray10", "gray90"),
                                           command=self._check_app_update)
        self.check_app_btn.pack(side="left")
        self.check_app_label = ctk.CTkLabel(check_row, text=f"v{core.APP_VERSION}", text_color=MUTED)
        self.check_app_label.pack(side="left", padx=10)

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(anchor="w", pady=(22, 0))
        ctk.CTkButton(actions, text=t("open_config_folder"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"),
                      command=lambda: open_folder(core.CONFIG_DIR)).pack(side="left")
        ctk.CTkButton(actions, text=t("reset_all"), fg_color=DANGER, hover_color=DANGER_HOVER,
                      command=self._reset).pack(side="left", padx=8)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(0, 20))
        ctk.CTkButton(buttons, text=t("save"), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._save).pack(side="right")
        ctk.CTkButton(buttons, text=t("cancel"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _save(self):
        cfg = self.app.config_data
        cfg["backup_mods"] = self.backup_var.get()
        cfg["allow_beta"] = self.beta_var.get()
        cfg["show_snapshots"] = self.snap_var.get()
        cfg["appearance"] = self.theme_names[self.theme.get()]
        language = self.language_codes[self.language_var.get()]
        language_changed = language != cfg.get("language")
        cfg["language"] = language
        cfg["app_auto_update"] = self.app_auto_update_var.get()
        core.save_config(cfg)
        self.destroy()
        if language_changed:
            self.app.rebuild_ui()
        else:
            self.app.apply_appearance()
            self.app.refresh_target_bar()

    def _check_app_update(self):
        self.check_app_btn.configure(state="disabled")
        self.check_app_label.configure(text=t("app_checking"), text_color=MUTED)

        def done(release: app_updater.Release):
            if not self.winfo_exists():
                return
            self.check_app_btn.configure(state="normal")
            if app_updater.is_newer(release):
                self.check_app_label.configure(text=t("app_update_available", version=release.version),
                                               text_color=ACCENT)
                self.app.banner_dismissed = False
                self.app._on_app_update_found(release, allow_auto=False)
            else:
                self.check_app_label.configure(text=t("app_up_to_date", version=core.APP_VERSION),
                                               text_color=MUTED)

        def failed(err: Exception):
            if self.winfo_exists():
                self.check_app_btn.configure(state="normal")
                self.check_app_label.configure(text=str(err), text_color=DANGER)

        self.app.run_task(app_updater.fetch_latest, done, failed)

    def _reset(self):
        if messagebox.askyesno(t("reset_title"), t("reset_confirm"),
                               icon="warning", parent=self):
            self.destroy()
            self.app.reset_all()


def shorten_path(path: str, limit: int = 80) -> str:
    if len(path) <= limit:
        return path
    keep = (limit - 1) // 2
    return path[:keep] + "…" + path[-keep:]


def open_folder(path: str) -> None:
    if not os.path.isdir(path):
        return
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class App(ctk.CTk):
    def __init__(self, offline: bool = False):
        """`offline` skips the startup network checks (used by tests and --self-test)."""
        self.config_data = core.load_config()
        i18n.set_language(self.config_data.get("language", i18n.SYSTEM))
        ctk.set_appearance_mode(self.config_data["appearance"])
        ctk.set_default_color_theme("green")
        super().__init__()

        self.title(core.APP_NAME)
        self.geometry("1120x700")
        self.minsize(900, 560)
        set_window_icon(self)

        self.client = core.ModrinthClient()
        self.offline = offline
        self.tags = core.load_tag_cache()
        self.mods: List[core.ModInfo] = []
        self.last_scan: Optional[core.ScanResult] = None
        self.app_release: Optional[app_updater.Release] = None
        self._list_token = 0  # identifies the latest request to list a profile's files
        self.icons = IconCache()
        self.banner_dismissed = False
        self.updating_app = False
        self.checked: set = set()
        self.busy = False
        self.sort_key = ("status", False)
        self._row_tags: Dict[str, List[str]] = {}
        self._hover_row: Optional[str] = None
        self._tooltip: Optional[tk.Toplevel] = None
        self._tree_font = tkfont.Font(size=10)
        self._queue: "queue.Queue" = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

        self.after(50, self._poll_queue)
        self.show_local_mods()
        if not offline:
            self.run_task(lambda: core.fetch_tags(self.client), self._on_tags, lambda _e: None)
            self.run_task(app_updater.check_for_update, self._on_app_update_found, lambda _e: None)

    # ----- background work ------------------------------------------------- #

    def run_task(self, work: Callable, on_done: Callable, on_error: Optional[Callable] = None):
        def target():
            try:
                result = work()
            except Exception as e:  # noqa: BLE001 - shown to the user
                self._queue.put((on_error or self._show_error, e))
                return
            self._queue.put((on_done, result))
        threading.Thread(target=target, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                fn, arg = self._queue.get_nowait()
                try:
                    fn(arg)
                except tk.TclError:
                    pass  # the window a result was meant for has been closed
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _progress_cb(self, fraction: float, message: str):
        self._queue.put((self._set_progress, (fraction, message)))

    def _set_progress(self, data):
        fraction, message = data
        self.progress.set(fraction)
        self.status_label.configure(text=message)

    def _show_error(self, err: Exception):
        self._set_busy(False)
        self.status_label.configure(text=t("error_prefix", error=err))
        messagebox.showerror(core.APP_NAME, str(err), parent=self)

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.check_btn, self.add_btn, self.import_btn, self.edit_btn, self.delete_btn,
                       self.backups_btn, self.version_box, self.loader_menu, self.settings_btn,
                       self.select_all_box):
            widget.configure(state=state)
        self._apply_content_state()
        if busy:
            self.update_btn.configure(state="disabled")
        else:
            self._refresh_update_button()

    # ----- layout ---------------------------------------------------------- #

    def _build_ui(self):
        self._build_sidebar()
        self._build_main()
        self.apply_appearance()
        self.refresh_profiles()
        self._refresh_update_button()

    def rebuild_ui(self):
        """Recreate every widget, e.g. after changing the language. Keeps the scan results."""
        i18n.set_language(self.config_data.get("language", i18n.SYSTEM))
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        if self.mods:
            self._fill_tree()
            self._update_summary()
            if self.last_scan:
                self._show_scan_status(self.last_scan)
        else:
            self.show_local_mods()
        if self.app_release and not self.banner_dismissed:
            self._show_update_banner()

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=SIDEBAR_MIN_WIDTH, corner_radius=0, fg_color=SIDEBAR_BG)
        self.sidebar = side
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(3, weight=1)
        side.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 18))
        logo_path = resource_path("updater-logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image
                self.logo = ctk.CTkImage(Image.open(logo_path), size=(40, 40))
                ctk.CTkLabel(brand, image=self.logo, text="").pack(side="left")
            except Exception as e:  # noqa: BLE001 - logo is optional
                self.logo_error = repr(e)
                print(f"Could not load logo: {e!r}", file=sys.stderr)
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left", padx=10)
        ctk.CTkLabel(titles, text="Mod Updater", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(titles, text=t("app_subtitle"), text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")

        ctk.CTkLabel(side, text=t("profiles"), text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=1, column=0, sticky="w", padx=20, pady=(4, 4))
        self.profile_list = ctk.CTkScrollableFrame(side, fg_color="transparent")
        self.profile_list.grid(row=3, column=0, sticky="nsew", padx=8)
        self.profile_container = ctk.CTkFrame(self.profile_list, fg_color="transparent", height=1)
        self.profile_container.pack(fill="x")
        self.profile_rows: List[ctk.CTkFrame] = []
        self._drag: Optional[Dict] = None
        self._drop_slot: Optional[ctk.CTkFrame] = None
        self._anim_job: Optional[str] = None

        profile_buttons = ctk.CTkFrame(side, fg_color="transparent")
        profile_buttons.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 6))
        profile_buttons.grid_columnconfigure(0, weight=1)
        self.add_btn = ctk.CTkButton(profile_buttons, text=t("new_profile_btn"), fg_color="transparent",
                                     border_width=1, text_color=("gray10", "gray90"), border_color=MUTED,
                                     command=self.add_profile)
        self.add_btn.grid(row=0, column=0, sticky="ew")
        self.import_btn = ctk.CTkButton(profile_buttons, text=t("import_btn"), fg_color="transparent",
                                        border_width=1, text_color=("gray10", "gray90"), border_color=MUTED,
                                        command=self.import_profiles)
        self.import_btn.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.settings_btn = ctk.CTkButton(side, text=t("settings_btn"), fg_color="transparent",
                                          text_color=("gray10", "gray90"), hover_color=("gray80", "gray25"),
                                          anchor="w", command=lambda: SettingsDialog(self))
        self.settings_btn.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 6))
        ctk.CTkLabel(side, text=f"v{core.APP_VERSION} · CodeInIA", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).grid(row=6, column=0, pady=(0, 14))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        # Banner shown when a new version of the app is available
        self.banner = ctk.CTkFrame(main, fg_color=("#DDF3E6", "#1E3A2A"), corner_radius=10)
        self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.banner.grid_columnconfigure(0, weight=1)
        self.banner_label = ctk.CTkLabel(self.banner, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.banner_label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)
        self.banner_notes_btn = ctk.CTkButton(self.banner, text=t("app_whats_new"), width=90, fg_color="transparent",
                                              border_width=1, text_color=("gray10", "gray90"),
                                              command=self._open_release_notes)
        self.banner_notes_btn.grid(row=0, column=1, padx=(0, 6))
        self.banner_later_btn = ctk.CTkButton(self.banner, text=t("app_update_later"), width=80, fg_color="transparent",
                                              text_color=("gray10", "gray90"), hover_color=("gray80", "gray25"),
                                              command=self._dismiss_update_banner)
        self.banner_later_btn.grid(row=0, column=2, padx=(0, 6))
        self.banner_update_btn = ctk.CTkButton(self.banner, text=t("app_update_now"), width=120, fg_color=ACCENT,
                                               hover_color=ACCENT_HOVER, command=self.start_app_update)
        self.banner_update_btn.grid(row=0, column=3, padx=(0, 10))
        self.banner.grid_remove()

        # Header with profile info and actions
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=1, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="w")
        self.profile_swatch = ctk.CTkFrame(title_row, width=20, height=20, corner_radius=6, fg_color=ACCENT)
        self.profile_swatch.pack(side="left", padx=(0, 10))
        self.profile_title = ctk.CTkLabel(title_row, text="", font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        self.profile_title.pack(side="left")
        self.profile_path = ctk.CTkLabel(header, text="", text_color=MUTED, anchor="w", cursor="hand2")
        self.profile_path.grid(row=1, column=0, sticky="w")
        self.profile_path.bind("<Button-1>", lambda _e: open_folder(self.current_profile()["path"])
                               if self.current_profile() else None)
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        ghost = dict(fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), width=90)
        ctk.CTkButton(actions, text=t("open"), command=lambda: open_folder(self.current_profile()["path"])
                      if self.current_profile() else None, **ghost).pack(side="left", padx=4)
        self.backups_btn = ctk.CTkButton(actions, text=t("backups_btn"), command=self.show_backups, **ghost)
        self.backups_btn.pack(side="left", padx=4)
        self.edit_btn = ctk.CTkButton(actions, text=t("edit"), command=self.edit_profile, **ghost)
        self.edit_btn.pack(side="left", padx=4)
        self.delete_btn = ctk.CTkButton(actions, text=t("delete"), command=self.delete_profile,
                                        fg_color="transparent", border_width=1, border_color=DANGER,
                                        text_color=DANGER, hover_color=("#F6DADA", "#3A2222"), width=90)
        self.delete_btn.pack(side="left", padx=(4, 0))

        # Target bar: Minecraft version, loader, check button
        bar = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        bar.grid(row=2, column=0, sticky="ew", pady=(16, 12))
        ctk.CTkLabel(bar, text="Minecraft", text_color=MUTED).pack(side="left", padx=(16, 8), pady=14)
        self.version_var = tk.StringVar()
        self.version_box = ctk.CTkComboBox(bar, variable=self.version_var, width=150,
                                           command=lambda _v: self._target_changed())
        self.version_box.pack(side="left")
        self.version_box.bind("<Return>", lambda _e: self._target_changed())
        self.version_box.bind("<FocusOut>", lambda _e: self._target_changed())
        ctk.CTkLabel(bar, text=t("loader"), text_color=MUTED).pack(side="left", padx=(18, 8))
        self.loader_var = tk.StringVar()
        self.loader_menu = ctk.CTkOptionMenu(bar, variable=self.loader_var, width=135,
                                             command=lambda _v: self._target_changed())
        self.loader_menu.pack(side="left")
        self.detected_label = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.detected_label.pack(side="left", padx=(14, 0))
        self.check_btn = ctk.CTkButton(bar, text=t("check_updates"), height=36,
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.check_updates)
        self.check_btn.pack(side="right", padx=14)

        # Summary + search
        summary = ctk.CTkFrame(main, fg_color="transparent")
        summary.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.summary_label = ctk.CTkLabel(summary, text=t("press_check"),
                                          text_color=MUTED, anchor="w")
        self.summary_label.pack(side="left")
        self.search_entry = ctk.CTkEntry(summary, placeholder_text=t("filter_placeholder"), width=220)
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._fill_tree())
        self.select_all_var = tk.BooleanVar(value=False)
        self.select_all_box = ctk.CTkCheckBox(summary, text=t("select_all"), variable=self.select_all_var,
                                              command=self._toggle_all, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                              checkbox_width=18, checkbox_height=18)
        self.select_all_box.pack(side="right", padx=(0, 16))

        # Mod table
        table = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        table.grid(row=4, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        # Column #0 shows checkbox + icon + name: it is the only Treeview column that can show an image.
        columns = ("current", "latest", "status")
        self.tree = ttk.Treeview(table, columns=columns, show="tree headings", style="Mods.Treeview",
                                 selectmode="none")
        self.tree.heading("#0", text=t("col_mod"), anchor="w", command=lambda: self._sort_by("name"))
        self.tree.column("#0", width=290, minwidth=200, stretch=True, anchor="w")
        headings = {"current": t("col_installed"), "latest": t("col_available"), "status": t("col_status")}
        widths = {"current": 160, "latest": 160, "status": 190}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="w", command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths[col], minwidth=40, stretch=False, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scroll = ctk.CTkScrollbar(table, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=4, pady=10)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda _e: self._set_link_hover(None))
        self.tree.bind("<Button-3>", self._on_tree_menu)
        if sys.platform == "darwin":
            self.tree.bind("<Button-2>", self._on_tree_menu)
            self.tree.bind("<Control-Button-1>", self._on_tree_menu)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)

        # Footer: progress and update button
        footer = ctk.CTkFrame(main, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(footer, text=t("ready"), text_color=MUTED, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress = ctk.CTkProgressBar(footer, progress_color=ACCENT, height=8)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(4, 0), padx=(0, 16))
        self.update_btn = ctk.CTkButton(footer, text=t("update_selected"), height=40, width=230,
                                        font=ctk.CTkFont(size=14, weight="bold"), fg_color=ACCENT,
                                        hover_color=ACCENT_HOVER, state="disabled", command=self.update_selected)
        self.update_btn.grid(row=0, column=1, rowspan=2, sticky="e")

    # ----- appearance ------------------------------------------------------ #

    def apply_appearance(self):
        ctk.set_appearance_mode(self.config_data["appearance"])
        self.after(50, self._style_tree)

    def _style_tree(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        family = ui_font_family()
        bg = pick(CARD_BG)
        fg = "#E8EAED" if is_dark() else "#1F2328"
        head_bg = "#2C3034" if is_dark() else "#E4E7EA"
        style.configure("Mods.Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=32,
                        borderwidth=0, relief="flat", font=(family, 10))
        style.layout("Mods.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Mods.Treeview", indent=0)
        style.layout("Mods.Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""})]})])
        style.configure("Mods.Treeview.Item", padding=(TREE_ITEM_PADDING, 0, 0, 0))
        self._tree_font = tkfont.Font(family=family, size=10)
        style.configure("Mods.Treeview.Heading", background=head_bg, foreground=fg, relief="flat",
                        borderwidth=0, font=(family, 10, "bold"), padding=(8, 6))
        style.map("Mods.Treeview.Heading", background=[("active", head_bg)])
        style.map("Mods.Treeview", background=[("selected", bg)], foreground=[("selected", fg)])
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=pick(color))
        self.tree.tag_configure("odd", background="#26292D" if is_dark() else "#F0F2F4")
        self.tree.tag_configure("hover", background="#30353A" if is_dark() else "#E3E7EB")
        self._refresh_row_images()

    # ----- profiles -------------------------------------------------------- #

    def current_profile(self) -> Optional[Dict]:
        for p in self.config_data["profiles"]:
            if p["name"] == self.config_data["current_profile"]:
                return p
        if self.config_data["profiles"]:
            self.config_data["current_profile"] = self.config_data["profiles"][0]["name"]
            return self.config_data["profiles"][0]
        return None

    def refresh_profiles(self):
        for row in self.profile_rows:
            row.destroy()
        if self._drop_slot:
            self._drop_slot.destroy()
            self._drop_slot = None
        self.profile_rows = []
        current = self.current_profile()
        for i, profile in enumerate(self.config_data["profiles"]):
            row = self._make_profile_row(profile, current is profile)
            row.slot_y = i * PROFILE_SLOT
            row.place(x=0, y=row.slot_y, relwidth=1)
            self.profile_rows.append(row)
        self.profile_container.configure(height=max(1, len(self.profile_rows) * PROFILE_SLOT))
        self.add_btn.configure(state="normal" if len(self.config_data["profiles"]) < core.MAX_PROFILES else "disabled")
        self._fit_sidebar_width()

        has_profile = current is not None
        if has_profile:
            self.profile_swatch.configure(fg_color=current.get("color") or ACCENT)
            self.profile_swatch.pack(side="left", padx=(0, 10), before=self.profile_title)
        else:
            self.profile_swatch.pack_forget()
        self.profile_title.configure(text=current["name"] if has_profile else t("no_profiles"))
        self.profile_path.configure(text=shorten_path(current["path"]) if has_profile else t("create_profile_hint"))
        for w in (self.edit_btn, self.delete_btn, self.check_btn, self.backups_btn):
            w.configure(state="normal" if has_profile else "disabled")
        self.refresh_target_bar()

    @staticmethod
    def _sidebar_name(name: str) -> str:
        """Name as shown in the sidebar: shortened with "…" if it is too long or too wide."""
        if len(name) > core.MAX_PROFILE_NAME:
            name = name[:core.MAX_PROFILE_NAME - 1] + "…"
        font = ctk.CTkFont(size=14, weight="bold")
        max_px = SIDEBAR_MAX_WIDTH - SIDEBAR_ROW_EXTRA
        while font.measure(name) > max_px and len(name) > 2:
            name = name.rstrip("…")[:-1] + "…"
        return name

    def _fit_sidebar_width(self):
        """Make the sidebar as wide as the longest profile name (never narrower than the default)."""
        # Widest style (the active profile). CTkFont and widget widths are both unscaled units.
        font = ctk.CTkFont(size=14, weight="bold")
        longest = max((font.measure(self._sidebar_name(p["name"])) for p in self.config_data["profiles"]),
                      default=0)
        width = min(SIDEBAR_MAX_WIDTH, max(SIDEBAR_MIN_WIDTH, int(longest) + SIDEBAR_ROW_EXTRA))
        if self.sidebar.cget("width") != width:
            self.sidebar.configure(width=width)

    def _make_profile_row(self, profile: Dict, active: bool) -> ctk.CTkFrame:
        """Sidebar entry: color square + name. Click selects it, dragging reorders the profiles."""
        idle_bg = ACCENT if active else "transparent"
        hover_bg = ACCENT_HOVER if active else ("gray80", "gray25")
        row = ctk.CTkFrame(self.profile_container, height=PROFILE_ROW_HEIGHT, corner_radius=8, fg_color=idle_bg)
        row.pack_propagate(False)
        swatch = ctk.CTkFrame(row, width=16, height=16, corner_radius=5, fg_color=profile.get("color") or ACCENT,
                              border_width=2 if active else 0, border_color=("white", "white"))
        swatch.pack(side="left", padx=(12, 10))
        label = ctk.CTkLabel(row, text=self._sidebar_name(profile["name"]), anchor="w",
                             text_color=("white", "white") if active else ("gray10", "gray90"),
                             font=ctk.CTkFont(size=14, weight="bold" if active else "normal"))
        label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        row.profile_name = profile["name"]
        row.idle_bg, row.hover_bg = idle_bg, hover_bg

        def leave(event):
            under = self.winfo_containing(event.x_root, event.y_root)
            if not (under and str(under).startswith(str(row))) and self._drag is None:
                row.configure(fg_color=idle_bg)

        for widget in (row, swatch, label):
            widget.bind("<Enter>", lambda _e: row.configure(fg_color=hover_bg))
            widget.bind("<Leave>", leave)
            widget.bind("<ButtonPress-1>", lambda e: self._profile_press(e, row))
            widget.bind("<B1-Motion>", lambda e: self._profile_drag(e, row))
            widget.bind("<ButtonRelease-1>", lambda e: self._profile_release(e, row))
        return row

    # ----- drag and drop of profiles ------------------------------------- #
    # The dragged row follows the mouse, a slot shows where it will land and the
    # other rows slide out of the way; on release the row glides into its slot.

    def _profile_press(self, event, row):
        if self.busy:
            return
        self._drag = {"row": row, "start": event.y_root, "pointer": event.y_root,
                      "offset": event.y_root - row.winfo_rooty(), "moved": False}

    def _profile_drag(self, event, row):
        drag = self._drag
        if not drag:
            return
        drag["pointer"] = event.y_root
        if not drag["moved"]:
            if abs(event.y_root - drag["start"]) < 6:  # small movements still count as a click
                return
            drag["moved"] = True
            self.configure(cursor="fleur")
            row.configure(fg_color=row.hover_bg, border_width=2, border_color=("#7A8088", "#C9CED4"))
            row.lift()
            self._drop_slot = ctk.CTkFrame(self.profile_container, height=PROFILE_ROW_HEIGHT, corner_radius=8,
                                           fg_color=("gray86", "gray17"), border_width=2,
                                           border_color=("gray70", "gray30"))
            self._drop_slot.place(x=0, y=row.slot_y, relwidth=1)
            self._drop_slot.lower()
        self._follow_pointer()
        self._start_profile_animation()

    def _follow_pointer(self):
        """Move the dragged row under the mouse and reorder the list when it crosses another row."""
        drag = self._drag
        row = drag["row"]
        count = len(self.profile_rows)
        y = drag["pointer"] - self.profile_container.winfo_rooty() - drag["offset"]
        y = max(0, min(y, (count - 1) * PROFILE_SLOT))
        row.slot_y = y
        row.place_configure(y=round(y))
        target = max(0, min(count - 1, round(y / PROFILE_SLOT)))
        current = self.profile_rows.index(row)
        if target != current:
            profiles = self.config_data["profiles"]
            profiles.insert(target, profiles.pop(current))
            self.profile_rows.insert(target, self.profile_rows.pop(current))
        self._drop_slot.place_configure(y=target * PROFILE_SLOT)

    def _autoscroll_profiles(self):
        canvas = getattr(self.profile_list, "_parent_canvas", None)
        if canvas is None:
            return
        # Only scroll when the list is taller than the visible area, and only towards hidden
        # content: Tk would otherwise move a list that fits completely out of place.
        first, last = canvas.yview()
        if first <= 0 and last >= 1:
            return
        top = canvas.winfo_rooty()
        bottom = top + canvas.winfo_height()
        if self._drag["pointer"] < top + 24 and first > 0:
            canvas.yview_scroll(-1, "units")
        elif self._drag["pointer"] > bottom - 24 and last < 1:
            canvas.yview_scroll(1, "units")

    def _start_profile_animation(self):
        if self._anim_job is None:
            self._anim_job = self.after(15, self._animate_profiles)

    def _animate_profiles(self):
        self._anim_job = None
        dragging = bool(self._drag and self._drag["moved"])
        try:
            if dragging:
                self._autoscroll_profiles()
                self._follow_pointer()
            moving = False
            for index, row in enumerate(self.profile_rows):
                if dragging and row is self._drag["row"]:
                    continue
                target = index * PROFILE_SLOT
                if abs(row.slot_y - target) > 0.5:
                    row.slot_y += (target - row.slot_y) * 0.3  # ease towards the slot
                    moving = True
                else:
                    row.slot_y = target
                row.place_configure(y=round(row.slot_y))
        except tk.TclError:  # the rows were rebuilt meanwhile
            return
        if moving or dragging:
            self._start_profile_animation()

    def _profile_release(self, event, row):
        drag, self._drag = self._drag, None
        self.configure(cursor="")
        if not drag:
            return
        if drag["moved"]:
            row.configure(fg_color=row.idle_bg, border_width=0)
            if self._drop_slot:
                self._drop_slot.destroy()
                self._drop_slot = None
            core.save_config(self.config_data)
            self._start_profile_animation()  # glide into the slot
        else:
            self.select_profile(row.profile_name)

    def move_profile(self, old_index: int, new_index: int, save: bool = True):
        """Move a profile from one position to another (the rows slide to their new places)."""
        profiles = self.config_data["profiles"]
        profiles.insert(new_index, profiles.pop(old_index))
        self.profile_rows.insert(new_index, self.profile_rows.pop(old_index))
        self._start_profile_animation()
        if save:
            core.save_config(self.config_data)

    def refresh_target_bar(self):
        profile = self.current_profile()
        self.version_box.configure(values=self.version_choices())
        self.loader_menu.configure(values=self.loader_choices())
        if profile:
            self.version_var.set(to_label(profile.get("game_version")))
            self.loader_var.set(to_label(profile.get("loader")))
        self._apply_content_state()

    def _profile_content(self) -> str:
        profile = self.current_profile()
        return profile.get("content", core.CONTENT_MODS) if profile else core.CONTENT_MODS

    def _apply_content_state(self):
        """Resource packs, shaders and data packs have no mod loader to choose."""
        if self._profile_content() != core.CONTENT_MODS:
            self.loader_var.set("—")
            self.loader_menu.configure(state="disabled")
        elif not self.busy:
            self.loader_menu.configure(state="normal")

    def select_profile(self, name: str):
        if self.busy or name == self.config_data["current_profile"]:
            return
        self.config_data["current_profile"] = name
        core.save_config(self.config_data)
        self.refresh_profiles()
        self.show_local_mods()

    def add_profile(self):
        dialog = ProfileDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.config_data["profiles"].append(dialog.result)
            self.config_data["current_profile"] = dialog.result["name"]
            core.save_config(self.config_data)
            self.refresh_profiles()
            self.show_local_mods()

    def edit_profile(self):
        profile = self.current_profile()
        if not profile:
            return
        dialog = ProfileDialog(self, profile)
        self.wait_window(dialog)
        if dialog.result:
            profile.update(dialog.result)
            self.config_data["current_profile"] = profile["name"]
            core.save_config(self.config_data)
            self.refresh_profiles()
            self.show_local_mods()

    def import_profiles(self):
        dialog = ImportDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        names = {p["name"] for p in self.config_data["profiles"]}
        added = 0
        for inst in dialog.result:
            if len(self.config_data["profiles"]) >= core.MAX_PROFILES:
                break
            base = inst.name[:core.MAX_PROFILE_NAME]
            name, n = base, 2
            while name in names:  # keep names unique
                suffix = f" ({n})"
                name = base[:core.MAX_PROFILE_NAME - len(suffix)] + suffix
                n += 1
            names.add(name)
            self.config_data["profiles"].append({
                "name": name, "path": inst.mods_path, "game_version": core.AUTO, "loader": core.AUTO,
                "color": core.next_profile_color(self.config_data["profiles"]), "content": core.CONTENT_MODS,
                "server": False, "ignored": []})
            added += 1
        if added:
            self.config_data["current_profile"] = self.config_data["profiles"][-1]["name"]
            core.save_config(self.config_data)
            self.refresh_profiles()
            self.show_local_mods(status=t("import_done", n=added))

    def show_backups(self):
        if self.current_profile() and not self.busy:
            self.wait_window(BackupsDialog(self))

    def delete_profile(self):
        profile = self.current_profile()
        if not profile:
            return
        if not messagebox.askyesno(t("delete_profile_title"), t("delete_profile_confirm", name=profile["name"]),
                                   parent=self):
            return
        self.config_data["profiles"].remove(profile)
        self.config_data["current_profile"] = (self.config_data["profiles"][0]["name"]
                                               if self.config_data["profiles"] else "")
        core.save_config(self.config_data)
        self.refresh_profiles()
        self.show_local_mods()

    def reset_all(self):
        self.config_data = core.reset_config()
        core.save_config(self.config_data)
        self.mods = []
        self.rebuild_ui()

    # ----- updates of this app -------------------------------------------- #

    def _on_app_update_found(self, release: Optional[app_updater.Release], allow_auto: bool = True):
        if not release or self.updating_app:
            return
        self.app_release = release
        if allow_auto and self.config_data.get("app_auto_update") and app_updater.is_frozen():
            self.start_app_update()
        else:
            self._show_update_banner()

    def _show_update_banner(self, text: Optional[str] = None, busy: bool = False):
        self.banner_label.configure(text=text or t("app_update_available", version=self.app_release.version))
        for btn in (self.banner_update_btn, self.banner_later_btn):
            btn.configure(state="disabled" if busy else "normal")
        self.banner.grid()

    def _dismiss_update_banner(self):
        self.banner_dismissed = True
        self.banner.grid_remove()

    def _open_release_notes(self):
        if self.app_release:
            webbrowser.open(self.app_release.page_url)

    def start_app_update(self):
        release = self.app_release
        if not release or self.updating_app:
            return
        if not app_updater.is_frozen():
            # Running from source: there is no installed app to replace.
            webbrowser.open(release.page_url)
            return
        self.updating_app = True
        self._show_update_banner(t("app_downloading", version=release.version, percent=0), busy=True)

        def progress(fraction: float):
            self._queue.put((lambda f: self.banner_label.configure(
                text=t("app_downloading", version=release.version, percent=int(f * 100))), fraction))

        self.run_task(lambda: app_updater.download(release, progress), self._on_app_downloaded,
                      self._on_app_update_failed)

    def _on_app_downloaded(self, path: str):
        if self.busy:
            # Do not close the app in the middle of a mod scan or update.
            self.after(1000, lambda: self._on_app_downloaded(path))
            return
        self.banner_label.configure(text=t("app_installing"))
        self.update_idletasks()
        try:
            app_updater.install(path)
        except Exception as e:  # noqa: BLE001 - shown to the user
            self._on_app_update_failed(e)
            return
        self.after(1500, self.destroy)

    def _on_app_update_failed(self, err: Exception):
        self.updating_app = False
        self._show_update_banner(t("app_update_failed", error=err))

    # ----- target (Minecraft version / loader) ----------------------------- #

    def _on_tags(self, tags: Dict):
        self.tags = tags
        self.refresh_target_bar()

    def version_choices(self) -> List[str]:
        versions = self.tags.get("game_versions", [])
        releases = [v["version"] for v in versions if v.get("version_type") == "release"]
        if not self.config_data.get("show_snapshots"):
            return [t("auto")] + releases
        others = [v["version"] for v in versions if v.get("version_type") != "release"][:40]
        return [t("auto")] + others + releases

    def loader_choices(self) -> List[str]:
        return [t("auto")] + (self.tags.get("loaders") or core.sort_loaders(core.PREFERRED_LOADERS))

    def _target_changed(self):
        profile = self.current_profile()
        if not profile:
            return
        new_version = from_label(self.version_var.get())
        new_loader = (from_label(self.loader_var.get()) if self._profile_content() == core.CONTENT_MODS
                      else profile.get("loader", core.AUTO))
        if (new_version, new_loader) != (profile.get("game_version"), profile.get("loader")):
            profile["game_version"] = new_version
            profile["loader"] = new_loader
            core.save_config(self.config_data)
            if self.last_scan:
                self.show_local_mods(status=t("target_changed"))

    # ----- checking & updating -------------------------------------------- #

    def check_updates(self):
        profile = self.current_profile()
        if not profile or self.busy:
            return
        self._target_changed()
        path = profile["path"]
        if not os.path.isdir(path):
            messagebox.showerror(core.APP_NAME, t("folder_missing", path=path), parent=self)
            return
        game_version = profile["game_version"]
        known = {v["version"] for v in self.tags.get("game_versions", [])}
        if known and game_version != core.AUTO and game_version not in known:
            if not messagebox.askyesno(core.APP_NAME, t("unknown_version", version=game_version), parent=self):
                return

        self._clear_results()
        self._list_token += 1  # a listing still in progress must not replace the scan results
        self._set_busy(True)
        allow_beta = self.config_data["allow_beta"]
        content = profile.get("content", core.CONTENT_MODS)
        ignored = list(profile.get("ignored", []))
        server = bool(profile.get("server"))
        self.run_task(
            lambda: core.scan_mods(self.client, path, game_version, profile["loader"], allow_beta,
                                   self._progress_cb, content=content, ignored=ignored, server=server),
            self._on_scan_done)

    def _on_scan_done(self, result: core.ScanResult):
        self._set_busy(False)
        self.last_scan = result
        self.mods = result.mods
        self.checked = {m.path for m in self.mods if m.actionable}
        self._fill_tree()
        self._update_summary()
        self._show_scan_status(result)
        missing = self.icons.missing(m.icon_url for m in self.mods)
        if missing:
            self.run_task(lambda: self.icons.download(missing), lambda _r: self._refresh_row_images(),
                          lambda _e: None)

    def _show_scan_status(self, result: core.ScanResult):
        mods = result.mods
        is_mods = result.content == core.CONTENT_MODS
        if result.detected:
            target = (f"→ {result.game_version or '?'} · {result.loader or '?'}" if is_mods
                      else f"→ {result.game_version or '?'}")
            self.detected_label.configure(text=target,
                                          text_color=ACCENT if result.game_version and result.loaders else DANGER)
        if not mods:
            self.status_label.configure(text=t("no_jars") if is_mods else t("no_files"))
        elif not result.game_version or not result.loaders:
            self.status_label.configure(text=t("detect_failed"))
        else:
            pending = len(self.checked)
            self.status_label.configure(text=t("updates_available", n=pending) if pending
                                        else t("all_up_to_date"))

    def update_selected(self):
        profile = self.current_profile()
        selected = [m for m in self.mods if m.path in self.checked and m.actionable]
        if not profile or not selected or self.busy:
            return
        self._set_busy(True)
        self.progress.set(0)
        backup = self.config_data["backup_mods"]
        self.run_task(lambda: core.update_mods(self.client, selected, profile["path"], backup, self._progress_cb),
                      lambda backup_dir: self._on_update_done(selected, backup_dir))

    def _on_update_done(self, mods: List[core.ModInfo], backup_dir: Optional[str]):
        self._set_busy(False)
        self.last_scan = None
        self.checked = set()
        self._fill_tree()
        self._update_summary()
        ok = sum(1 for m in mods if m.status in (core.STATUS_UPDATED, core.STATUS_INSTALLED))
        installed = sum(1 for m in mods if m.status == core.STATUS_INSTALLED)
        failed = [m for m in mods if m.status == core.STATUS_FAILED]
        text = t("updated_count", n=ok - installed)
        if installed:
            text += " " + t("installed_count", n=installed)
        if failed:
            text += " " + t("failed_count", n=len(failed))
        if backup_dir and ok:
            text += " " + t("backup_saved")
        self.status_label.configure(text=text)
        if failed:
            details = "\n".join(f"• {m.display_name}: {m.error}" for m in failed[:15])
            messagebox.showwarning(core.APP_NAME, t("some_failed", details=details), parent=self)
        elif backup_dir and ok and messagebox.askyesno(
                core.APP_NAME, t("updated_backup_prompt", n=ok, path=backup_dir), parent=self):
            open_folder(backup_dir)

    # ----- files of the profile before checking ------------------------------ #

    def show_local_mods(self, status: Optional[str] = None):
        """List the files of the current profile right away, without going online.

        Names, icons and versions come from earlier checks; files never seen are
        then identified on Modrinth. The status says they have not been checked
        for updates yet. "Check for updates" replaces this list.
        """
        self._clear_results()
        self._list_token += 1
        token = self._list_token
        profile = self.current_profile()
        if not profile:
            return
        path, content = profile["path"], profile.get("content", core.CONTENT_MODS)
        if not os.path.isdir(path):
            self.status_label.configure(text=t("folder_missing", path=path).replace("\n", " "))
            return
        self.run_task(lambda: core.list_local_mods(path, content),
                      lambda mods: self._on_local_mods(token, mods, content, status), lambda _e: None)

    def _on_local_mods(self, token: int, mods: List[core.ModInfo], content: str, status: Optional[str]):
        if token != self._list_token or self.busy or self.last_scan:
            return  # another profile was selected, or a check started meanwhile
        self.mods = mods
        self._fill_tree()
        self._update_summary()
        if status:
            self.status_label.configure(text=status)
        elif mods:
            self.status_label.configure(text=t("local_listed", n=len(mods)))
        else:
            self.status_label.configure(text=t("no_jars") if content == core.CONTENT_MODS else t("no_files"))
        self._load_local_icons(mods)
        if not self.offline and any(m.sha512 and not m.current for m in mods):
            # First time these files are seen: ask Modrinth what they are (not whether they are outdated)
            self.run_task(lambda: core.identify_local_mods(self.client, mods),
                          lambda found: self._on_local_identified(token, found), lambda _e: None)

    def _on_local_identified(self, token: int, mods: List[core.ModInfo]):
        if token != self._list_token or self.busy or self.last_scan:
            return
        self.mods = mods
        self._fill_tree()
        self._load_local_icons(mods)

    def _load_local_icons(self, mods: List[core.ModInfo]):
        missing = self.icons.missing(m.icon_url for m in mods)
        if missing:
            self.run_task(lambda: self.icons.download(missing), lambda _r: self._refresh_row_images(),
                          lambda _e: None)

    # ----- table ----------------------------------------------------------- #

    def _clear_results(self):
        self.mods = []
        self.last_scan = None
        self.checked = set()
        self.tree.delete(*self.tree.get_children())
        self.detected_label.configure(text="")
        self.progress.set(0)
        self.summary_label.configure(text=t("press_check"))
        self.status_label.configure(text=t("ready"))
        self._refresh_update_button()

    def _visible_mods(self) -> List[core.ModInfo]:
        query = self.search_entry.get().strip().lower()
        mods = [m for m in self.mods if not query or query in m.display_name.lower() or query in m.filename.lower()]
        key, reverse = self.sort_key
        order = STATUS_ORDER
        keyfn = {
            "name": lambda m: m.display_name.lower(),
            "current": lambda m: m.current_version.lower(),
            "latest": lambda m: m.latest_version.lower(),
            "status": lambda m: (order.index(m.status), m.display_name.lower()),
        }[key]
        return sorted(mods, key=keyfn, reverse=reverse)

    def _row_image(self, mod: core.ModInfo):
        check = (mod.path in self.checked) if mod.actionable else None
        return self.icons.row_image(mod.icon_url, check, is_dark())

    def _refresh_row_images(self):
        mods = {m.path: m for m in self.mods}
        for iid in self.tree.get_children():
            if iid in mods:
                self.tree.item(iid, image=self._row_image(mods[iid]))

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._row_tags = {}
        self._hover_row = None
        for i, mod in enumerate(self._visible_mods()):
            name = mod.display_name + (f"  {t('disabled_suffix')}" if mod.disabled else "")
            tags = [mod.status] + (["odd"] if i % 2 else [])
            self._row_tags[mod.path] = tags
            installed = (t("needed_by", names=", ".join(mod.required_by[:3]) + ("…" if len(mod.required_by) > 3 else ""))
                         if mod.status == core.STATUS_MISSING_DEP else mod.current_version)
            self.tree.insert("", "end", iid=mod.path, text="  " + name, image=self._row_image(mod),
                             values=(installed, mod.latest_version, row_status(mod)), tags=tags)
        self._refresh_update_button()

    def _update_summary(self):
        counts = {s: 0 for s in STATUS_ORDER}
        for m in self.mods:
            counts[m.status] = counts.get(m.status, 0) + 1
        if self.mods and all(m.status == core.STATUS_UNCHECKED for m in self.mods):
            self.summary_label.configure(text=t("sum_mods", n=len(self.mods)) + "  ·  " + t("press_check"))
            return
        parts = [t("sum_mods", n=len([m for m in self.mods if m.status != core.STATUS_MISSING_DEP]))]
        if counts[core.STATUS_MISSING_DEP]:
            parts.append(t("sum_missing", n=counts[core.STATUS_MISSING_DEP]))
        if counts[core.STATUS_UPDATE]:
            parts.append(t("sum_update", n=counts[core.STATUS_UPDATE]))
        if counts[core.STATUS_UPDATED]:
            parts.append(t("sum_updated", n=counts[core.STATUS_UPDATED]))
        parts.append(t("sum_up_to_date", n=counts[core.STATUS_UP_TO_DATE]))
        if counts[core.STATUS_NO_COMPATIBLE]:
            parts.append(t("sum_no_compatible", n=counts[core.STATUS_NO_COMPATIBLE]))
        if counts[core.STATUS_NOT_FOUND]:
            parts.append(t("sum_not_found", n=counts[core.STATUS_NOT_FOUND]))
        if counts[core.STATUS_IGNORED]:
            parts.append(t("sum_ignored", n=counts[core.STATUS_IGNORED]))
        sides = sum(1 for m in self.mods if m.side_warning)
        if sides:
            parts.append(t("sum_side", n=sides))
        self.summary_label.configure(text="  ·  ".join(parts))

    def _refresh_update_button(self):
        n = sum(1 for m in self.mods if m.path in self.checked and m.actionable)
        updatable = [m for m in self.mods if m.actionable]
        self.select_all_var.set(bool(updatable) and all(m.path in self.checked for m in updatable))
        self.select_all_box.configure(state="normal" if updatable and not self.busy else "disabled")
        enabled = bool(n) and not self.busy
        self.update_btn.configure(text=t("update_selected_n", n=n) if n else t("update_selected"),
                                  state="normal" if enabled else "disabled",
                                  fg_color=ACCENT if enabled else ("gray75", "gray30"))

    def _hit_area(self, event) -> Tuple[Optional[core.ModInfo], str]:
        """Which part of a row is under the mouse: 'checkbox', 'link' (icon + name) or 'row'."""
        if self.tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            return None, ""
        iid = self.tree.identify_row(event.y)
        mod = next((m for m in self.mods if m.path == iid), None)
        if not mod:
            return None, ""
        if self.tree.identify_column(event.x) != "#0":
            return mod, "row"
        bbox = self.tree.bbox(iid, "#0")
        x = event.x - (bbox[0] if bbox else 0) - TREE_ITEM_PADDING
        if x < mod_icons.BOX + mod_icons.GAP // 2:
            return mod, "checkbox"
        name_end = mod_icons.BOX + mod_icons.GAP + mod_icons.ICON + self._tree_font.measure(self.tree.item(iid, "text"))
        return mod, "link" if x <= name_end else "row"

    def _on_tree_click(self, event):
        mod, area = self._hit_area(event)
        if area == "link" and mod.page_url:
            webbrowser.open(mod.page_url)
            return
        if self.busy or not mod or not mod.actionable:
            return
        iid = mod.path
        self.checked.symmetric_difference_update({iid})
        self.tree.item(iid, image=self._row_image(mod))
        self._refresh_update_button()

    def _toggle_all(self):
        if self.busy:
            return
        updatable = {m.path for m in self._visible_mods() if m.actionable}
        if updatable and updatable <= self.checked:
            self.checked -= updatable
        else:
            self.checked |= updatable
        self._refresh_row_images()
        self._refresh_update_button()

    def _on_tree_menu(self, event):
        """Right-click menu of a mod: changelog, Modrinth page, (don't) update it, show the file."""
        iid = self.tree.identify_row(event.y)
        mod = next((m for m in self.mods if m.path == iid), None)
        if not mod:
            return
        menu = tk.Menu(self, tearoff=False)
        if mod.latest and self.last_scan:
            menu.add_command(label=t("menu_changelog"), command=lambda: self.show_changelog(mod))
        if mod.page_url:
            menu.add_command(label=t("open_in_modrinth"), command=lambda: webbrowser.open(mod.page_url))
        if mod.current and mod.project_id and not self.busy and self.last_scan:
            ignored = mod.status == core.STATUS_IGNORED
            menu.add_command(label=t("menu_unignore") if ignored else t("menu_ignore"),
                             command=lambda: self.set_ignored(mod, not ignored))
        if os.path.exists(mod.path):
            menu.add_command(label=t("menu_show_file"), command=lambda: open_folder(os.path.dirname(mod.path)))
        if menu.index("end") is not None:
            menu.tk_popup(event.x_root, event.y_root)

    def _on_tree_double_click(self, event):
        mod, area = self._hit_area(event)
        if mod and area == "row" and mod.latest and self.last_scan:
            self.show_changelog(mod)

    def show_changelog(self, mod: core.ModInfo):
        scan = self.last_scan
        ChangelogDialog(self, mod, scan.game_version if scan else "", scan.loaders if scan else [])

    def set_ignored(self, mod: core.ModInfo, ignored: bool):
        """Stop (or resume) offering updates for a mod in the current profile."""
        profile = self.current_profile()
        if not profile or not mod.project_id:
            return
        listed = profile.setdefault("ignored", [])
        if ignored and mod.project_id not in listed:
            listed.append(mod.project_id)
        elif not ignored and mod.project_id in listed:
            listed.remove(mod.project_id)
        core.save_config(self.config_data)
        scan = self.last_scan
        if ignored:
            mod.status = core.STATUS_IGNORED
            self.checked.discard(mod.path)
        else:
            mod.status = core.determine_status(mod, (scan.game_version or "") if scan else "",
                                               scan.loaders if scan else [])
            if mod.actionable:
                self.checked.add(mod.path)
        self._fill_tree()
        self._update_summary()

    def _sort_by(self, column: str):
        key, reverse = self.sort_key
        self.sort_key = (column, not reverse if key == column else False)
        self._fill_tree()

    def _set_link_hover(self, event):
        """Hand cursor and an "Open in Modrinth" tooltip while the mouse is over a mod name."""
        if event is None:
            self.tree.configure(cursor="")
            if self._tooltip and self._tooltip.winfo_exists():
                self._tooltip.withdraw()
            return
        if not self._tooltip or not self._tooltip.winfo_exists():
            self._tooltip = tk.Toplevel(self)
            self._tooltip.overrideredirect(True)
            self._tooltip.attributes("-topmost", True)
            self._tooltip_label = tk.Label(self._tooltip, padx=8, pady=3, font=(ui_font_family(), 9))
            self._tooltip_label.pack()
        self._tooltip_label.configure(text=t("open_in_modrinth") + "  ↗", bg=pick(SIDEBAR_BG),
                                      fg="#E8EAED" if is_dark() else "#1F2328")
        self._tooltip.geometry(f"+{event.x_root + 14}+{event.y_root + 18}")
        self._tooltip.deiconify()
        self.tree.configure(cursor="hand2")

    def _on_tree_motion(self, event):
        mod, area = self._hit_area(event)
        self._set_link_hover(event if area == "link" and mod.page_url else None)
        row = self.tree.identify_row(event.y)
        previous = getattr(self, "_hover_row", None)
        if row == previous:
            return
        if previous and self.tree.exists(previous):
            self.tree.item(previous, tags=self._row_tags.get(previous, []))
        if row:
            self.tree.item(row, tags=[t for t in self._row_tags.get(row, []) if t != "odd"] + ["hover"])
        self._hover_row = row


def self_test() -> int:
    """Check that the packaged app has everything it needs. Used by the release workflow."""
    errors = []
    for name in ("updater-logo.png", "updater-logo.ico"):
        if not os.path.exists(resource_path(name)):
            errors.append(f"missing resource: {name}")
    for lang in i18n.LANGUAGES:
        missing = set(i18n.STRINGS["en"]) - set(i18n.STRINGS[lang])
        if missing:
            errors.append(f"{lang}: missing translations {sorted(missing)[:5]}")
    try:
        app = App(offline=True)
        app.update()
        if getattr(app, "logo_error", None):
            errors.append(f"logo: {app.logo_error}")
        app.icons.row_image("", True, True)  # Pillow drawing + ImageTk
        app.destroy()
    except Exception as e:  # noqa: BLE001 - reported below
        errors.append(f"window: {e!r}")
    report = "\n".join(errors) if errors else f"self-test OK (version {core.APP_VERSION})"
    print(report)
    out = os.environ.get("MMU_SELF_TEST_OUTPUT")
    if out:  # GUI builds have no console, so the workflow reads the result from a file
        with open(out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    return 1 if errors else 0


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
