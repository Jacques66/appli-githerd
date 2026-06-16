# -*- coding: utf-8 -*-
"""
GitHerd — App module.

Main application class.
"""

import os
import sys
import customtkinter as ctk

from .core import AppCoreMixin
from .tabs import AppTabsMixin
from .menus import AppMenusMixin
from .dialogs import AppDialogsMixin
from .persistence import AppPersistenceMixin


def _trace(msg):
    """Print init progress to stderr when GITHERD_TRACE=1."""
    if os.environ.get("GITHERD_TRACE") == "1":
        print(f"[INIT] {msg}", flush=True, file=sys.stderr)


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
        _trace("super().__init__() …")
        super().__init__()
        _trace("super done")

        # Hide window during initialization
        self.withdraw()
        _trace("withdrew")

        # Initialize state
        self._init_state()
        _trace("_init_state done")

        # Initialize window
        self._init_window()
        _trace("_init_window done")

        # Build menus
        self._build_menus()
        _trace("_build_menus done")

        # Status bar at the bottom (packed first with side="bottom" so it
        # stays anchored regardless of the log accordion above it).
        self._build_status_bar()
        _trace("_build_status_bar done")

        # Create tab bar
        self.tab_bar = ctk.CTkFrame(self, height=40)
        self.tab_bar.pack(fill="x", padx=10, pady=(10, 0))
        _trace("tab_bar packed")

        # Container for tab content
        self.content_container = ctk.CTkFrame(self)
        self.content_container.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        _trace("content_container packed")

        # Load saved repos
        _trace("load_saved_repos starting …")
        self.load_saved_repos()
        _trace(f"load_saved_repos done ({len(self.tabs)} tabs)")

        # If no repos, open dialog
        if not self.tabs:
            self.after(100, self.add_repo_dialog)

        # Save on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Start the thread-safe UI dispatcher drainer on the main loop
        self.after(30, self._drain_ui_queue)
        _trace("ui drainer scheduled")

        # Periodic safety net that keeps tab button colors in lockstep
        # with the live polling/health state.
        self.after(1500, self._reconcile_tab_colors)

        # Always on top
        self.after(500, self.set_always_on_top)

        # Update menu colors
        self.update_menu_colors()
        _trace("update_menu_colors done")

        # Show window after complete initialization
        _trace("update_idletasks …")
        self.update_idletasks()
        _trace("update_idletasks done; deiconify …")
        self.deiconify()
        _trace("deiconify done — entering mainloop next")


__all__ = ["App"]
