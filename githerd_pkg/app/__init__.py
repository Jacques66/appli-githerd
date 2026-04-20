# -*- coding: utf-8 -*-
"""
GitHerd — App module.

Main application class.
"""

import customtkinter as ctk

from .core import AppCoreMixin
from .tabs import AppTabsMixin
from .menus import AppMenusMixin
from .dialogs import AppDialogsMixin
from .persistence import AppPersistenceMixin


class App(
    AppCoreMixin,
    AppTabsMixin,
    AppMenusMixin,
    AppDialogsMixin,
    AppPersistenceMixin,
    ctk.CTk
):
    """Main GitHerd application."""

    def __init__(self):
        super().__init__()

        # Hide window during initialization
        self.withdraw()

        # Initialize state
        self._init_state()

        # Initialize window
        self._init_window()

        # Build menus
        self._build_menus()

        # Create tab bar
        self.tab_bar = ctk.CTkFrame(self, height=40)
        self.tab_bar.pack(fill="x", padx=10, pady=(10, 0))

        # Container for tab content
        self.content_container = ctk.CTkFrame(self)
        self.content_container.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Load saved repos
        self.load_saved_repos()

        # If no repos, open dialog
        if not self.tabs:
            self.after(100, self.add_repo_dialog)

        # Save on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Start the thread-safe UI dispatcher drainer on the main loop
        self.after(30, self._drain_ui_queue)

        # Always on top
        self.after(500, self.set_always_on_top)

        # Update menu colors
        self.update_menu_colors()

        # Show window after complete initialization
        self.update_idletasks()
        self.deiconify()


__all__ = ["App"]
