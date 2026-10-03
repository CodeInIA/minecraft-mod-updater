"""Dialogs: profile, changelog, backups, import from launchers and settings."""

import os
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import customtkinter as ctk

import app_updater
import i18n
import launchers
import modpack
import updater_core as core
from i18n import t
from ui_common import (
    ACCENT,
    ACCENT_HOVER,
    CARD_BG,
    CONTENT_ORDER,
    DANGER,
    DANGER_HOVER,
    MARKDOWN_LINK,
    MUTED,
    Dialog,
    compact_number,
    content_label,
    from_label,
    open_folder,
    shorten_path,
    to_label,
)

if TYPE_CHECKING:
    from mod_updater import App


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


class VersionPickerDialog(Dialog):
    """Choose a version of a mod to install (a newer or an older one); the mod is then pinned to it."""

    def __init__(self, app: "App", mod: core.ModInfo):
        super().__init__(app, t("choose_version_title", mod=mod.display_name), 600, 520)
        self.app = app
        self.mod = mod
        scan = app.last_scan
        self.game_version = (scan.game_version or "") if scan else ""
        self.loaders = scan.loaders if scan else []
        ctk.CTkLabel(self, text=t("choose_version_title", mod=mod.display_name),
                     font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(18, 2))
        ctk.CTkLabel(self, text=t("choose_version_hint", version=self.game_version or "?",
                                  loader=", ".join(self.loaders) or "?"),
                     text_color=MUTED, anchor="w", justify="left", wraplength=560).pack(fill="x", padx=20)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=20, pady=12)
        self.message = ctk.CTkLabel(self.list, text=t("versions_loading"), text_color=MUTED)
        self.message.pack(padx=12, pady=16, anchor="w")
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(0, 18))
        self.install_btn = ctk.CTkButton(buttons, text=t("install_version"), fg_color=ACCENT,
                                         hover_color=ACCENT_HOVER, state="disabled", command=self._install)
        self.install_btn.pack(side="right")
        ctk.CTkButton(buttons, text=t("cancel"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.choice = tk.StringVar(value="")
        self.versions: Dict[str, Dict] = {}
        app.run_task(lambda: core.available_versions(app.client, mod, self.game_version, self.loaders),
                     self._show, lambda e: self._show_message(str(e)))

    def _show_message(self, text: str):
        if self.winfo_exists():
            self.message.configure(text=text)

    def _show(self, versions: List[Dict]):
        if not self.winfo_exists():
            return
        if not versions:
            return self._show_message(t("no_versions"))
        self.message.destroy()
        installed = (self.mod.current or {}).get("id")
        for v in versions:
            vid = v.get("id", "")
            self.versions[vid] = v
            kind = v.get("version_type", "release")
            text = f"{v.get('version_number', '?')}   ·   {(v.get('date_published') or '')[:10]}"
            if kind != "release":
                text += f"   [{kind}]"
            if vid == installed:
                text += f"   ({t('version_installed_tag')})"
            ctk.CTkRadioButton(self.list, text=text, variable=self.choice, value=vid, fg_color=ACCENT,
                               hover_color=ACCENT_HOVER, state="disabled" if vid == installed else "normal",
                               command=lambda: self.install_btn.configure(state="normal")).pack(
                anchor="w", padx=12, pady=5)

    def _install(self):
        version = self.versions.get(self.choice.get())
        if version:
            self.destroy()
            self.app.install_version(self.mod, version)


class SearchDialog(Dialog):
    """Find mods (or packs/shaders) on Modrinth for the profile's target and install them."""

    ROW_ICON = 36

    def __init__(self, app: "App"):
        super().__init__(app, t("search_title"), 700, 640)
        self.app = app
        self.profile = app.current_profile() or {}
        self.content = self.profile.get("content", core.CONTENT_MODS)
        self.game_version = ""
        self.loaders: List[str] = []
        self.installed = core.installed_projects(app.mods)
        self.rows: Dict[str, Dict[str, Any]] = {}
        self._images: List[ctk.CTkImage] = []
        ctk.CTkLabel(self, text=t("search_title"), font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        self.target_label = ctk.CTkLabel(self, text=t("search_target_detecting"), text_color=MUTED, anchor="w",
                                         justify="left", wraplength=650)
        self.target_label.pack(fill="x", padx=22)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=(12, 0))
        self.query = ctk.CTkEntry(bar, placeholder_text=t("search_placeholder"))
        self.query.pack(side="left", fill="x", expand=True)
        self.query.bind("<Return>", lambda _e: self.search())
        self.search_btn = ctk.CTkButton(bar, text=t("search_go"), width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        state="disabled", command=self.search)
        self.search_btn.pack(side="left", padx=(8, 0))
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=22, pady=12)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(0, 18))
        ctk.CTkButton(buttons, text=t("close"), width=110, command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self._message(t("search_target_detecting"))
        self._find_target()

    # ----- target ----------------------------------------------------------- #

    def _find_target(self):
        """The profile's Minecraft version and loader: from the last check, the profile, or detected."""
        scan, profile = self.app.last_scan, self.profile
        version, loader = profile.get("game_version", core.AUTO), profile.get("loader", core.AUTO)
        if scan and scan.game_version:
            version, loader = scan.game_version, scan.loader or loader
        if version != core.AUTO and (loader != core.AUTO or self.content != core.CONTENT_MODS):
            return self._set_target({"game_version": version, "loader": loader})
        self.app.run_task(lambda: core.detect_target(self.app.client, profile["path"], self.content),
                          lambda found: self._set_target({"game_version": version if version != core.AUTO
                                                          else found.get("game_version", ""),
                                                          "loader": loader if loader != core.AUTO
                                                          else found.get("loader", "")}),
                          lambda _e: self._set_target({}))

    def _set_target(self, target: Dict[str, str]):
        if not self.winfo_exists():
            return
        self.game_version = target.get("game_version") or ""
        self.loaders = core.target_loaders(self.content, target.get("loader"))
        if not self.game_version or not self.loaders:
            self.target_label.configure(text=t("search_target_unknown"), text_color=DANGER)
            self._message(t("search_target_unknown"))
            return
        loader = target.get("loader") if self.content == core.CONTENT_MODS else content_label(self.content)
        self.target_label.configure(text=t("search_target", version=self.game_version, loader=loader))
        self.search_btn.configure(state="normal")
        self.query.focus_set()
        self.search()

    # ----- results ---------------------------------------------------------- #

    def _message(self, text: str):
        for child in self.list.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.list, text=text, text_color=MUTED, wraplength=600, justify="left").pack(
            padx=12, pady=16, anchor="w")

    def search(self):
        if not self.game_version:
            return
        query = self.query.get().strip()
        self.search_btn.configure(state="disabled")
        self._message(t("search_searching"))
        self.app.run_task(lambda: core.search_projects(self.app.client, query, self.content, self.game_version,
                                                       self.loaders),
                          self._show, lambda e: self._failed(e))

    def _failed(self, err: Exception):
        if self.winfo_exists():
            self.search_btn.configure(state="normal")
            self._message(str(err))

    def _show(self, hits: List[Dict]):
        if not self.winfo_exists():
            return
        self.search_btn.configure(state="normal")
        for child in self.list.winfo_children():
            child.destroy()
        self.rows = {}
        if not hits:
            return self._message(t("search_none"))
        for hit in hits:
            self._add_row(hit)
        missing = self.app.icons.missing(h.get("icon_url") or "" for h in hits)
        if missing:
            self.app.run_task(lambda: self.app.icons.download(missing), lambda _r: self._refresh_icons(),
                              lambda _e: None)

    def _icon_image(self, url: str) -> Optional[ctk.CTkImage]:
        image = self.app.icons.get(url)
        if image is None:
            return None
        icon = ctk.CTkImage(light_image=image, dark_image=image, size=(self.ROW_ICON, self.ROW_ICON))
        self._images.append(icon)
        return icon

    def _refresh_icons(self):
        if not self.winfo_exists():
            return
        for row in self.rows.values():
            icon = self._icon_image(row["hit"].get("icon_url") or "")
            if icon is not None:
                row["icon"].configure(image=icon, text="", fg_color="transparent")

    def _add_row(self, hit: Dict):
        project_id = hit.get("project_id", "")
        row = ctk.CTkFrame(self.list, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=6)
        icon = self._icon_image(hit.get("icon_url") or "")
        icon_label = ctk.CTkLabel(row, text="" if icon else "▢", image=icon, width=self.ROW_ICON,
                                  height=self.ROW_ICON, fg_color="transparent" if icon else ("gray80", "gray25"),
                                  corner_radius=8)
        icon_label.pack(side="left", padx=(4, 10), anchor="n")
        installed = project_id in self.installed
        button = ctk.CTkButton(row, text=t("search_installed") if installed else t("search_install"), width=100,
                               fg_color=ACCENT if not installed else "transparent", hover_color=ACCENT_HOVER,
                               border_width=0 if not installed else 1, text_color=("gray10", "gray90"),
                               state="disabled" if installed else "normal",
                               command=lambda: self._install(project_id))
        if not installed:
            button.configure(text_color=("white", "white"))
        button.pack(side="right", padx=(10, 4), anchor="center")
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        title = ctk.CTkLabel(text, text=hit.get("title", "?"), font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
                             cursor="hand2")
        title.pack(fill="x")
        title.bind("<Button-1>", lambda _e: webbrowser.open(
            f"https://modrinth.com/{hit.get('project_type') or 'mod'}/{hit.get('slug') or project_id}"))
        details = t("search_by", author=hit.get("author", "?")) + "  ·  " + \
            t("search_downloads", n=compact_number(int(hit.get("downloads") or 0)))
        ctk.CTkLabel(text, text=details, text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        ctk.CTkLabel(text, text=hit.get("description", ""), anchor="w", justify="left", wraplength=440).pack(fill="x")
        self.rows[project_id] = {"hit": hit, "button": button, "icon": icon_label}

    # ----- install ----------------------------------------------------------- #

    def _install(self, project_id: str):
        row = self.rows.get(project_id)
        if not row or self.app.busy:
            return
        button = row["button"]
        button.configure(state="disabled", text=t("search_installing"))

        def done(mods: List[core.ModInfo]):
            failed = [m for m in mods if m.status == core.STATUS_FAILED]
            if self.winfo_exists():
                if failed:
                    button.configure(state="normal", text=t("search_install"))
                else:
                    button.configure(text=t("search_installed"), fg_color="transparent", border_width=1,
                                     text_color=("gray10", "gray90"))
                    self.installed |= {m.project_id for m in mods}

        def failed(err: Exception):
            if self.winfo_exists():
                button.configure(state="normal", text=t("search_install"))
            messagebox.showerror(t("search_title"), t("search_failed", mod=row["hit"].get("title", "?"), error=err),
                                 parent=self if self.winfo_exists() else self.app)

        self.app.install_projects(row["hit"], self.game_version, self.loaders, done, failed, parent=self)


class CompareDialog(Dialog):
    """What is different between the current profile and another one (for example client and server)."""

    def __init__(self, app: "App"):
        super().__init__(app, t("compare_title"), 680, 600)
        self.app = app
        self.profile = app.current_profile() or {}
        content = self.profile.get("content", core.CONTENT_MODS)
        self.others = {p["name"]: p for p in app.config_data["profiles"]
                       if p is not self.profile and p.get("content", core.CONTENT_MODS) == content}
        ctk.CTkLabel(self, text=t("compare_title"), font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text=t("compare_hint"), text_color=MUTED, wraplength=630, justify="left",
                     anchor="w").pack(fill="x", padx=22)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(12, 0))
        ctk.CTkLabel(row, text=f"{self.profile.get('name', '')}   ⟷").pack(side="left", padx=(0, 8))
        names = list(self.others)
        self.other_var = tk.StringVar(value=names[0] if names else "")
        ctk.CTkOptionMenu(row, variable=self.other_var, values=names or [""], width=220,
                          state="normal" if names else "disabled").pack(side="left")
        self.go_btn = ctk.CTkButton(row, text=t("compare_go"), width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                    state="normal" if names else "disabled", command=self._compare)
        self.go_btn.pack(side="left", padx=8)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=22, pady=12)
        ctk.CTkButton(self, text=t("close"), width=110, command=self.destroy).pack(anchor="e", padx=22, pady=(0, 18))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._message(t("compare_pick") if names else t("compare_no_others"))

    def _message(self, text: str):
        for child in self.list.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.list, text=text, text_color=MUTED, wraplength=600, justify="left").pack(
            padx=12, pady=16, anchor="w")

    def _compare(self):
        other = self.others.get(self.other_var.get())
        if not other:
            return
        self.go_btn.configure(state="disabled")
        self._message(t("compare_working"))
        content = self.profile.get("content", core.CONTENT_MODS)
        self.app.run_task(lambda: modpack.compare_folders(self.app.client, self.profile["path"], other["path"],
                                                          content),
                          lambda diffs: self._show(diffs, other["name"]), self._failed)

    def _failed(self, err: Exception):
        if self.winfo_exists():
            self.go_btn.configure(state="normal")
            self._message(str(err))

    def _show(self, diffs: List[modpack.Difference], other_name: str):
        if not self.winfo_exists():
            return
        self.go_btn.configure(state="normal")
        for child in self.list.winfo_children():
            child.destroy()
        mine = self.profile.get("name", "")
        groups = [(modpack.DIFFERENT, t("compare_different")), (modpack.ONLY_A, t("compare_only", name=mine)),
                  (modpack.ONLY_B, t("compare_only", name=other_name))]
        shown = False
        for kind, title in groups:
            items = [d for d in diffs if d.kind == kind]
            if not items:
                continue
            shown = True
            ctk.CTkLabel(self.list, text=f"{title}  ({len(items)})", font=ctk.CTkFont(size=14, weight="bold"),
                         anchor="w").pack(fill="x", padx=10, pady=(10, 2))
            for d in items:
                line = ctk.CTkFrame(self.list, fg_color="transparent")
                line.pack(fill="x", padx=10, pady=1)
                ctk.CTkLabel(line, text=d.name, anchor="w").pack(side="left")
                detail = (f"{d.version_a}  ⟷  {d.version_b}" if kind == modpack.DIFFERENT
                          else (d.version_a or d.version_b))
                if d.side:
                    detail = t(f"compare_{d.side}_only") + "  ·  " + detail
                ctk.CTkLabel(line, text=detail, text_color=MUTED, anchor="e").pack(side="right")
        same = sum(1 for d in diffs if d.kind == modpack.SAME)
        if not shown:
            self._message(t("compare_identical"))
        elif same:
            ctk.CTkLabel(self.list, text=t("compare_same", n=same), text_color=MUTED, anchor="w").pack(
                fill="x", padx=10, pady=(12, 4))


