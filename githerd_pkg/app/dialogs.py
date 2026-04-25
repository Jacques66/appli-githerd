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
from ..resources import HELP_TEXT


class AppDialogsMixin:
    """Mixin for global dialogs."""

    def show_global_settings(self):
        """Show global settings dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("500x665")
        dialog.transient(self)
        dialog.wait_visibility()
        dialog.grab_set()
        dialog.resizable(False, False)
        self.ensure_dialog_on_screen(dialog)

        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        row = 0

        # === APPEARANCE SECTION ===
        ctk.CTkLabel(main_frame, text="Appearance", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        # Appearance mode
        ctk.CTkLabel(main_frame, text="Mode:").grid(row=row, column=0, sticky="w", pady=8)
        appearance_var = ctk.StringVar(value=self.global_settings.get("appearance_mode", "dark"))

        def on_appearance_change(mode):
            ctk.set_appearance_mode(mode)
            self.update_menu_colors(mode)

        appearance_menu = ctk.CTkOptionMenu(
            main_frame,
            variable=appearance_var,
            values=APPEARANCE_MODES,
            width=150,
            command=on_appearance_change
        )
        appearance_menu.grid(row=row, column=1, sticky="w", pady=8, padx=(10, 0))
        row += 1

        # Color theme
        ctk.CTkLabel(main_frame, text="Color:").grid(row=row, column=0, sticky="w", pady=8)
        theme_var = ctk.StringVar(value=self.global_settings.get("color_theme", "blue"))

        def on_theme_change(new_theme):
            if new_theme != self.global_settings.get("color_theme"):
                self.global_settings["color_theme"] = new_theme
                save_global_settings(self.global_settings)
                dialog.destroy()
                self.rebuild_ui()
                self.after(150, self.show_global_settings)

        theme_menu = ctk.CTkOptionMenu(
            main_frame,
            variable=theme_var,
            values=COLOR_THEMES,
            width=150,
            command=on_theme_change
        )
        theme_menu.grid(row=row, column=1, sticky="w", pady=8, padx=(10, 0))
        row += 1

        # Font zoom
        ctk.CTkLabel(main_frame, text="Font zoom:").grid(row=row, column=0, sticky="w", pady=8)
        zoom_var = ctk.DoubleVar(value=self.global_settings.get("font_zoom", 1.0))

        zoom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        zoom_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=8, padx=(10, 0))

        zoom_slider = ctk.CTkSlider(
            zoom_frame,
            from_=0.8,
            to=2.0,
            number_of_steps=12,
            variable=zoom_var,
            width=120
        )
        zoom_slider.pack(side="left")

        zoom_label = ctk.CTkLabel(zoom_frame, text=f"{zoom_var.get():.1f}x", width=40)
        zoom_label.pack(side="left", padx=(5, 0))

        # Debounce for zoom
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
                    self.after(150, self.show_global_settings)
            zoom_timer[0] = dialog.after(500, apply_zoom)

        zoom_slider.configure(command=on_zoom_change)
        row += 1

        # Separator
        ctk.CTkLabel(main_frame, text="").grid(row=row, column=0, pady=5)
        row += 1

        # === GIT SECTION ===
        ctk.CTkLabel(main_frame, text="Git", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        # Git binary
        ctk.CTkLabel(main_frame, text="Executable:").grid(row=row, column=0, sticky="w", pady=8)
        git_entry = ctk.CTkEntry(main_frame, width=250)
        git_entry.insert(0, self.global_settings.get("git_binary", "git"))
        git_entry.grid(row=row, column=1, sticky="ew", pady=8, padx=(10, 5))

        def browse_git():
            path = filedialog.askopenfilename(
                title="Select Git executable",
                filetypes=[("Executables", "*")]
            )
            if path:
                git_entry.delete(0, "end")
                git_entry.insert(0, path)

        ctk.CTkButton(main_frame, text="📂", width=40, command=browse_git).grid(
            row=row, column=2, pady=8)
        row += 1

        # Separator
        ctk.CTkLabel(main_frame, text="").grid(row=row, column=0, pady=5)
        row += 1

        # === OPTIONS SECTION ===
        ctk.CTkLabel(main_frame, text="Options", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        # Auto-start polling
        auto_poll_var = ctk.BooleanVar(value=self.global_settings.get("auto_start_polling", False))
        ctk.CTkCheckBox(main_frame, text="Auto-start polling",
                       variable=auto_poll_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Start collapsed
        collapsed_var = ctk.BooleanVar(value=self.global_settings.get("start_collapsed", False))
        ctk.CTkCheckBox(main_frame, text="Start with log collapsed",
                       variable=collapsed_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Advanced mode
        advanced_var = ctk.BooleanVar(value=self.global_settings.get("advanced_mode", False))
        ctk.CTkCheckBox(main_frame, text="Advanced mode (click tab=polling, double-click=sync)",
                       variable=advanced_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Desktop notifications
        notif_var = ctk.BooleanVar(value=self.global_settings.get("desktop_notifications", True))
        ctk.CTkCheckBox(main_frame, text="Desktop notifications (notify-send)",
                       variable=notif_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Restore polling on restart
        restore_poll_var = ctk.BooleanVar(value=self.global_settings.get("restore_polling", False))
        ctk.CTkCheckBox(main_frame, text="Restore polling state on restart",
                       variable=restore_poll_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Sync new branches by default
        sync_new_var = ctk.BooleanVar(value=self.global_settings.get("sync_new_branches_by_default", False))
        ctk.CTkCheckBox(main_frame, text="Enable sync for newly discovered branches",
                       variable=sync_new_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        row += 1

        # Recent sync activity buffer size (status bar)
        ctk.CTkLabel(main_frame, text="Recent activity entries kept:").grid(row=row, column=0, sticky="w", pady=6)
        recent_limit_var = ctk.StringVar(value=str(self.global_settings.get("recent_sync_limit", 5)))
        ctk.CTkOptionMenu(main_frame, variable=recent_limit_var,
                         values=["3", "5", "10", "20"], width=80).grid(row=row, column=1, sticky="w", pady=6)
        row += 1

        main_frame.columnconfigure(1, weight=1)

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
                save_global_settings(self.global_settings)
            except Exception as e:
                messagebox.showerror("Error", f"Unable to save: {e}", parent=dialog)
                return

            dialog.destroy()

            # Rebuild UI if advanced mode changed
            if old_advanced != new_advanced:
                self.rebuild_ui()

        ctk.CTkButton(btn_frame, text="Save", command=save_settings).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

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
            if path in self.tab_paths.values():
                messagebox.showinfo(
                    "Info",
                    "This repository is already open.",
                    parent=self
                )
                return

            detected = detect_repo_settings(path, git)
            config_file = Path(path) / "githerd.toml"
            if not config_file.exists():
                save_repo_config(path, detected)

            self.add_repo(path)
            self.save_current_repos()
