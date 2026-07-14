# -*- coding: utf-8 -*-
"""
GitHerd — App persistence mixin.

Handles loading/saving repos, window state, rebuild UI, and restart.
"""

import re
import sys
import os
import subprocess
from pathlib import Path
import tkinter.font as tkfont
import customtkinter as ctk

from ..config import (
    load_global_settings, save_global_settings,
    load_saved_repos as load_repos_from_file, save_repos,
    apply_theme_settings
)
from ..git_utils import is_git_repo


class AppPersistenceMixin:
    """Mixin for persistence and UI rebuild."""

    def load_saved_repos(self):
        """Load saved repositories and restore state.

        Resilient: a single repo that fails to open (bad githerd.toml,
        a widget error, a transient git problem) must NOT abort the
        whole loop and make every following repo disappear. Any repo
        listed in repos.json that we could not open here is remembered
        in self._unloaded_repos so save_current_repos does not silently
        drop it from persistence.
        """
        repos = load_repos_from_file()
        git = self.global_settings.get("git_binary", "git")
        hidden_repos = self.global_settings.get("hidden_repos", [])
        # Repos present in repos.json but not turned into a live tab this
        # session (missing folder, not a git repo, or an open error).
        # Preserved so a later save keeps them in the file.
        self._unloaded_repos = []
        for repo_path in repos:
            # Skip hidden (inactive) repos — they stay in persistence via
            # the hidden_repos list, not via _unloaded_repos.
            if repo_path in hidden_repos:
                continue
            try:
                if Path(repo_path).exists() and is_git_repo(repo_path, git):
                    self.add_repo(repo_path, switch_to=False)
                else:
                    # Folder gone / not a git repo right now: keep the
                    # entry rather than erasing it (the drive might be
                    # unmounted, WSL path temporarily absent, etc.).
                    self._unloaded_repos.append(repo_path)
            except Exception as e:
                import sys
                print(f"[GitHerd] Failed to open repo {repo_path!r}: {e!r}",
                      file=sys.stderr, flush=True)
                self._unloaded_repos.append(repo_path)

        def restore_tab():
            last_tab = self.global_settings.get("last_active_tab", "")
            if last_tab and last_tab in self.tabs:
                self.switch_tab(last_tab)
            elif self.tabs:
                first_tab = list(self.tabs.keys())[0]
                self.switch_tab(first_tab)

        def restore_polling():
            """Restore polling state if option is enabled."""
            if not self.global_settings.get("restore_polling", False):
                return
            polling_states = self.global_settings.get("polling_states", {})
            for tab_name, tab in self.tabs.items():
                repo_path = self.tab_paths.get(tab_name, "")
                if repo_path and polling_states.get(repo_path, False):
                    if tab.git_healthy and not tab.polling:
                        tab.toggle_polling()

        self.after(100, restore_tab)
        self.after(200, restore_polling)

    def save_current_repos(self):
        """Save list of repositories to repos.json.

        Includes: currently open tabs + hidden repos + any repo that
        was in repos.json but could not be opened this session
        (_unloaded_repos). The last part is critical — without it, a
        repo that failed to load once would be permanently erased from
        the file the next time this runs, which is exactly how the
        "far fewer repos than before" data loss happened.
        """
        repos = list(self.tab_paths.values())
        hidden_repos = self.global_settings.get("hidden_repos", [])
        for hidden in hidden_repos:
            if hidden not in repos:
                repos.append(hidden)
        for unloaded in getattr(self, "_unloaded_repos", []):
            if unloaded not in repos:
                repos.append(unloaded)
        save_repos(repos)

    def save_window_state(self):
        """Save window position and state for restart."""
        self.update_idletasks()
        geom = self.geometry()
        match = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geom)
        if match:
            self.global_settings["window_width"] = int(match.group(1))
            self.global_settings["window_x"] = int(match.group(3))
            self.global_settings["window_y"] = int(match.group(4))

        # Save collapsed state based on current tab
        if self.current_tab and self.current_tab in self.tabs:
            current_tab_obj = self.tabs[self.current_tab]
            self.global_settings["start_collapsed"] = not current_tab_obj.log_visible
            self.global_settings["last_active_tab"] = self.current_tab

        # Always save polling state for each repo
        polling_states = {}
        for tab_name, tab in self.tabs.items():
            repo_path = self.tab_paths.get(tab_name, "")
            if repo_path:
                polling_states[repo_path] = tab.polling
        self.global_settings["polling_states"] = polling_states

        save_global_settings(self.global_settings)

    def rebuild_ui(self):
        """Rebuild UI without restarting process."""
        import tkinter as tk

        # Save current state
        saved_current_tab = self.current_tab
        saved_repos = list(self.tab_paths.values())
        saved_geometry = self.geometry()

        # Stop all polling properly
        for tab in self.tabs.values():
            if tab.polling:
                tab.polling = False
                tab.stop_event.set()
                tab.stop_countdown()

        def do_rebuild():
            any_alive = any(
                tab.polling_thread and tab.polling_thread.is_alive()
                for tab in self.tabs.values()
            )
            if any_alive:
                self.after(200, do_rebuild)
                return

            # Hide window during rebuild
            self.withdraw()

            # Destroy all child widgets
            for widget in self.winfo_children():
                widget.destroy()

            # Reset structures
            self.tabs = {}
            self.tab_paths = {}
            self.tab_buttons = {}
            self.tab_frames = {}
            self.current_tab = None

            # Apply new theme
            apply_theme_settings()

            # Recreate menu bar
            font_zoom = self.global_settings.get("font_zoom", 1.0)
            ctk.set_widget_scaling(font_zoom)
            ctk.set_window_scaling(font_zoom)

            # Rebuild menus
            self._build_menus()

            # Recreate tab bar
            self.tab_bar = ctk.CTkFrame(self, height=40)
            self.tab_bar.pack(fill="x", padx=10, pady=(10, 0))

            # Container for content
            self.content_container = ctk.CTkFrame(self)
            self.content_container.pack(fill="both", expand=True, padx=10, pady=(5, 10))

            # Reload repos
            git = self.global_settings.get("git_binary", "git")
            for repo_path in saved_repos:
                if Path(repo_path).exists() and is_git_repo(repo_path, git):
                    self.add_repo(repo_path)

            # Restore active tab
            def restore():
                if saved_current_tab and saved_current_tab in self.tabs:
                    self.switch_tab(saved_current_tab)
                elif self.tabs:
                    first_tab = list(self.tabs.keys())[0]
                    self.switch_tab(first_tab)

            self.after(100, restore)

            # Restore geometry and show window
            self.geometry(saved_geometry)
            self.update_idletasks()
            self.deiconify()

        do_rebuild()

    def restart_app(self):
        """Restart the application."""
        any_sync_locked = any(tab.lock.locked() for tab in self.tabs.values())
        polling_count = sum(1 for tab in self.tabs.values() if tab.polling)

        if any_sync_locked or polling_count > 0:
            # Custom dialog with Cancel and Restart buttons
            dialog = ctk.CTkToplevel(self)
            dialog.title("Restart")
            dialog.geometry("400x180")
            dialog.transient(self)
            dialog.wait_visibility()
            dialog.grab_set()
            dialog.resizable(False, False)
            self.ensure_dialog_on_screen(dialog)

            frame = ctk.CTkFrame(dialog)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            if any_sync_locked:
                msg = "A synchronization is in progress.\n\nRestart will wait for it to finish, then stop polling."
            else:
                msg = f"{polling_count} polling(s) active.\n\nRestart will stop all polling."

            ctk.CTkLabel(frame, text=msg, justify="center").pack(pady=20)

            btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
            btn_frame.pack(pady=10)

            def do_restart():
                dialog.destroy()
                # Save state FIRST so polling_states captures tabs that
                # were polling. Stopping polling sets tab.polling=False,
                # so save_window_state must run before.
                self.save_window_state()
                self.save_current_repos()

                # Signal all threads to stop
                for tab in self.tabs.values():
                    if tab.polling:
                        tab.polling = False
                        tab.stop_event.set()
                        tab.stop_countdown()

                def wait_and_restart():
                    any_alive = any(
                        tab.polling_thread and tab.polling_thread.is_alive()
                        for tab in self.tabs.values()
                    )
                    if any_alive:
                        self.after(500, wait_and_restart)
                    else:
                        python = sys.executable
                        script = os.path.abspath(sys.argv[0])
                        self.destroy()
                        subprocess.Popen([python, script])
                        sys.exit(0)

                wait_and_restart()

            ctk.CTkButton(btn_frame, text="Cancel", width=100,
                         command=dialog.destroy).pack(side="left", padx=10)
            ctk.CTkButton(btn_frame, text="Restart", width=100,
                         fg_color="#8B0000", hover_color="#CD5C5C",
                         command=do_restart).pack(side="left", padx=10)
            return

        # No sync or polling - restart immediately
        self.save_window_state()
        self.save_current_repos()
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        self.destroy()
        subprocess.Popen([python, script])
        sys.exit(0)