class MigrationDialog(Dialog):
    """Check which mods are ready for another Minecraft version and move the profile to it."""

    def __init__(self, app: "App"):
        super().__init__(app, t("migrate_title"), 660, 600)
        self.app = app
        profile = app.current_profile() or {}
        self.profile = profile
        self.plan: Optional[core.MigrationPlan] = None
        ctk.CTkLabel(self, text=t("migrate_title"), font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text=t("migrate_hint"), text_color=MUTED, wraplength=610, justify="left",
                     anchor="w").pack(fill="x", padx=22)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(12, 0))
        ctk.CTkLabel(row, text="Minecraft").pack(side="left", padx=(0, 8))
        versions = [v for v in app.version_choices() if v != t("auto")]
        current = profile.get("game_version", core.AUTO)
        self.version_var = tk.StringVar(value=versions[0] if versions else "")
        self.version_box = ctk.CTkComboBox(row, variable=self.version_var, values=versions, width=160)
        self.version_box.pack(side="left")
        self.check_btn = ctk.CTkButton(row, text=t("migrate_check"), width=120, command=self._check)
        self.check_btn.pack(side="left", padx=8)
        if current != core.AUTO:
            ctk.CTkLabel(row, text=t("migrate_current", version=current), text_color=MUTED).pack(side="left", padx=8)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.list.pack(fill="both", expand=True, padx=22, pady=12)
        self.summary = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=610)
        self.summary.pack(fill="x", padx=22)
        self.disable_var = tk.BooleanVar(value=True)
        self.disable_switch = ctk.CTkSwitch(self, text=t("migrate_disable_missing"), variable=self.disable_var,
                                            progress_color=ACCENT, state="disabled")
        self.disable_switch.pack(anchor="w", padx=22, pady=(8, 0))
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(10, 18))
        self.migrate_btn = ctk.CTkButton(buttons, text=t("migrate_go", version="…"), fg_color=ACCENT,
                                         hover_color=ACCENT_HOVER, state="disabled", command=self._migrate)
        self.migrate_btn.pack(side="right")
        ctk.CTkButton(buttons, text=t("cancel"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._message(t("migrate_pick"))

    def _message(self, text: str):
        for child in self.list.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.list, text=text, text_color=MUTED, wraplength=560, justify="left").pack(
            padx=12, pady=16, anchor="w")

    def _check(self):
        target = self.version_var.get().strip()
        if not target or self.app.busy:
            return
        self.plan = None
        self.check_btn.configure(state="disabled")
        self.migrate_btn.configure(state="disabled", text=t("migrate_go", version=target))
        self.summary.configure(text="")
        self._message(t("migrate_checking", version=target))
        profile = self.profile
        allow_beta = self.app.config_data["allow_beta"]
        self.app.run_task(
            lambda: core.plan_migration(self.app.client, profile["path"], profile.get("loader", core.AUTO), target,
                                        allow_beta, profile.get("content", core.CONTENT_MODS)),
            self._show, self._failed)

    def _failed(self, err: Exception):
        if self.winfo_exists():
            self.check_btn.configure(state="normal")
            self._message(str(err))

    def _show(self, plan: core.MigrationPlan):
        if not self.winfo_exists():
            return
        self.plan = plan
        self.check_btn.configure(state="normal")
        for child in self.list.winfo_children():
            child.destroy()
        rows: List[Tuple[str, str, Any]] = []
        for mod in sorted(plan.missing, key=lambda m: m.display_name.lower()):
            rows.append(("✖  " + mod.display_name, t("migrate_not_ready"), DANGER))
        for mod in sorted(plan.dependencies, key=lambda m: m.display_name.lower()):
            rows.append(("＋  " + mod.display_name, t("migrate_dependency", version=mod.latest_version), ACCENT))
        for mod in sorted(plan.ready, key=lambda m: m.display_name.lower()):
            detail = (f"{mod.current_version}  →  {mod.latest_version}" if mod.status == core.STATUS_UPDATE
                      else t("migrate_compatible"))
            rows.append(("✔  " + mod.display_name, detail, ACCENT))
        for mod in sorted(plan.unknown, key=lambda m: m.display_name.lower()):
            rows.append(("?  " + mod.display_name, t("migrate_unknown"), MUTED))
        if not rows:
            self._message(t("no_files"))
        for name, detail, color in rows:
            line = ctk.CTkFrame(self.list, fg_color="transparent")
            line.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(line, text=name, anchor="w", text_color=color).pack(side="left")
            ctk.CTkLabel(line, text=detail, anchor="e", text_color=MUTED).pack(side="right")
        total = len(plan.ready) + len(plan.missing)
        text = t("migrate_summary", ready=len(plan.ready), total=total, version=plan.target)
        if plan.missing:
            text += "\n" + t("migrate_missing_note", n=len(plan.missing))
        self.summary.configure(text=text, text_color=DANGER if plan.missing else ACCENT)
        self.disable_switch.configure(state="normal" if plan.missing else "disabled")
        self.migrate_btn.configure(state="normal" if plan.ready or plan.dependencies else "disabled",
                                   text=t("migrate_go", version=plan.target))

    def _migrate(self):
        if not self.plan:
            return
        plan, disable = self.plan, bool(self.disable_var.get()) and bool(self.plan.missing)
        self.destroy()
        self.app.migrate_profile(plan, disable)


class BackupsDialog(Dialog):
    """List the backups of the current profile and undo the latest update."""

    def __init__(self, app: "App"):
        super().__init__(app, t("backups_title"), 620, 500)
        self.app = app
        profile = app.current_profile()
        self.folder = profile["path"] if profile else ""
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
        if not self.app.confirm_game_closed(self.folder, parent=self):
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
        ctk.CTkButton(buttons, text=t("import_mrpack_btn"), fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._import_mrpack).pack(side="left")
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

    def _import_mrpack(self):
        path = filedialog.askopenfilename(parent=self, title=t("import_mrpack_btn"),
                                          filetypes=[("Modrinth modpack", "*.mrpack"), ("*", "*")])
        if not path:
            return
        game_dir = filedialog.askdirectory(parent=self, title=t("mrpack_pick_folder"), mustexist=False)
        if not game_dir:
            return
        game_dir = os.path.normpath(game_dir)
        if os.path.isdir(game_dir) and os.listdir(game_dir) and not messagebox.askyesno(
                t("import_title"), t("mrpack_folder_not_empty", path=game_dir), icon="warning", parent=self):
            return
        self.destroy()
        self.app.import_mrpack(path, game_dir)

    def _refresh_button(self):
        n = sum(1 for var, _inst in self.choices if var.get())
        self.import_btn.configure(text=t("import_selected", n=n), state="normal" if n else "disabled")

    def _import(self):
        self.result = [inst for var, inst in self.choices if var.get()]
        self.destroy()


class SettingsDialog(Dialog):
    def __init__(self, app: "App"):
        super().__init__(app, t("settings"), 600, 620)
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
        self.language_var = tk.StringVar(value=languages.get(cfg.get("language", i18n.SYSTEM), languages[i18n.SYSTEM]))
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

        ghost = dict(fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(anchor="w", pady=(22, 0))
        ctk.CTkButton(actions, text=t("open_config_folder"), command=lambda: open_folder(core.CONFIG_DIR),
                      **ghost).pack(side="left")
        ctk.CTkButton(actions, text=t("open_log"), command=lambda: open_folder(core.LOG_FILE),
                      **ghost).pack(side="left", padx=8)
        more = ctk.CTkFrame(body, fg_color="transparent")
        more.pack(anchor="w", pady=(8, 0))
        ctk.CTkButton(more, text=t("shortcuts_btn"), command=app.show_shortcuts, **ghost).pack(side="left")
        ctk.CTkButton(more, text=t("reset_all"), fg_color=DANGER, hover_color=DANGER_HOVER,
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
