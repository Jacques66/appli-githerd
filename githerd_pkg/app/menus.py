# -*- coding: utf-8 -*-
"""
GitHerd — App menus mixin.

Handles menu creation and updates.
"""

import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk

from ..git_utils import get_tracked_branches


class AppMenusMixin:
    """Mixin for menu management."""

    def _build_menus(self):
        """Build the menu bar."""
        # Calculate menu font size based on font_zoom
        font_zoom = self.global_settings.get("font_zoom", 1.0)
        menu_font_size = int(10 * font_zoom)
        menu_font = tkfont.Font(family="sans-serif", size=menu_font_size)

        # Colors based on appearance mode
        appearance = self.global_settings.get("appearance_mode", "dark")
        if appearance == "dark" or (appearance == "system" and ctk.get_appearance_mode() == "Dark"):
            menu_bg = "#2b2b2b"
            menu_fg = "#ffffff"
            menu_active_bg = "#404040"
            menu_active_fg = "#ffffff"
        else:
            menu_bg = "#f0f0f0"
            menu_fg = "#000000"
            menu_active_bg = "#0078d4"
            menu_active_fg = "#ffffff"

        self.menubar = tk.Menu(self, font=menu_font, bg=menu_bg, fg=menu_fg,
                               activebackground=menu_active_bg, activeforeground=menu_active_fg)
        self.config(menu=self.menubar)

        # File menu
        file_menu = tk.Menu(self.menubar, tearoff=0, font=menu_font, bg=menu_bg, fg=menu_fg,
                           activebackground=menu_active_bg, activeforeground=menu_active_fg)
        self.menubar.add_cascade(label="\u00a0\u00a0\u00a0File\u00a0\u00a0\u00a0", menu=file_menu)
        file_menu.add_command(label="Add repository...", command=self.add_repo_dialog,
                             accelerator="Ctrl+O")
        file_menu.add_command(label="Stop all polling", command=self.stop_all_polling,
                             accelerator="Ctrl+S")
        # Suspend / Restore \u2014 label flips depending on whether a
        # suspend snapshot is currently pending.
        suspend_label = (
            "Restore all polling"
            if getattr(self, "_suspended_polling", None)
            else "Suspend all polling"
        )
        file_menu.add_command(label=suspend_label,
                              command=self.suspend_or_restore_all_polling)
        self._file_menu = file_menu
        self._suspend_menu_index = file_menu.index("end")
        file_menu.add_separator()
        file_menu.add_command(label="Restart", command=self.restart_app,
                             accelerator="Ctrl+R")
        file_menu.add_command(label="Quit", command=self.on_close, accelerator="Ctrl+Q")

        # Repository menu (dynamically updated)
        self.repo_menu = tk.Menu(self.menubar, tearoff=0, font=menu_font, bg=menu_bg, fg=menu_fg,
                                activebackground=menu_active_bg, activeforeground=menu_active_fg)
        self.menu_font = menu_font
        self.menu_colors = {"bg": menu_bg, "fg": menu_fg, "active_bg": menu_active_bg, "active_fg": menu_active_fg}
        self.menubar.add_cascade(label="\u00a0\u00a0\u00a0Repository\u00a0\u00a0\u00a0", menu=self.repo_menu)

        # ? menu (Options + Help)
        help_menu = tk.Menu(self.menubar, tearoff=0, font=menu_font, bg=menu_bg, fg=menu_fg,
                           activebackground=menu_active_bg, activeforeground=menu_active_fg)
        self.menubar.add_cascade(label="\u00a0\u00a0\u00a0?\u00a0\u00a0\u00a0", menu=help_menu)
        help_menu.add_command(label="Settings...", command=self.show_global_settings)
        help_menu.add_separator()
        help_menu.add_command(label="Help", command=self.show_help)
        help_menu.add_command(label="About GitHerd", command=self.show_about)

        # Keyboard shortcuts
        self.bind("<Control-o>", lambda e: self.add_repo_dialog())
        self.bind("<Control-s>", lambda e: self.stop_all_polling())
        self.bind("<Control-r>", lambda e: self.restart_app())
        self.bind("<Control-q>", lambda e: self.on_close())

    def update_menu_colors(self, mode=None):
        """Update menu colors based on appearance mode."""
        if mode is None:
            mode = self.global_settings.get("appearance_mode", "dark")

        if mode == "dark" or (mode == "system" and ctk.get_appearance_mode() == "Dark"):
            menu_bg = "#2b2b2b"
            menu_fg = "#ffffff"
            menu_active_bg = "#404040"
            menu_active_fg = "#ffffff"
        else:
            menu_bg = "#f0f0f0"
            menu_fg = "#000000"
            menu_active_bg = "#0078d4"
            menu_active_fg = "#ffffff"

        # Update menubar and all submenus
        self.menubar.configure(bg=menu_bg, fg=menu_fg,
                              activebackground=menu_active_bg, activeforeground=menu_active_fg)
        for i in range(self.menubar.index("end") + 1):
            try:
                submenu = self.menubar.nametowidget(self.menubar.entrycget(i, "menu"))
                submenu.configure(bg=menu_bg, fg=menu_fg,
                                 activebackground=menu_active_bg, activeforeground=menu_active_fg)
            except:
                pass

        self.menu_colors = {"bg": menu_bg, "fg": menu_fg, "active_bg": menu_active_bg, "active_fg": menu_active_fg}

    def update_repo_menu(self):
        """Rebuild the Repository menu for current tab."""
        self.repo_menu.delete(0, "end")

        tab = self.get_current_tab()
        if not tab:
            self.repo_menu.add_command(label="(no repository)", state="disabled")
            return

        # Options
        self.repo_menu.add_command(label="Options...", command=tab.show_config_dialog)
        self.repo_menu.add_command(label="Open folder", command=tab.open_folder)
        self.repo_menu.add_separator()

        # Sync actions
        self.repo_menu.add_command(
            label="Sync now",
            command=tab.manual_sync,
            state="normal" if tab.git_healthy else "disabled"
        )

        polling_label = "Stop polling" if tab.polling else "Start polling"
        self.repo_menu.add_command(
            label=polling_label,
            command=tab.toggle_polling,
            state="normal" if tab.git_healthy else "disabled"
        )

        self.repo_menu.add_separator()

        # List branches matching prefix
        try:
            branches = get_tracked_branches(tab.remote, tab.prefix,
                                           cwd=tab.repo_path, git=tab.git)
        except:
            branches = []

        # Branch operations: open the two dedicated dialogs.
        self.repo_menu.add_command(
            label="Sync branches…",
            command=lambda t=tab: self.show_branch_sync_dialog(t),
            state="normal" if branches else "disabled",
        )
        self.repo_menu.add_command(
            label="Delete branches…",
            command=lambda t=tab: self.show_branch_delete_dialog(t),
            state="normal" if branches else "disabled",
        )
        self.repo_menu.add_separator()

        # Close tab
        self.repo_menu.add_command(label="Close", command=self.close_current_tab)

        # Inactive repos submenu
        hidden_repos = self.global_settings.get("hidden_repos", [])
        if hidden_repos:
            self.repo_menu.add_separator()
            inactive_menu = tk.Menu(
                self.repo_menu, tearoff=0, font=self.menu_font,
                bg=self.menu_colors["bg"], fg=self.menu_colors["fg"],
                activebackground=self.menu_colors["active_bg"],
                activeforeground=self.menu_colors["active_fg"]
            )
            for repo_path in hidden_repos:
                display_name = self.get_tab_display_name(repo_path)
                inactive_menu.add_command(
                    label=display_name,
                    command=lambda rp=repo_path: self.show_repo(rp)
                )
            self.repo_menu.add_cascade(
                label=f"Inactive repos ({len(hidden_repos)})",
                menu=inactive_menu
            )

