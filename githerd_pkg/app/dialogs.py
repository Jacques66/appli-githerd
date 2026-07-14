# -*- coding: utf-8 -*-
"""
GitHerd — App dialogs mixin.

Handles global settings, about, and help dialogs.
"""

from tkinter import filedialog, messagebox
import customtkinter as ctk

from ..config import (
    load_global_settings, save_global_settings,
    APPEARANCE_MODES, COLOR_THEMES
)
from ..git_utils import get_tracked_branches, delete_remote_branch
from ..resources import HELP_TEXT


class AppDialogsMixin:
    """Mixin for global dialogs."""

    def show_global_settings(self, active_section=None):
        """Show global settings dialog.

        Two-pane layout: a section list on the left, the selected
        section's content on the right. `active_section` lets callers
        reopen on the same section after a theme/zoom rebuild.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("680x520")
        dialog.transient(self)
        dialog.wait_visibility()
        dialog.grab_set()
        dialog.resizable(False, False)
        self.ensure_dialog_on_screen(dialog)

        # --- overall structure: [nav | content] on top, buttons below --
        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=15, pady=(15, 0))

        nav = ctk.CTkFrame(body, width=150)
        nav.pack(side="left", fill="y", padx=(0, 12))
        nav.pack_propagate(False)

        content = ctk.CTkFrame(body)
        content.pack(side="left", fill="both", expand=True)

        # One frame per section; only the active one is packed.
        section_order = ["Appearance", "Git", "General", "Sync", "Automation"]
        sections = {name: ctk.CTkFrame(content, fg_color="transparent")
                    for name in section_order}

        nav_buttons = {}

        def show_section(name):
            for other in sections.values():
                other.pack_forget()
            sections[name].pack(fill="both", expand=True, padx=12, pady=12)
            for bn, btn in nav_buttons.items():
                if bn == name:
                    btn.configure(fg_color=("#3a7ebf", "#1f6aa5"))
                else:
                    btn.configure(fg_color="transparent")

        for name in section_order:
            b = ctk.CTkButton(
                nav, text=name, anchor="w", fg_color="transparent",
                command=lambda n=name: show_section(n),
            )
            b.pack(fill="x", pady=2)
            nav_buttons[name] = b

        def section_title(parent, text):
            ctk.CTkLabel(parent, text=text,
                         font=ctk.CTkFont(size=15, weight="bold")).grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # ============================ APPEARANCE ============================
        appf = sections["Appearance"]
        section_title(appf, "Appearance")

        ctk.CTkLabel(appf, text="Mode:").grid(row=1, column=0, sticky="w", pady=8)
        appearance_var = ctk.StringVar(value=self.global_settings.get("appearance_mode", "dark"))

        def on_appearance_change(mode):
            ctk.set_appearance_mode(mode)
            self.update_menu_colors(mode)

        appearance_menu = ctk.CTkOptionMenu(
            appf, variable=appearance_var, values=APPEARANCE_MODES,
            width=150, command=on_appearance_change)
        appearance_menu.grid(row=1, column=1, sticky="w", pady=8, padx=(10, 0))

        ctk.CTkLabel(appf, text="Color:").grid(row=2, column=0, sticky="w", pady=8)
        theme_var = ctk.StringVar(value=self.global_settings.get("color_theme", "blue"))

        def on_theme_change(new_theme):
            if new_theme != self.global_settings.get("color_theme"):
                self.global_settings["color_theme"] = new_theme
                save_global_settings(self.global_settings)
                dialog.destroy()
                self.rebuild_ui()
                self.after(150, lambda: self.show_global_settings("Appearance"))

        theme_menu = ctk.CTkOptionMenu(
            appf, variable=theme_var, values=COLOR_THEMES,
            width=150, command=on_theme_change)
        theme_menu.grid(row=2, column=1, sticky="w", pady=8, padx=(10, 0))

        ctk.CTkLabel(appf, text="Font zoom:").grid(row=3, column=0, sticky="w", pady=8)
        zoom_var = ctk.DoubleVar(value=self.global_settings.get("font_zoom", 1.0))
        zoom_frame = ctk.CTkFrame(appf, fg_color="transparent")
        zoom_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=8, padx=(10, 0))
        zoom_slider = ctk.CTkSlider(zoom_frame, from_=0.8, to=2.0,
                                    number_of_steps=12, variable=zoom_var, width=120)
        zoom_slider.pack(side="left")
        zoom_label = ctk.CTkLabel(zoom_frame, text=f"{zoom_var.get():.1f}x", width=40)
        zoom_label.pack(side="left", padx=(5, 0))
        zoom_timer = [None]

        def on_zoom_change(val):
            zoom_label.configure(text=f"{float(val):.1f}x")
            if zoom_timer[0]:
                dialog.after_cancel(zoom_timer[0])
            def apply_zoom():
                new_zoom = float(val)
                if abs(new_zoom - self.global_settings.get("font_zoom", 1.0)) > 0.01:
                    self.global_settings["font_zoom"] = new_zoom
                    save_global_settings(self.global_settings)
                    dialog.destroy()
                    self.rebuild_ui()
                    self.after(150, lambda: self.show_global_settings("Appearance"))
            zoom_timer[0] = dialog.after(500, apply_zoom)

        zoom_slider.configure(command=on_zoom_change)

        # =============================== GIT ================================
        gitf = sections["Git"]
        section_title(gitf, "Git")
        ctk.CTkLabel(gitf, text="Executable:").grid(row=1, column=0, sticky="w", pady=8)
        git_entry = ctk.CTkEntry(gitf, width=250)
        git_entry.insert(0, self.global_settings.get("git_binary", "git"))
        git_entry.grid(row=1, column=1, sticky="ew", pady=8, padx=(10, 5))

        def browse_git():
            path = filedialog.askopenfilename(
                title="Select Git executable", filetypes=[("Executables", "*")])
            if path:
                git_entry.delete(0, "end")
                git_entry.insert(0, path)

        ctk.CTkButton(gitf, text="📂", width=40, command=browse_git).grid(
            row=1, column=2, pady=8)
        gitf.columnconfigure(1, weight=1)

        # ============================= GENERAL =============================
        genf = sections["General"]
        section_title(genf, "General")
        grow = 1

        auto_poll_var = ctk.BooleanVar(value=self.global_settings.get("auto_start_polling", False))
        ctk.CTkCheckBox(genf, text="Auto-start polling",
                       variable=auto_poll_var).grid(row=grow, column=0, columnspan=3, sticky="w", pady=6)
        grow += 1

        collapsed_var = ctk.BooleanVar(value=self.global_settings.get("start_collapsed", False))
        ctk.CTkCheckBox(genf, text="Start with log collapsed",
                       variable=collapsed_var).grid(row=grow, column=0, columnspan=3, sticky="w", pady=6)
        grow += 1

        advanced_var = ctk.BooleanVar(value=self.global_settings.get("advanced_mode", False))
        ctk.CTkCheckBox(genf, text="Advanced mode (click tab=polling, double-click=sync)",
                       variable=advanced_var).grid(row=grow, column=0, columnspan=3, sticky="w", pady=6)
        grow += 1

        notif_var = ctk.BooleanVar(value=self.global_settings.get("desktop_notifications", True))
        ctk.CTkCheckBox(genf, text="Desktop notifications (notify-send)",
                       variable=notif_var).grid(row=grow, column=0, columnspan=3, sticky="w", pady=6)
        grow += 1

        restore_poll_var = ctk.BooleanVar(value=self.global_settings.get("restore_polling", False))
        ctk.CTkCheckBox(genf, text="Restore polling state on restart",
                       variable=restore_poll_var).grid(row=grow, column=0, columnspan=3, sticky="w", pady=6)
        grow += 1

        # =============================== SYNC ==============================
        syncf = sections["Sync"]
        section_title(syncf, "Sync")
        srow = 1

        sync_new_var = ctk.BooleanVar(value=self.global_settings.get("sync_new_branches_by_default", False))
        ctk.CTkCheckBox(syncf, text="Enable sync for newly discovered branches",
                       variable=sync_new_var).grid(row=srow, column=0, columnspan=3, sticky="w", pady=6)
        srow += 1

        ctk.CTkLabel(syncf, text="Recent activity entries kept:").grid(
            row=srow, column=0, sticky="w", pady=6)
        recent_limit_var = ctk.StringVar(value=str(self.global_settings.get("recent_sync_limit", 5)))
        ctk.CTkOptionMenu(syncf, variable=recent_limit_var,
                         values=["3", "5", "10", "20"], width=80).grid(
            row=srow, column=1, sticky="w", pady=6)
        srow += 1

        ctk.CTkLabel(syncf, text="Default polling interval (sec) for new repos:").grid(
            row=srow, column=0, sticky="w", pady=6)
        default_interval_entry = ctk.CTkEntry(syncf, width=80)
        default_interval_entry.insert(0, str(self.global_settings.get("default_interval_seconds", 60)))
        default_interval_entry.grid(row=srow, column=1, sticky="w", pady=6)
        srow += 1

        # ============================ AUTOMATION ===========================
        autof = sections["Automation"]
        section_title(autof, "Polling automation")
        arow = 1

        auto_retry_var = ctk.BooleanVar(value=self.global_settings.get("auto_retry_errored", False))
        ctk.CTkCheckBox(autof, text="Auto-retry repos in error (reconnect)",
                       variable=auto_retry_var).grid(row=arow, column=0, columnspan=3, sticky="w", pady=6)
        arow += 1

        ctk.CTkLabel(autof, text="Auto-retry interval (sec):").grid(
            row=arow, column=0, sticky="w", pady=6)
        auto_retry_interval_entry = ctk.CTkEntry(autof, width=80)
        auto_retry_interval_entry.insert(0, str(self.global_settings.get("auto_retry_interval_seconds", 60)))
        auto_retry_interval_entry.grid(row=arow, column=1, sticky="w", pady=6)
        arow += 1

        ctk.CTkLabel(autof, text="Watch idle repos, start on change (sec, 0=off):").grid(
            row=arow, column=0, sticky="w", pady=6)
        watch_idle_entry = ctk.CTkEntry(autof, width=80)
        watch_idle_entry.insert(0, str(self.global_settings.get("watch_idle_interval_seconds", 0)))
        watch_idle_entry.grid(row=arow, column=1, sticky="w", pady=6)
        arow += 1

        ctk.CTkLabel(autof, text="Disable polling after inactivity (hours, 0=off):",
                     text_color="#e05555").grid(row=arow, column=0, sticky="w", pady=6)
        inactivity_entry = ctk.CTkEntry(autof, width=80)
        inactivity_entry.insert(0, str(self.global_settings.get("inactivity_disable_hours", 24)))
        inactivity_entry.grid(row=arow, column=1, sticky="w", pady=6)
        arow += 1

        # Show the requested (or first) section.
        show_section(active_section if active_section in sections else "Appearance")

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)

        def save_settings():
            old_advanced = self.global_settings.get("advanced_mode", False)
            new_advanced = advanced_var.get()

            self.global_settings["appearance_mode"] = appearance_var.get()
            self.global_settings["git_binary"] = git_entry.get().strip()
            self.global_settings["auto_start_polling"] = auto_poll_var.get()
            self.global_settings["start_collapsed"] = collapsed_var.get()
            self.global_settings["advanced_mode"] = new_advanced
            self.global_settings["desktop_notifications"] = notif_var.get()
            self.global_settings["restore_polling"] = restore_poll_var.get()
            self.global_settings["sync_new_branches_by_default"] = sync_new_var.get()
            try:
                new_recent_limit = int(recent_limit_var.get())
            except ValueError:
                new_recent_limit = 5
            self.global_settings["recent_sync_limit"] = new_recent_limit
            self._resize_recent_events(new_recent_limit)
            try:
                new_default_interval = max(1, int(default_interval_entry.get().strip()))
            except (ValueError, AttributeError):
                new_default_interval = 60
            self.global_settings["default_interval_seconds"] = new_default_interval
            self.global_settings["auto_retry_errored"] = auto_retry_var.get()
            try:
                new_retry_interval = max(5, int(auto_retry_interval_entry.get().strip()))
            except (ValueError, AttributeError):
                new_retry_interval = 60
            self.global_settings["auto_retry_interval_seconds"] = new_retry_interval
            try:
                new_watch_idle = max(0, int(watch_idle_entry.get().strip()))
            except (ValueError, AttributeError):
                new_watch_idle = 0
            self.global_settings["watch_idle_interval_seconds"] = new_watch_idle
            try:
                new_inactivity = max(0, float(inactivity_entry.get().strip()))
            except (ValueError, AttributeError):
                new_inactivity = 24
            self.global_settings["inactivity_disable_hours"] = new_inactivity

            try:
                save_global_settings(self.global_settings)
            except Exception as e:
                messagebox.showerror("Error", f"Unable to save: {e}", parent=dialog)
                return

            dialog.destroy()

            # Rebuild UI if advanced mode changed
            if old_advanced != new_advanced:
                self.rebuild_ui()

        # Right-aligned, order Cancel then Save. Pack Save first at the
        # right edge, then Cancel to its left → visual: [Cancel][Save].
        ctk.CTkButton(btn_frame, text="Save", command=save_settings).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)

    def show_about(self):
        """Show about dialog."""
        about_win = ctk.CTkToplevel(self)
        about_win.title("About GitHerd")
        about_win.geometry("400x400")
        about_win.transient(self)
        about_win.wait_visibility()
        about_win.grab_set()
        about_win.resizable(False, False)
        self.ensure_dialog_on_screen(about_win)

        # Main frame
        frame = ctk.CTkFrame(about_win)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(
            frame,
            text="GitHerd",
            font=ctk.CTkFont(size=28, weight="bold")
        ).pack(pady=(20, 5))

        # Version
        ctk.CTkLabel(
            frame,
            text="Version 1.0",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        ).pack()

        # Description
        ctk.CTkLabel(
            frame,
            text="Real-time Git branch synchronizer",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            frame,
            text="Keeps multiple Git branches aligned in real-time.\nIdeal for parallel AI coding sessions.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="center"
        ).pack()

        # Copyright
        ctk.CTkLabel(
            frame,
            text="© 2026 InZeMobile — Jacques Lovi",
            font=ctk.CTkFont(size=12)
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            frame,
            text="All rights reserved",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack()

        # Close button
        ctk.CTkButton(about_win, text="Close", command=about_win.destroy, width=100).pack(pady=15)

    def show_help(self):
        """Show help dialog."""
        help_win = ctk.CTkToplevel(self)
        help_win.title("Help — GitHerd")
        help_win.geometry("700x600")
        help_win.transient(self)
        help_win.wait_visibility()
        help_win.grab_set()
        self.ensure_dialog_on_screen(help_win)

        text = ctk.CTkTextbox(help_win, font=ctk.CTkFont(family="Consolas", size=12))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")

        ctk.CTkButton(help_win, text="Close", command=help_win.destroy).pack(pady=10)

    def add_repo_dialog(self):
        """Show add repository dialog."""
        from pathlib import Path
        from ..git_utils import is_git_repo, detect_repo_settings
        from ..config import save_repo_config

        path = filedialog.askdirectory(
            title="Select a Git repository",
            mustexist=True
        )
        if path:
            git = self.global_settings.get("git_binary", "git")
            if not is_git_repo(path, git):
                messagebox.showerror(
                    "Error",
                    f"'{path}' is not a valid Git repository.",
                    parent=self
                )
                return
            known = self.find_known_repo(path)
            if known is not None:
                existing_raw, kind = known
                name = self.get_tab_display_name(existing_raw)
                if kind == "open":
                    msg = f"This repository is already open as “{name}”."
                else:
                    msg = (
                        f"This repository is already known as “{name}” "
                        f"(currently in Repository → Inactive repos)."
                    )
                messagebox.showinfo(
                    "Repository already known", msg, parent=self,
                )
                return

            detected = detect_repo_settings(path, git)
            # Apply the user-configured default polling interval to
            # newly added repos (only when no githerd.toml already
            # exists — an existing config wins).
            detected["interval_seconds"] = self.global_settings.get(
                "default_interval_seconds", 60
            )
            config_file = Path(path) / "githerd.toml"
            if not config_file.exists():
                save_repo_config(path, detected)

            self.add_repo(path)
            self.save_current_repos()

    # ------------------------------------------------------------------
    # Branch sync / delete dialogs (replace the inline Repository menu
    # branch lists)
    # ------------------------------------------------------------------

    def _branch_dialog_skeleton(self, tab, title, geometry):
        """Build the common parts of the two branch dialogs.

        Returns (dialog, master, list_frame, vars_by_name, short_names,
        btn_frame) or None if there are no branches to show. The
        caller is expected to populate `vars_by_name`, then pack its
        Save/Cancel/Delete buttons into `btn_frame`.
        """
        try:
            branches = get_tracked_branches(tab.remote, tab.prefix,
                                            cwd=tab.repo_path, git=tab.git)
        except Exception:
            branches = []
        short_names = [b.replace(f"{tab.remote}/", "") for b in branches]
        if not short_names:
            messagebox.showinfo(
                "No branches",
                f"No branches matching '{tab.prefix}*' on {tab.remote}.",
                parent=self,
            )
            return None

        # Mirror the ordering of show_global_settings (which renders
        # correctly): transient → wait_visibility → grab_set → resizable
        # → ensure_dialog_on_screen, THEN add children. Adding children
        # before the toplevel is mapped left them invisible.
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry(geometry)
        dialog.transient(self)
        dialog.wait_visibility()
        dialog.grab_set()
        dialog.resizable(False, False)
        self.ensure_dialog_on_screen(dialog)

        # Pack the button bar FIRST at the bottom so it claims its space
        # before the (expand=True) content area takes the rest.
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        outer = ctk.CTkFrame(dialog)
        outer.pack(side="top", fill="both", expand=True, padx=15, pady=(15, 0))

        # Header row: master checkbox + "(n/m)" counter + mixed glyph
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 6))
        master_var = ctk.BooleanVar(value=False)
        master = ctk.CTkCheckBox(header, text="Select all", variable=master_var)
        master.pack(side="left")
        counter_label = ctk.CTkLabel(header, text="(0/0)", text_color="gray")
        counter_label.pack(side="left", padx=(8, 0))
        mixed_glyph = ctk.CTkLabel(header, text="", width=14,
                                    text_color="#fbbf24")
        mixed_glyph.pack(side="left", padx=(4, 0))
        master._gh_var = master_var
        master._gh_counter = counter_label
        master._gh_mixed = mixed_glyph

        # List of per-branch checkboxes
        list_frame = ctk.CTkFrame(outer)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        vars_by_name = {}
        return dialog, master, list_frame, vars_by_name, short_names, btn_frame

    def _wire_master_checkbox(self, master, vars_by_name):
        """Bind master ↔ individual checkboxes with mixed-state visual.

        Returns recompute_master() the caller invokes whenever an
        individual var changes.
        """
        master_var = master._gh_var
        counter = master._gh_counter
        mixed_glyph = master._gh_mixed

        def recompute_master():
            n = sum(1 for v in vars_by_name.values() if v.get())
            m = len(vars_by_name)
            counter.configure(text=f"({n}/{m})")
            if n == 0:
                master_var.set(False)
                mixed_glyph.configure(text="")
            elif n == m:
                master_var.set(True)
                mixed_glyph.configure(text="")
            else:
                master_var.set(False)
                mixed_glyph.configure(text="—")

        def on_master_click():
            target = master_var.get()
            for v in vars_by_name.values():
                v.set(target)
            recompute_master()

        master.configure(command=on_master_click)
        return recompute_master

    def show_branch_sync_dialog(self, tab):
        """Bulk toggle which branches participate in sync.

        Save / Cancel explicit; Esc cancels.
        """
        skel = self._branch_dialog_skeleton(
            tab, f"Sync branches — {tab.tab_name}", "440x500"
        )
        if skel is None:
            return
        dialog, master, list_frame, vars_by_name, short_names, btn_frame = skel

        settings = load_global_settings()
        branch_states = settings.get("branch_update_enabled", {}).get(
            str(tab.repo_path), {}
        )
        default_enabled = settings.get("sync_new_branches_by_default", False)

        recompute_master = self._wire_master_checkbox(master, vars_by_name)

        for name in short_names:
            v = ctk.BooleanVar(
                value=branch_states.get(name, default_enabled)
            )
            vars_by_name[name] = v
            ctk.CTkCheckBox(
                list_frame, text=name, variable=v,
                command=recompute_master,
            ).pack(anchor="w", padx=8, pady=2)

        recompute_master()

        def save():
            s = load_global_settings()
            all_states = s.setdefault("branch_update_enabled", {})
            repo_states = all_states.setdefault(str(tab.repo_path), {})
            for name, var in vars_by_name.items():
                repo_states[name] = bool(var.get())
            save_global_settings(s)
            self.update_repo_menu()
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Save", command=save).pack(
            side="left", padx=5
        )
        ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=5
        )

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.focus_set()

    def show_branch_delete_dialog(self, tab):
        """Pick branches to delete remotely. Single batch confirmation.

        In advanced_mode the confirmation dialog is skipped to match
        the existing per-branch delete behavior in repo_tab/dialogs.py.
        """
        skel = self._branch_dialog_skeleton(
            tab, f"Delete branches — {tab.tab_name}", "440x500"
        )
        if skel is None:
            return
        dialog, master, list_frame, vars_by_name, short_names, btn_frame = skel

        recompute_master = self._wire_master_checkbox(master, vars_by_name)

        for name in short_names:
            v = ctk.BooleanVar(value=False)
            vars_by_name[name] = v
            ctk.CTkCheckBox(
                list_frame, text=name, variable=v,
                command=recompute_master,
            ).pack(anchor="w", padx=8, pady=2)

        recompute_master()

        def do_delete():
            selected = [name for name, v in vars_by_name.items() if v.get()]
            if not selected:
                return
            if not self.global_settings.get("advanced_mode", False):
                listing = "\n".join(f"  • {n}" for n in selected)
                if not messagebox.askyesno(
                    "Confirm deletion",
                    f"Delete {len(selected)} remote branch(es)?\n\n"
                    f"{listing}\n\nThis action is irreversible.",
                    parent=dialog,
                ):
                    return
            errors = 0
            for name in selected:
                tab.log_msg(f"Deleting {name}…")
                ok, err = delete_remote_branch(
                    name, tab.remote, cwd=tab.repo_path, git=tab.git
                )
                if ok:
                    tab.log_msg(f"Branch {name} deleted")
                else:
                    tab.log_msg(f"Error deleting {name}: {err}")
                    errors += 1
            self.update_repo_menu()
            dialog.destroy()
            if errors == 0:
                tab.manual_sync()

        ctk.CTkButton(
            btn_frame, text="Delete selected", command=do_delete,
            fg_color="#8B0000", hover_color="#CD5C5C",
        ).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=5
        )

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.focus_set()
