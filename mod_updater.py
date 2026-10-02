"""Minecraft Mod Updater - graphical interface."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

import app_updater
import i18n
import updater_core as core
from i18n import t

ACCENT = ("#2E9E5B", "#2E9E5B")
ACCENT_HOVER = ("#247C48", "#3DB56C")
DANGER = ("#C94141", "#B83A3A")
DANGER_HOVER = ("#A83535", "#D04848")
SIDEBAR_BG = ("#E6E9EC", "#1A1C1E")
CARD_BG = ("#F5F6F7", "#232629")
MUTED = ("#5F6670", "#9AA1A9")

# Display order of statuses in the table
STATUS_ORDER = [core.STATUS_UPDATE, core.STATUS_UP_TO_DATE, core.STATUS_NOT_FOUND,
                core.STATUS_NO_COMPATIBLE, core.STATUS_UPDATED, core.STATUS_FAILED]
# (light, dark) foreground per status
STATUS_COLORS = {
    core.STATUS_UPDATE: ("#B26A00", "#F0B44C"),
    core.STATUS_UP_TO_DATE: ("#2E7D4F", "#5FCB8A"),
    core.STATUS_NOT_FOUND: ("#7A8088", "#8A9099"),
    core.STATUS_NO_COMPATIBLE: ("#B0413E", "#E57373"),
    core.STATUS_UPDATED: ("#1F8A4C", "#7BE0A3"),
    core.STATUS_FAILED: ("#C62828", "#FF6B6B"),
}


def status_label(status: str) -> str:
    return t(f"status_{status}")


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
        super().__init__(app, t("edit_profile") if profile else t("new_profile"), 580, 390)
        self.app = app
        self.original = profile
        self.result: Optional[Dict] = None
        profile = profile or {
            "name": "",
            "path": core.DEFAULT_MINECRAFT_MODS if not app.config_data["profiles"] else "",
            "game_version": core.AUTO,
            "loader": core.AUTO,
        }

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body, text=t("new_profile") if not self.original else t("edit_profile"),
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ctk.CTkLabel(body, text=t("name")).grid(row=1, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar(value=profile["name"])
        ctk.CTkEntry(body, textvariable=self.name_var, placeholder_text=t("name_placeholder")).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=6)

        ctk.CTkLabel(body, text=t("mods_folder")).grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self.path_var = tk.StringVar(value=profile["path"])
        ctk.CTkEntry(body, textvariable=self.path_var).grid(row=2, column=1, sticky="ew", pady=6)
        ctk.CTkButton(body, text=t("browse"), width=96, command=self._browse).grid(row=2, column=2, padx=(8, 0), pady=6)

        ctk.CTkLabel(body, text="Minecraft").grid(row=3, column=0, sticky="w", pady=6)
        self.version_var = tk.StringVar(value=to_label(profile["game_version"]))
        ctk.CTkComboBox(body, variable=self.version_var, values=app.version_choices()).grid(
            row=3, column=1, sticky="ew", pady=6)
        self.detect_btn = ctk.CTkButton(body, text=t("detect"), width=96, fg_color="transparent", border_width=1,
                                        text_color=("gray10", "gray90"), command=self._detect)
        self.detect_btn.grid(row=3, column=2, padx=(8, 0), pady=6)

        ctk.CTkLabel(body, text=t("loader")).grid(row=4, column=0, sticky="w", pady=6)
        self.loader_var = tk.StringVar(value=to_label(profile["loader"]))
        ctk.CTkOptionMenu(body, variable=self.loader_var, values=app.loader_choices()).grid(
            row=4, column=1, sticky="ew", pady=6)

        self.hint = ctk.CTkLabel(body, text=t("profile_hint"), text_color=MUTED, wraplength=520, justify="left")
        self.hint.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))

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

        self.app.run_task(lambda: core.detect_target(self.app.client, path), done, failed)

    def _save(self):
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        game_version = self.version_var.get().strip()
        if not name:
            return self._error(t("err_name_required"))
        others = [p["name"] for p in self.app.config_data["profiles"] if p is not self.original]
        if name in others:
            return self._error(t("err_name_exists", name=name))
        if not path:
            return self._error(t("err_folder_required"))
        if not game_version:
            return self._error(t("err_version_required"))
        self.result = {"name": name, "path": path, "game_version": from_label(game_version),
                       "loader": from_label(self.loader_var.get())}
        self.destroy()

    def _error(self, text: str):
        self.hint.configure(text=text, text_color=DANGER)


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
        self.app_auto_update_var = tk.BooleanVar(value=cfg.get("app_auto_update", False))
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
    def __init__(self):
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
        self.tags = core.load_tag_cache()
        self.mods: List[core.ModInfo] = []
        self.last_scan: Optional[core.ScanResult] = None
        self.app_release: Optional[app_updater.Release] = None
        self.banner_dismissed = False
        self.updating_app = False
        self.checked: set = set()
        self.busy = False
        self.sort_key = ("status", False)
        self._row_tags: Dict[str, List[str]] = {}
        self._hover_row: Optional[str] = None
        self._queue: "queue.Queue" = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

        self.after(50, self._poll_queue)
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
                fn(arg)
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
        for widget in (self.check_btn, self.add_btn, self.edit_btn, self.delete_btn, self.version_box,
                       self.loader_menu, self.settings_btn):
            widget.configure(state=state)
        for btn in self.profile_buttons:
            btn.configure(state=state)
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
        if self.app_release and not self.banner_dismissed:
            self._show_update_banner()

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=SIDEBAR_BG)
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
                print(f"Could not load logo: {e!r}", file=sys.stderr)
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left", padx=10)
        ctk.CTkLabel(titles, text="Mod Updater", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(titles, text=t("app_subtitle"), text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")

        ctk.CTkLabel(side, text=t("profiles"), text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=1, column=0, sticky="w", padx=20, pady=(4, 4))
        self.profile_list = ctk.CTkScrollableFrame(side, fg_color="transparent")
        self.profile_list.grid(row=3, column=0, sticky="nsew", padx=8)
        self.profile_buttons: List[ctk.CTkButton] = []

        self.add_btn = ctk.CTkButton(side, text=t("new_profile_btn"), fg_color="transparent", border_width=1,
                                     text_color=("gray10", "gray90"), border_color=MUTED,
                                     command=self.add_profile)
        self.add_btn.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 6))
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
        self.profile_title = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        self.profile_title.grid(row=0, column=0, sticky="w")
        self.profile_path = ctk.CTkLabel(header, text="", text_color=MUTED, anchor="w", cursor="hand2")
        self.profile_path.grid(row=1, column=0, sticky="w")
        self.profile_path.bind("<Button-1>", lambda _e: open_folder(self.current_profile()["path"])
                               if self.current_profile() else None)
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        ghost = dict(fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), width=90)
        ctk.CTkButton(actions, text=t("open"), command=lambda: open_folder(self.current_profile()["path"])
                      if self.current_profile() else None, **ghost).pack(side="left", padx=4)
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

        # Mod table
        table = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        table.grid(row=4, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        columns = ("sel", "name", "current", "latest", "status")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", style="Mods.Treeview", selectmode="none")
        headings = {"sel": "", "name": t("col_mod"), "current": t("col_installed"), "latest": t("col_available"),
                    "status": t("col_status")}
        widths = {"sel": 40, "name": 240, "current": 160, "latest": 160, "status": 190}
        for col in columns:
            self.tree.heading(col, text=headings[col], command=(lambda c=col: self._sort_by(c)) if col != "sel"
                              else self._toggle_all)
            self.tree.column(col, width=widths[col], minwidth=40, stretch=col == "name",
                             anchor="center" if col == "sel" else "w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scroll = ctk.CTkScrollbar(table, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=4, pady=10)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Motion>", self._on_tree_motion)

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
        style.configure("Mods.Treeview.Heading", background=head_bg, foreground=fg, relief="flat",
                        borderwidth=0, font=(family, 10, "bold"), padding=(8, 6))
        style.map("Mods.Treeview.Heading", background=[("active", head_bg)])
        style.map("Mods.Treeview", background=[("selected", bg)], foreground=[("selected", fg)])
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=pick(color))
        self.tree.tag_configure("odd", background="#26292D" if is_dark() else "#F0F2F4")
        self.tree.tag_configure("hover", background="#30353A" if is_dark() else "#E3E7EB")

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
        for btn in self.profile_buttons:
            btn.destroy()
        self.profile_buttons = []
        current = self.current_profile()
        for profile in self.config_data["profiles"]:
            active = current is profile
            btn = ctk.CTkButton(
                self.profile_list, text=f"  {profile['name']}", anchor="w", height=36,
                fg_color=ACCENT if active else "transparent",
                hover_color=ACCENT_HOVER if active else ("gray80", "gray25"),
                text_color=("white", "white") if active else ("gray10", "gray90"),
                font=ctk.CTkFont(size=14, weight="bold" if active else "normal"),
                command=lambda name=profile["name"]: self.select_profile(name))
            btn.pack(fill="x", pady=2)
            self.profile_buttons.append(btn)
        self.add_btn.configure(state="normal" if len(self.config_data["profiles"]) < core.MAX_PROFILES else "disabled")

        has_profile = current is not None
        self.profile_title.configure(text=current["name"] if has_profile else t("no_profiles"))
        self.profile_path.configure(text=shorten_path(current["path"]) if has_profile else t("create_profile_hint"))
        for w in (self.edit_btn, self.delete_btn, self.check_btn):
            w.configure(state="normal" if has_profile else "disabled")
        self.refresh_target_bar()

    def refresh_target_bar(self):
        profile = self.current_profile()
        self.version_box.configure(values=self.version_choices())
        self.loader_menu.configure(values=self.loader_choices())
        if profile:
            self.version_var.set(to_label(profile.get("game_version")))
            self.loader_var.set(to_label(profile.get("loader")))

    def select_profile(self, name: str):
        if self.busy or name == self.config_data["current_profile"]:
            return
        self.config_data["current_profile"] = name
        core.save_config(self.config_data)
        self._clear_results()
        self.refresh_profiles()

    def add_profile(self):
        dialog = ProfileDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.config_data["profiles"].append(dialog.result)
            self.config_data["current_profile"] = dialog.result["name"]
            core.save_config(self.config_data)
            self._clear_results()
            self.refresh_profiles()

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
            self._clear_results()
            self.refresh_profiles()

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
        self._clear_results()
        self.refresh_profiles()

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
        new_loader = from_label(self.loader_var.get())
        if (new_version, new_loader) != (profile.get("game_version"), profile.get("loader")):
            profile["game_version"] = new_version
            profile["loader"] = new_loader
            core.save_config(self.config_data)
            if self.mods:
                self._clear_results()
                self.summary_label.configure(text=t("target_changed"))

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
        self._set_busy(True)
        allow_beta = self.config_data["allow_beta"]
        self.run_task(
            lambda: core.scan_mods(self.client, path, game_version, profile["loader"], allow_beta, self._progress_cb),
            self._on_scan_done)

    def _on_scan_done(self, result: core.ScanResult):
        self._set_busy(False)
        self.last_scan = result
        self.mods = result.mods
        self.checked = {m.path for m in self.mods if m.status == core.STATUS_UPDATE}
        self._fill_tree()
        self._update_summary()
        self._show_scan_status(result)

    def _show_scan_status(self, result: core.ScanResult):
        mods = result.mods
        if result.detected:
            self.detected_label.configure(
                text=f"→ {result.game_version or '?'} · {result.loader or '?'}",
                text_color=ACCENT if result.game_version and result.loader else DANGER)
        if not mods:
            self.status_label.configure(text=t("no_jars"))
        elif not result.game_version or not result.loader:
            self.status_label.configure(text=t("detect_failed"))
        else:
            pending = len(self.checked)
            self.status_label.configure(text=t("updates_available", n=pending) if pending
                                        else t("all_up_to_date"))

    def update_selected(self):
        profile = self.current_profile()
        selected = [m for m in self.mods if m.path in self.checked and m.status == core.STATUS_UPDATE]
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
        ok = sum(1 for m in mods if m.status == core.STATUS_UPDATED)
        failed = [m for m in mods if m.status == core.STATUS_FAILED]
        text = t("updated_count", n=ok)
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

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._row_tags = {}
        self._hover_row = None
        for i, mod in enumerate(self._visible_mods()):
            selectable = mod.status == core.STATUS_UPDATE
            mark = ("☑" if mod.path in self.checked else "☐") if selectable else ""
            name = mod.display_name + (f"  {t('disabled_suffix')}" if mod.disabled else "")
            status = status_label(mod.status)
            tags = [mod.status] + (["odd"] if i % 2 else [])
            self._row_tags[mod.path] = tags
            self.tree.insert("", "end", iid=mod.path, values=(mark, name, mod.current_version, mod.latest_version, status),
                             tags=tags)
        self._refresh_update_button()

    def _update_summary(self):
        counts = {s: 0 for s in STATUS_ORDER}
        for m in self.mods:
            counts[m.status] = counts.get(m.status, 0) + 1
        parts = [t("sum_mods", n=len(self.mods))]
        if counts[core.STATUS_UPDATE]:
            parts.append(t("sum_update", n=counts[core.STATUS_UPDATE]))
        if counts[core.STATUS_UPDATED]:
            parts.append(t("sum_updated", n=counts[core.STATUS_UPDATED]))
        parts.append(t("sum_up_to_date", n=counts[core.STATUS_UP_TO_DATE]))
        if counts[core.STATUS_NO_COMPATIBLE]:
            parts.append(t("sum_no_compatible", n=counts[core.STATUS_NO_COMPATIBLE]))
        if counts[core.STATUS_NOT_FOUND]:
            parts.append(t("sum_not_found", n=counts[core.STATUS_NOT_FOUND]))
        self.summary_label.configure(text="  ·  ".join(parts))

    def _refresh_update_button(self):
        n = sum(1 for m in self.mods if m.path in self.checked and m.status == core.STATUS_UPDATE)
        enabled = bool(n) and not self.busy
        self.update_btn.configure(text=t("update_selected_n", n=n) if n else t("update_selected"),
                                  state="normal" if enabled else "disabled",
                                  fg_color=ACCENT if enabled else ("gray75", "gray30"))

    def _on_tree_click(self, event):
        if self.busy or self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        mod = next((m for m in self.mods if m.path == iid), None)
        if not mod or mod.status != core.STATUS_UPDATE:
            return
        self.checked.symmetric_difference_update({iid})
        values = list(self.tree.item(iid, "values"))
        values[0] = "☑" if iid in self.checked else "☐"
        self.tree.item(iid, values=values)
        self._refresh_update_button()

    def _toggle_all(self):
        if self.busy:
            return
        updatable = {m.path for m in self._visible_mods() if m.status == core.STATUS_UPDATE}
        if updatable and updatable <= self.checked:
            self.checked -= updatable
        else:
            self.checked |= updatable
        self._fill_tree()

    def _sort_by(self, column: str):
        key, reverse = self.sort_key
        self.sort_key = (column, not reverse if key == column else False)
        self._fill_tree()

    def _on_tree_motion(self, event):
        row = self.tree.identify_row(event.y)
        previous = getattr(self, "_hover_row", None)
        if row == previous:
            return
        if previous and self.tree.exists(previous):
            self.tree.item(previous, tags=self._row_tags.get(previous, []))
        if row:
            self.tree.item(row, tags=[t for t in self._row_tags.get(row, []) if t != "odd"] + ["hover"])
        self._hover_row = row


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
