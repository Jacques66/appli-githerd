# -*- coding: utf-8 -*-
"""
GitHerd — App core mixin.

Handles initialization, lifecycle, and basic window management.
"""

import queue
import subprocess
from collections import deque
from datetime import datetime
import customtkinter as ctk

from ..config import load_global_settings, save_global_settings


class AppCoreMixin:
    """Mixin for app initialization and lifecycle."""

    def _init_state(self):
        """Initialize application state."""
        self.tabs = {}  # tab_name -> RepoTabContent
        self.tab_paths = {}  # tab_name -> repo_path
        self.global_settings = load_global_settings()
        self.tab_buttons = {}
        self.tab_frames = {}
        self.current_tab = None
        # Thread-safe UI dispatcher: worker threads push callables here,
        # the main thread drains them. Needed because self.after() itself
        # is not thread-safe in this Tcl/Tk build (createcommand requires
        # the main thread).
        self._ui_queue = queue.Queue()
        # Global rolling list of meaningful sync events across all repos.
        # Each entry: (datetime, repo_alias, message). Newest first.
        self._recent_events_limit = max(1, int(self.global_settings.get("recent_sync_limit", 5)))
        self.recent_events = deque(maxlen=self._recent_events_limit)

    def ui_call(self, fn):
        """Thread-safe: schedule fn() to run on the Tk main thread.

        Call this from any thread to marshal a UI update onto the main
        loop. Exceptions raised by fn() are swallowed to keep the
        drainer alive.
        """
        self._ui_queue.put(fn)

    def _drain_ui_queue(self):
        """Runs on the main thread via after(). Drains pending UI calls."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(30, self._drain_ui_queue)

    def record_event(self, repo_alias):
        """Record a meaningful sync event for the global status bar.

        Thread-safe: the deque append is atomic in CPython, and the
        widget refresh is marshalled to the main thread via ui_call.
        """
        self.recent_events.appendleft((datetime.now(), repo_alias))
        self.ui_call(self._refresh_status_bar)

    def _refresh_status_bar(self):
        """Render the bar as N entries: oldest left, newest right (white)."""
        inner = getattr(self, "status_bar_inner", None)
        if inner is None:
            return
        for child in inner.winfo_children():
            child.destroy()
        if not self.recent_events:
            return
        entries = list(reversed(self.recent_events))  # oldest first, newest last
        last_idx = len(entries) - 1
        for i, (ts, tab_name) in enumerate(entries):
            path = self.tab_paths.get(tab_name)
            display = self.get_tab_display_name(path) if path else tab_name
            text = f"{ts.strftime('%H:%M:%S')} {display}"
            is_newest = (i == last_idx)
            label = ctk.CTkLabel(
                inner,
                text=text,
                font=ctk.CTkFont(size=12, weight="bold" if is_newest else "normal"),
                text_color="white" if is_newest else "gray",
                cursor="hand2"
            )
            label.pack(side="left")
            label.bind("<Button-1>", lambda e: self.show_recent_events_popup())
            if i < last_idx:
                sep = ctk.CTkLabel(inner, text="  ·  ",
                                   font=ctk.CTkFont(size=12), text_color="gray")
                sep.pack(side="left")
                sep.bind("<Button-1>", lambda e: self.show_recent_events_popup())

    def _build_status_bar(self):
        """Create the bottom status bar showing last meaningful sync event.

        Packed with side='bottom' BEFORE the tab bar / content container so
        it stays anchored at the bottom of the window regardless of the
        per-tab log accordion above.
        """
        self.status_bar = ctk.CTkFrame(self, height=24, corner_radius=0)
        self.status_bar.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar.pack_propagate(False)
        self.status_bar.bind("<Button-1>", lambda e: self.show_recent_events_popup())

        # Inner container holds one CTkLabel per entry so we can color the
        # newest one differently.
        self.status_bar_inner = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        self.status_bar_inner.pack(side="left", fill="x", expand=True, padx=10, pady=2)
        self.status_bar_inner.bind("<Button-1>", lambda e: self.show_recent_events_popup())

    def show_recent_events_popup(self):
        """Open a Toplevel listing the last N recorded events."""
        import tkinter as tk
        if not self.recent_events:
            return
        popup = ctk.CTkToplevel(self)
        popup.title("Recent sync activity")
        popup.geometry("520x240")
        popup.transient(self)

        frame = ctk.CTkFrame(popup, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        text = ctk.CTkTextbox(frame, font=ctk.CTkFont(family="Consolas", size=12))
        text.pack(fill="both", expand=True)
        for ts, tab_name in self.recent_events:
            path = self.tab_paths.get(tab_name)
            display = self.get_tab_display_name(path) if path else tab_name
            text.insert("end", f"{ts.strftime('%H:%M:%S')}  {display}\n")
        text.configure(state="disabled")

        ctk.CTkButton(popup, text="Close", command=popup.destroy, width=80).pack(pady=(0, 10))

    def _resize_recent_events(self, new_limit):
        """Rebuild the deque preserving content when the limit changes."""
        new_limit = max(1, int(new_limit))
        if new_limit == self._recent_events_limit:
            return
        self._recent_events_limit = new_limit
        self.recent_events = deque(list(self.recent_events)[:new_limit], maxlen=new_limit)
        self._refresh_status_bar()

    def _init_window(self):
        """Initialize window geometry and position."""
        self.title("GitHerd")
        if self.global_settings.get("start_collapsed", False):
            advanced_mode = self.global_settings.get("advanced_mode", False)
            # +24px for the bottom status bar
            collapsed_height = (151 if advanced_mode else 189) + 24
            self.geometry(f"710x{collapsed_height}")
        else:
            self.geometry("710x774")

        # Restore window position if saved (after restart)
        saved_x = self.global_settings.get("window_x")
        saved_y = self.global_settings.get("window_y")
        if saved_x is not None and saved_y is not None:
            self.geometry(f"+{saved_x}+{saved_y}")
            # Clean up after use
            del self.global_settings["window_x"]
            del self.global_settings["window_y"]
            save_global_settings(self.global_settings)

    def set_always_on_top(self):
        """Set window to always be on top."""
        self.attributes("-topmost", True)
        try:
            subprocess.run(
                ["wmctrl", "-r", self.title(), "-b", "add,above"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        except FileNotFoundError:
            pass

    def ensure_dialog_on_screen(self, dialog):
        """Ensure dialog is fully visible on screen."""
        dialog.update_idletasks()

        # Dialog dimensions
        dlg_width = dialog.winfo_width()
        dlg_height = dialog.winfo_height()

        # Screen dimensions
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        # Main window position
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()

        # Position near main window
        x = main_x + (main_width - dlg_width) // 2
        y = main_y + 50

        # Adjust if off screen
        if x + dlg_width > screen_width:
            x = screen_width - dlg_width - 10
        if x < 0:
            x = 10
        if y + dlg_height > screen_height:
            y = screen_height - dlg_height - 50
        if y < 0:
            y = 10

        dialog.geometry(f"+{x}+{y}")

    def update_title(self):
        """Update window title with status."""
        total = len(self.tabs)
        polling = sum(1 for t in self.tabs.values() if t.polling)
        stopped = sum(1 for t in self.tabs.values() if t.pending_branches and not t.polling)

        if total == 0:
            self.title("GitHerd")
        elif stopped > 0:
            self.title(f"GitHerd — {total} repos, {polling} polling, {stopped} STOP")
        elif polling > 0:
            self.title(f"GitHerd — {total} repos, {polling} polling")
        else:
            self.title(f"GitHerd — {total} repos")

    def stop_all_polling(self):
        """Stop polling for all tabs."""
        stopped = 0
        for tab in self.tabs.values():
            if tab.polling:
                tab.polling = False
                tab.stop_event.set()
                tab.stop_countdown()
                tab.btn_poll.configure(text="▶ Start polling")
                self.update_tab_color(tab)
                stopped += 1

        self.update_title()

        if stopped > 0:
            from tkinter import messagebox
            self.after(100, lambda: messagebox.showinfo(
                "Polling stopped",
                f"{stopped} polling(s) stopped.",
                parent=self
            ))

    def on_close(self):
        """Handle window close."""
        # Signal all threads to stop
        for tab in self.tabs.values():
            if tab.polling:
                tab.polling = False
                tab.stop_event.set()

        # Wait for all threads to finish
        for tab in self.tabs.values():
            tab.wait_for_polling_thread(timeout=30)

        # Save last active tab
        if self.tabs and self.current_tab:
            self.global_settings["last_active_tab"] = self.current_tab
            save_global_settings(self.global_settings)

        self.save_current_repos()
        self.destroy()

    def get_current_tab(self):
        """Get the current tab content object."""
        if not self.tabs or not self.current_tab:
            return None
        return self.tabs.get(self.current_tab)
