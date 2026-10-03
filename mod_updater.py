"""Minecraft Mod Updater - graphical interface."""

import os
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

import app_updater
import i18n
import modpack
import updater_core as core
from dialogs import (  # noqa: F401
    BackupsDialog,
    ChangelogDialog,
    CompareDialog,
    ImportDialog,
    MigrationDialog,
    ProfileDialog,
    SearchDialog,
    SettingsDialog,
    VersionPickerDialog,
)
from i18n import t
from mod_icons import IconCache
from mod_table import ModTableMixin
from sidebar import ProfileListMixin
from ui_common import (  # noqa: F401
    ACCENT,
    ACCENT_HOVER,
    CARD_BG,
    DANGER,
    MUTED,
    PROFILE_ROW_HEIGHT,
    PROFILE_SLOT,
    SIDEBAR_BG,
    SIDEBAR_MAX_WIDTH,
    SIDEBAR_MIN_WIDTH,
    STATUS_COLORS,
    TREE_ITEM_PADDING,
    from_label,
    is_dark,
    open_folder,
    pick,
    resource_path,
    set_window_icon,
    to_label,
    ui_font_family,
)

# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class App(ProfileListMixin, ModTableMixin, ctk.CTk):
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
        self._queue: queue.Queue = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

        self._bind_shortcuts()
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
                core.log.warning("background task failed: %r", e)
                self._queue.put((on_error or self._show_error, e))
                return
            self._queue.put((on_done, result))
        threading.Thread(target=target, daemon=True).start()

    def _poll_queue(self):
        """Run the results of background work on the Tk thread. Keeps going whatever a callback does."""
        try:
            while True:
                fn, arg = self._queue.get_nowait()
                try:
                    fn(arg)
                except tk.TclError:
                    pass  # the window a result was meant for has been closed
                except Exception:  # noqa: BLE001 - one broken callback must not stop all the others
                    self.report_callback_exception(*sys.exc_info())
        except queue.Empty:
            pass
        finally:
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
                       self.select_all_box, self.migrate_btn, self.search_btn, self.more_btn):
            widget.configure(state=state)
        self._apply_content_state()
        if busy:
            self.update_btn.configure(state="disabled")
        else:
            self._refresh_update_button()

    def report_callback_exception(self, exc, val, tb):
        """Errors in Tk callbacks go to the log as well as to the console."""
        core.log.error("unexpected error", exc_info=(exc, val, tb))
        super().report_callback_exception(exc, val, tb)

    # ----- keyboard shortcuts ---------------------------------------------- #

    MOD_KEY = "Command" if sys.platform == "darwin" else "Control"
    MOD_LABEL = "⌘" if sys.platform == "darwin" else "Ctrl+"

    def shortcut_list(self) -> List[Tuple[str, str]]:
        """(keys, what they do) for the shortcuts window."""
        m = self.MOD_LABEL
        plain = lambda key: re.sub(r"^[^\w]+", "", t(key)).strip()  # noqa: E731 - drop the button's emoji
        return [(f"F5  /  {m}R", plain("check_updates")), (f"{m}U", plain("update_selected")),
                (f"{m}F", t("sc_filter")), ("Esc", t("sc_clear_filter")), (f"{m}A", plain("select_all")),
                (f"{m}↑  /  {m}↓", t("sc_switch_profile")), (f"{m}N", plain("new_profile")),
                (f"{m}E", plain("edit_profile")), (f"{m}B", plain("backups_title")),
                (f"{m},", plain("settings")), ("F1", t("sc_help"))]

    def _bind_shortcuts(self):
        k = self.MOD_KEY
        actions = {
            "<F5>": self.check_updates, f"<{k}-r>": self.check_updates, f"<{k}-u>": self.update_selected,
            f"<{k}-f>": self._focus_filter, "<Escape>": self._clear_filter, f"<{k}-a>": self._shortcut_select_all,
            f"<{k}-Up>": lambda: self._switch_profile(-1), f"<{k}-Down>": lambda: self._switch_profile(1),
            f"<{k}-n>": self.add_profile, f"<{k}-e>": self.edit_profile, f"<{k}-b>": self.show_backups,
            f"<{k}-comma>": lambda: SettingsDialog(self), "<F1>": self.show_shortcuts,
        }
        for sequence, action in actions.items():
            self.bind_all(sequence, lambda event, a=action: self._run_shortcut(event, a), add="+")

    def _run_shortcut(self, event, action: Callable):
        # Only in the main window, not in a dialog that is open on top of it
        widget = event.widget if isinstance(event.widget, tk.Misc) else None
        if widget is None or widget.winfo_toplevel() is not self or self.busy and action != self.show_shortcuts:
            return None
        action()
        return "break"

    def _focus_filter(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def _clear_filter(self):
        if self.search_entry.get():
            self.search_entry.delete(0, "end")
            self._fill_tree()
        self.focus_set()

    def _shortcut_select_all(self):
        if self.focus_get() is not getattr(self.search_entry, "_entry", None):  # Ctrl+A in the filter selects text
            self._toggle_all()

    def _switch_profile(self, step: int):
        profiles = self.config_data["profiles"]
        current = self.current_profile()
        if not profiles or current is None:
            return
        index = (profiles.index(current) + step) % len(profiles)
        self.select_profile(profiles[index]["name"])

    def show_shortcuts(self):
        lines = [f"{keys:<14}  {text}" for keys, text in self.shortcut_list()]
        messagebox.showinfo(t("shortcuts_btn"), "\n".join(lines), parent=self)

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
        self.more_btn = ctk.CTkButton(actions, text="⋯", width=40, command=self._show_more_menu,
                                      **{k: v for k, v in ghost.items() if k != "width"})
        self.more_btn.pack(side="left", padx=(8, 0))

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
        self.migrate_btn = ctk.CTkButton(bar, text=t("migrate_btn"), fg_color="transparent", border_width=1,
                                         text_color=("gray10", "gray90"), width=110, height=36,
                                         command=self.show_migration)
        self.migrate_btn.pack(side="right")

        # Summary on its own line, then the table's tools: find on Modrinth | select all, filter
        summary = ctk.CTkFrame(main, fg_color="transparent")
        summary.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.summary_label = ctk.CTkLabel(summary, text=t("press_check"),
                                          text_color=MUTED, anchor="w")
        self.summary_label.pack(fill="x", pady=(0, 6))
        tools = ctk.CTkFrame(summary, fg_color="transparent")
        tools.pack(fill="x")
        self.search_btn = ctk.CTkButton(tools, text=t("search_btn"), fg_color="transparent", border_width=1,
                                        text_color=("gray10", "gray90"), command=self.show_search)
        self.search_btn.pack(side="left")
        self.search_entry = ctk.CTkEntry(tools, placeholder_text=t("filter_placeholder"), width=220)
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._fill_tree())
        self.select_all_var = tk.BooleanVar(value=False)
        self.select_all_box = ctk.CTkCheckBox(tools, text=t("select_all"), variable=self.select_all_var,
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
        added = 0
        for inst in dialog.result:
            if len(self.config_data["profiles"]) >= core.MAX_PROFILES:
                break
            name = self._unique_profile_name(inst.name)
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

    def _unique_profile_name(self, wanted: str) -> str:
        names = {p["name"] for p in self.config_data["profiles"]}
        base = wanted.strip()[:core.MAX_PROFILE_NAME] or "pack"
        name, n = base, 2
        while name in names:
            suffix = f" ({n})"
            name = base[:core.MAX_PROFILE_NAME - len(suffix)] + suffix
            n += 1
        return name

    # ----- modpacks and comparing ------------------------------------------- #

    def _show_more_menu(self):
        if not self.current_profile() or self.busy:
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=t("menu_export_mrpack"), command=self.export_profile)
        menu.add_command(label=t("menu_compare"), command=lambda: CompareDialog(self))
        x, y = self.more_btn.winfo_rootx(), self.more_btn.winfo_rooty() + self.more_btn.winfo_height()
        menu.tk_popup(x, y)

    def _profile_target(self, profile: Dict) -> Tuple[str, Optional[str]]:
        """Minecraft version and loader of a profile: from the last check, the profile, or detected."""
        scan = self.last_scan
        version, loader = profile.get("game_version", core.AUTO), profile.get("loader", core.AUTO)
        if scan and scan.game_version:
            version, loader = scan.game_version, scan.loader or loader
        if version == core.AUTO or loader == core.AUTO:
            found = core.detect_target(self.client, profile["path"], profile.get("content", core.CONTENT_MODS))
            version = found.get("game_version", "") if version == core.AUTO else version
            loader = found.get("loader") if loader == core.AUTO else loader
        if not version:
            raise core.ModrinthError(t("search_target_unknown"))
        return version, loader

    def export_profile(self):
        """Save the current profile as a Modrinth modpack (.mrpack)."""
        profile = self.current_profile()
        if not profile or self.busy:
            return
        destination = filedialog.asksaveasfilename(
            parent=self, title=t("menu_export_mrpack"), defaultextension=".mrpack",
            initialfile=f"{profile['name']}.mrpack", filetypes=[("Modrinth modpack", "*.mrpack")])
        if not destination:
            return
        self._set_busy(True)
        self.status_label.configure(text=t("mrpack_exporting"))

        def work():
            version, loader = self._profile_target(profile)
            return modpack.export_mrpack(self.client, profile["path"], profile.get("content", core.CONTENT_MODS),
                                         version, loader, profile["name"], destination)

        def done(counts: Dict[str, int]):
            self._set_busy(False)
            self.status_label.configure(text=t("export_done", n=counts["downloads"], m=counts["overrides"]))

        self.run_task(work, done)

    def import_mrpack(self, path: str, game_dir: str):
        """Install a Modrinth modpack into a folder and add it as a new profile."""
        if self.busy or len(self.config_data["profiles"]) >= core.MAX_PROFILES:
            return
        try:
            pack = modpack.read_mrpack(path)
        except modpack.ModpackError as e:
            messagebox.showerror(core.APP_NAME, str(e), parent=self)
            return
        self._set_busy(True)

        def done(_result):
            self._set_busy(False)
            name = self._unique_profile_name(pack.name)
            self.config_data["profiles"].append({
                "name": name, "path": os.path.join(game_dir, "mods"), "game_version": pack.game_version,
                "loader": pack.loader or core.AUTO, "color": core.next_profile_color(self.config_data["profiles"]),
                "content": core.CONTENT_MODS, "server": False, "ignored": [], "pinned": {}})
            self.config_data["current_profile"] = name
            core.save_config(self.config_data)
            self.refresh_profiles()
            self.show_local_mods()
            loader = (" " + t("mrpack_with_loader", loader=pack.loader, version=pack.loader_version or "?")
                      if pack.loader else "")
            messagebox.showinfo(core.APP_NAME, t("mrpack_done", name=pack.name, path=game_dir,
                                                 version=pack.game_version, loader=loader), parent=self)

        self.run_task(lambda: modpack.install_mrpack(self.client, pack, game_dir, self._progress_cb), done)

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
        version = self.app_release.version if self.app_release else ""
        self.banner_label.configure(text=text or t("app_update_available", version=version))
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
        pinned = dict(profile.get("pinned", {}))
        server = bool(profile.get("server"))
        self.run_task(
            lambda: core.scan_mods(self.client, path, game_version, profile["loader"], allow_beta,
                                   self._progress_cb, content=content, ignored=ignored, server=server,
                                   pinned=pinned),
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

    def confirm_game_closed(self, folder: str, parent: Optional[tk.Misc] = None) -> bool:
        """Ask to close Minecraft while it runs with this folder. False if the user gives up."""
        while core.game_running(folder):
            if not messagebox.askretrycancel(t("game_running_title"), t("game_running"), icon="warning",
                                             parent=parent or self):
                return False
        return True

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
            text = t("updates_available", n=pending) if pending else t("all_up_to_date")
            problems = sum(1 for m in mods if m.has_problems)
            if problems:
                text += "  " + t("problems_found", n=problems)
            self.status_label.configure(text=text)

    def update_selected(self):
        profile = self.current_profile()
        selected = [m for m in self.mods if m.path in self.checked and m.actionable]
        if not profile or not selected or self.busy or not self.confirm_game_closed(profile["path"]):
            return
        self._set_busy(True)
        self.progress.set(0)
        backup = self.config_data["backup_mods"]
        self.run_task(lambda: core.update_mods(self.client, selected, profile["path"], backup, self._progress_cb),
                      lambda backup_dir: self._on_update_done(selected, backup_dir))

    def show_search(self):
        if self.current_profile() and not self.busy:
            SearchDialog(self)

    def install_projects(self, project: Dict, game_version: str, loaders: List[str],
                         on_done: Callable, on_error: Callable, parent: Optional[tk.Misc] = None):
        """Install a project found in the search (and its missing dependencies) into the current profile."""
        profile = self.current_profile()
        if not profile or self.busy or not self.confirm_game_closed(profile["path"], parent=parent):
            return on_error(core.ModrinthError(t("game_running_title")))
        folder, content = profile["path"], profile.get("content", core.CONTENT_MODS)
        allow_beta = self.config_data["allow_beta"]
        self._set_busy(True)

        def work() -> List[core.ModInfo]:
            mods = core.plan_install(self.client, project, folder, game_version, loaders, allow_beta, content)
            core.update_mods(self.client, mods, folder, False, self._progress_cb)
            return mods

        def done(mods: List[core.ModInfo]):
            self._set_busy(False)
            installed = [m for m in mods if m.status == core.STATUS_INSTALLED]
            text = t("search_done", mod=mods[0].display_name)
            if len(installed) > 1:
                text += " " + t("installed_count", n=len(installed))
            self.show_local_mods(status=text)
            on_done(mods)

        def failed(err: Exception):
            self._set_busy(False)
            on_error(err)

        self.run_task(work, done, failed)

    def show_migration(self):
        if self.current_profile() and not self.busy:
            MigrationDialog(self)

    def migrate_profile(self, plan: core.MigrationPlan, disable_missing: bool):
        """Move the current profile to another Minecraft version (see MigrationDialog)."""
        profile = self.current_profile()
        if not profile or self.busy or not self.confirm_game_closed(profile["path"]):
            return
        self._clear_results()
        self._list_token += 1
        self._set_busy(True)
        backup = self.config_data["backup_mods"]

        def done(outcome):
            backup_dir, failed = outcome
            self._set_busy(False)
            profile["game_version"] = plan.target
            core.save_config(self.config_data)
            self.refresh_target_bar()
            if failed:
                details = "\n".join(f"• {m.display_name}: {m.error}" for m in failed[:15])
                messagebox.showwarning(core.APP_NAME, t("some_failed", details=details), parent=self)
            else:
                messagebox.showinfo(core.APP_NAME, t("migrate_done", version=plan.target,
                                                     n=len(plan.to_install)), parent=self)
            self.check_updates()

        self.run_task(lambda: core.migrate(self.client, plan, profile["path"], backup, disable_missing,
                                           self._progress_cb), done)

    def install_version(self, mod: core.ModInfo, version: Dict):
        """Install a version chosen in the version picker and pin the mod to it."""
        profile = self.current_profile()
        if not profile or self.busy or not mod.project_id or not self.confirm_game_closed(profile["path"]):
            return
        project_id = mod.project_id
        mod.latest = version
        self._set_busy(True)
        self.progress.set(0)
        backup = self.config_data["backup_mods"]

        def done(backup_dir: Optional[str]):
            if mod.status == core.STATUS_UPDATED:
                profile.setdefault("pinned", {})[project_id] = version.get("id", "")
                core.save_config(self.config_data)
                mod.status = core.STATUS_PINNED
            self._on_update_done([mod], backup_dir)

        self.run_task(lambda: core.update_mods(self.client, [mod], profile["path"], backup, self._progress_cb), done)

    def _on_update_done(self, mods: List[core.ModInfo], backup_dir: Optional[str]):
        self._set_busy(False)
        self.last_scan = None
        self.checked = set()
        self._fill_tree()
        self._update_summary()
        ok = sum(1 for m in mods if m.status in (core.STATUS_UPDATED, core.STATUS_INSTALLED, core.STATUS_PINNED))
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
    core.setup_logging()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
