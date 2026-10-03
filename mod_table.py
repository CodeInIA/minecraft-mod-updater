"""The mod table: rows with checkbox + icon + name, sorting, links, hover and the right-click menu."""

import os
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple, cast

import customtkinter as ctk

import mod_icons
import updater_core as core
from dialogs import ChangelogDialog, VersionPickerDialog
from i18n import t
from mod_icons import IconCache
from ui_common import (
    ACCENT,
    SIDEBAR_BG,
    STATUS_ORDER,
    TREE_ITEM_PADDING,
    is_dark,
    mod_warnings,
    open_folder,
    pick,
    row_status,
    ui_font_family,
)

if TYPE_CHECKING:
    from mod_updater import App


class ModTableMixin:
    """Part of App: what the mod table shows and how it reacts to the mouse."""

    # Provided by App (declared here for type checkers)
    config_data: Dict[str, Any]
    busy: bool
    mods: List[core.ModInfo]
    checked: Set[str]
    last_scan: Optional[core.ScanResult]
    icons: IconCache
    sort_key: Tuple[str, bool]
    tree: ttk.Treeview
    search_entry: ctk.CTkEntry
    select_all_var: tk.BooleanVar
    select_all_box: ctk.CTkCheckBox
    update_btn: ctk.CTkButton
    summary_label: ctk.CTkLabel
    status_label: ctk.CTkLabel
    detected_label: ctk.CTkLabel
    progress: ctk.CTkProgressBar
    _row_tags: Dict[str, List[str]]
    _hover_row: Optional[str]
    _tooltip: Optional[tk.Toplevel]
    _tooltip_label: tk.Label
    _tree_font: tkfont.Font
    current_profile: Callable[[], Optional[Dict[str, Any]]]
    confirm_game_closed: Callable[..., bool]

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
        if counts[core.STATUS_PINNED]:
            parts.append(t("sum_pinned", n=counts[core.STATUS_PINNED]))
        if counts[core.STATUS_IGNORED]:
            parts.append(t("sum_ignored", n=counts[core.STATUS_IGNORED]))
        problems = sum(1 for m in self.mods if m.has_problems)
        if problems:
            parts.append(t("sum_problems", n=problems))
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
            menu.add_command(label=t("menu_choose_version"),
                             command=lambda: VersionPickerDialog(cast("App", self), mod))
            if mod.status == core.STATUS_PINNED:
                menu.add_command(label=t("menu_unpin"), command=lambda: self.unpin(mod))
            ignored = mod.status == core.STATUS_IGNORED
            menu.add_command(label=t("menu_unignore") if ignored else t("menu_ignore"),
                             command=lambda: self.set_ignored(mod, not ignored))
        if os.path.exists(mod.path) and not self.busy:
            menu.add_command(label=t("menu_enable") if mod.disabled else t("menu_disable"),
                             command=lambda: self.set_enabled(mod, mod.disabled))
        if os.path.exists(mod.path):
            menu.add_command(label=t("menu_show_file"), command=lambda: open_folder(os.path.dirname(mod.path)))
        if menu.index("end") is not None:
            menu.tk_popup(event.x_root, event.y_root)

    def set_enabled(self, mod: core.ModInfo, enabled: bool):
        """Enable or disable a mod: the game skips files that end in .disabled."""
        if self.busy or not self.confirm_game_closed(os.path.dirname(mod.path)):
            return
        old_path = mod.path
        try:
            core.set_enabled(mod, enabled)
        except OSError as e:
            messagebox.showerror(t("menu_enable") if enabled else t("menu_disable"),
                                 t("toggle_failed", file=os.path.basename(old_path), error=e.strerror or e))
            return
        if old_path in self.checked:
            self.checked.discard(old_path)
            self.checked.add(mod.path)
        self._fill_tree()
        self.status_label.configure(text=t("mod_enabled" if enabled else "mod_disabled", mod=mod.display_name))

    def _on_tree_double_click(self, event):
        mod, area = self._hit_area(event)
        if mod and area == "row" and mod.latest and self.last_scan:
            self.show_changelog(mod)

    def show_changelog(self, mod: core.ModInfo):
        scan = self.last_scan
        ChangelogDialog(cast("App", self), mod, (scan.game_version or "") if scan else "", scan.loaders if scan else [])

    def unpin(self, mod: core.ModInfo):
        """Let a pinned mod be updated again."""
        profile = self.current_profile()
        if not profile:
            return
        profile.setdefault("pinned", {}).pop(mod.project_id, None)
        core.save_config(self.config_data)
        self._restore_status(mod)

    def _restore_status(self, mod: core.ModInfo):
        scan = self.last_scan
        mod.status = core.determine_status(mod, (scan.game_version or "") if scan else "", scan.loaders if scan else [])
        if mod.actionable:
            self.checked.add(mod.path)
        self._fill_tree()
        self._update_summary()

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
        if not ignored:
            pinned = mod.project_id in profile.get("pinned", {})
            if pinned:
                mod.status = core.STATUS_PINNED
                self._fill_tree()
                self._update_summary()
            else:
                self._restore_status(mod)
            return
        mod.status = core.STATUS_IGNORED
        self.checked.discard(mod.path)
        self._fill_tree()
        self._update_summary()

    def _sort_by(self, column: str):
        key, reverse = self.sort_key
        self.sort_key = (column, not reverse if key == column else False)
        self._fill_tree()

    def _set_link_hover(self, event, text: Optional[str] = None):
        """Tooltip under the mouse: "Open in Modrinth" (with a hand cursor) over a mod name, or `text`."""
        if event is None:
            self.tree.configure(cursor="")
            if self._tooltip and self._tooltip.winfo_exists():
                self._tooltip.withdraw()
            return
        if not self._tooltip or not self._tooltip.winfo_exists():
            self._tooltip = tk.Toplevel(cast("App", self))
            self._tooltip.overrideredirect(True)
            self._tooltip.attributes("-topmost", True)
            self._tooltip_label = tk.Label(self._tooltip, padx=8, pady=3, font=(ui_font_family(), 9))
            self._tooltip_label.pack()
        self._tooltip_label.configure(text=text or t("open_in_modrinth") + "  ↗", bg=pick(SIDEBAR_BG),
                                      fg="#E8EAED" if is_dark() else "#1F2328", justify="left", wraplength=420)
        self._tooltip.geometry(f"+{event.x_root + 14}+{event.y_root + 18}")
        self._tooltip.deiconify()
        self.tree.configure(cursor="" if text else "hand2")

    def _on_tree_motion(self, event):
        mod, area = self._hit_area(event)
        warnings = mod_warnings(mod, detailed=True) if mod and area == "row" else []
        if area == "link" and mod.page_url:
            self._set_link_hover(event)
        elif warnings and self.tree.identify_column(event.x) == "#3":  # the status column
            self._set_link_hover(event, "\n".join("⚠ " + w for w in warnings))
        else:
            self._set_link_hover(None)
        row = self.tree.identify_row(event.y)
        previous = getattr(self, "_hover_row", None)
        if row == previous:
            return
        if previous and self.tree.exists(previous):
            self.tree.item(previous, tags=self._row_tags.get(previous, []))
        if row:
            self.tree.item(row, tags=[t for t in self._row_tags.get(row, []) if t != "odd"] + ["hover"])
        self._hover_row = row
