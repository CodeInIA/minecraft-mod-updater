"""Profile list of the sidebar: one row per profile, reordered by dragging."""

import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

import updater_core as core
from i18n import t
from ui_common import (
    ACCENT,
    ACCENT_HOVER,
    PROFILE_ROW_HEIGHT,
    PROFILE_SLOT,
    SIDEBAR_MAX_WIDTH,
    SIDEBAR_MIN_WIDTH,
    SIDEBAR_ROW_EXTRA,
    shorten_path,
)


class ProfileListMixin:
    """Part of App: the profiles in the sidebar."""

    # Provided by App (declared here for type checkers)
    config_data: Dict[str, Any]
    busy: bool
    sidebar: ctk.CTkFrame
    profile_list: ctk.CTkScrollableFrame
    profile_container: ctk.CTkFrame
    profile_rows: List[ctk.CTkFrame]
    profile_swatch: ctk.CTkFrame
    profile_title: ctk.CTkLabel
    profile_path: ctk.CTkLabel
    add_btn: ctk.CTkButton
    edit_btn: ctk.CTkButton
    delete_btn: ctk.CTkButton
    check_btn: ctk.CTkButton
    backups_btn: ctk.CTkButton
    migrate_btn: ctk.CTkButton
    _drag: Optional[Dict[str, Any]]
    _drop_slot: Optional[ctk.CTkFrame]
    _anim_job: Optional[str]
    after: Callable[..., str]
    configure: Callable[..., Any]
    winfo_containing: Callable[..., Any]
    current_profile: Callable[[], Optional[Dict[str, Any]]]
    refresh_target_bar: Callable[[], None]
    select_profile: Callable[[str], None]

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
        for w in (self.edit_btn, self.delete_btn, self.check_btn, self.backups_btn, self.migrate_btn):
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
