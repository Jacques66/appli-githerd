# -*- coding: utf-8 -*-
"""
GitHerd — App tabs mixin.

Custom trapezoidal tab strip (widgets.TabBar) above a content pane.
Per-repo polling/health status is the tab's fill colour (green =
polling, red = error/STOP, neutral = idle); the active tab is drawn in
front with a top accent bar. Countdown + update marker live in the
tab label.
"""

import threading
import tkinter as tk
from pathlib import Path
import customtkinter as ctk

from ..config import (
    load_global_settings, save_global_settings, load_repo_config,
    save_repo_config
)
from ..git_utils import is_git_repo, detect_repo_settings
from ..widgets import TabBar
from ..repo_tab import RepoTabContent


class AppTabsMixin:
    """Mixin for tab management."""

    # ------------------------------------------------------------------
    # Container: trapezoid tab strip + content pane
    # ------------------------------------------------------------------

    def _build_tabs_container(self):
        """Create the TabBar (top) and the content pane (below). Called
        from App.__init__ and rebuild_ui."""
        zoom = self.global_settings.get("font_zoom", 1.0)
        self.tab_bar = TabBar(
            self, font_zoom=zoom,
            on_click=self.on_tab_click,
            on_double=self.on_tab_double_click,
            on_middle=self.hide_repo,
            on_right=self.on_tab_right_click,
            on_reorder=self._on_tabs_reordered,
        )
        # No vertical gap between the strip and the pane so the active
        # tab reads as connected to the content below.
        self.tab_bar.pack(fill="x", padx=10, pady=(10, 0))
        self.content_container = ctk.CTkFrame(self)
        self.content_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _on_tabs_reordered(self, new_order):
        """Persist a drag-reorder coming from the TabBar."""
        def reorder(d):
            return {n: d[n] for n in new_order if n in d}
        self.tabs = reorder(self.tabs)
        self.tab_paths = reorder(self.tab_paths)
        self.tab_frames = reorder(self.tab_frames)
        self.save_current_repos()

    # ------------------------------------------------------------------
    # Per-tab status: color state, reason, transition logging
    # ------------------------------------------------------------------

    def get_tab_bg_state(self, tab):
        """Return status state for tab."""
        if not tab.git_healthy:
            return "red"
        if getattr(tab, "sync_error", False):
            return "red"
        if tab.pending_branches and not tab.polling:
            return "red"
        if tab.polling:
            return "green"
        return "default"

    def _red_reason(self, tab):
        """Human-readable reason a tab is red (in priority order)."""
        if not tab.git_healthy:
            return tab.git_error or "Git not working"
        if getattr(tab, "sync_error", False):
            try:
                info = tab.info_label.cget("text")
            except Exception:
                info = ""
            return info or "sync error"
        if tab.pending_branches and not tab.polling:
            return "STOP — human action required (diverged / conflicting branches)"
        return "unknown"

    def _log_color_transition(self, tab, prev_bg, new_bg):
        """Log entering/leaving red to the tab's own log: orange in,
        green out. Other transitions are not logged."""
        if new_bg == prev_bg:
            return
        try:
            if new_bg == "red":
                tab.log_msg(f"⬤ RED — {self._red_reason(tab)}", color="#ff9500")
            elif prev_bg == "red":
                state = "polling" if new_bg == "green" else "idle"
                tab.log_msg(f"⬤ GREEN — error cleared ({state})", color="#4ade80")
        except Exception:
            pass

    def update_tab_color(self, tab):
        """Re-derive the tab's status + update marker on the strip."""
        name = tab.tab_name
        if name not in self.tabs:
            return
        bg_state = self.get_tab_bg_state(tab)

        prev_bg = getattr(tab, "_last_bg_state", None)
        if bg_state != prev_bg:
            tab._last_bg_state = bg_state
            if prev_bg is not None:  # skip the first paint at startup
                self._log_color_transition(tab, prev_bg, bg_state)

        try:
            self.tab_bar.update_tab(
                name, status=bg_state, has_update=getattr(tab, "has_update", False))
        except Exception:
            pass
        self.update_title()

    def _refresh_tab_label(self, tab):
        """Push the current display name into the tab strip."""
        try:
            self.tab_bar.update_tab(
                tab.tab_name, label=self.get_tab_display_name(str(tab.repo_path)))
        except Exception:
            pass

    def set_tab_countdown(self, tab_name, seconds):
        """Feed the polling countdown into the tab label (main thread)."""
        try:
            self.tab_bar.update_tab(tab_name, countdown=seconds or 0)
        except Exception:
            pass

    def _reconcile_tab_colors(self):
        """Periodic safety net so the tab status can never disagree with
        the live polling/health state."""
        try:
            for tab in self.tabs.values():
                self.update_tab_color(tab)
        except Exception:
            pass
        self.after(1500, self._reconcile_tab_colors)

    # ------------------------------------------------------------------
    # Periodic automation loops
    # ------------------------------------------------------------------

    def _tab_in_error(self, tab):
        return (not tab.git_healthy) or getattr(tab, "sync_error", False)

    def _retry_errored_repos(self):
        settings = self.global_settings
        if settings.get("auto_retry_errored", False) and not getattr(self, "_polling_circuit_open", False):
            for tab in self.tabs.values():
                if self._tab_in_error(tab) and not tab.lock.locked():
                    threading.Thread(target=tab.retry_recovery, daemon=True).start()
        interval = max(5, int(settings.get("auto_retry_interval_seconds", 60)))
        self.after(interval * 1000, self._retry_errored_repos)

    def _watch_idle_repos(self):
        settings = self.global_settings
        try:
            interval = int(settings.get("watch_idle_interval_seconds", 0) or 0)
        except (TypeError, ValueError):
            interval = 0
        if interval > 0 and not getattr(self, "_polling_circuit_open", False):
            for tab in self.tabs.values():
                if (tab.git_healthy and not tab.polling
                        and not getattr(tab, "sync_error", False)
                        and not tab.lock.locked()):
                    threading.Thread(target=tab.watch_for_changes, daemon=True).start()
            delay = max(5, interval) * 1000
        elif interval > 0:
            delay = max(5, interval) * 1000
        else:
            delay = 5000
        self.after(delay, self._watch_idle_repos)

    def _disable_inactive_repos(self):
        import time
        settings = self.global_settings
        try:
            hours = float(settings.get("inactivity_disable_hours", 24) or 0)
        except (TypeError, ValueError):
            hours = 0
        if hours > 0:
            cutoff = hours * 3600
            now = time.time()
            for tab in self.tabs.values():
                if tab.polling and (now - getattr(tab, "last_activity_time", now)) >= cutoff:
                    tab.log_msg(f"Inactive for ≥{hours:g}h → stopping polling")
                    tab.polling = False
                    tab.polling_interrupted = False
                    tab.stop_event.set()
                    tab.btn_poll.configure(text="▶ Start polling")
                    tab.stop_countdown()
                    self.update_tab_color(tab)
            self.update_title()
        self.after(60000, self._disable_inactive_repos)

    def mark_tab_updated(self, tab):
        if not tab.has_update:
            tab.has_update = True
            self.update_tab_color(tab)

    def clear_tab_marker(self, tab):
        if tab.has_update:
            tab.has_update = False
            self.update_tab_color(tab)

    # ------------------------------------------------------------------
    # Add / switch / close / hide
    # ------------------------------------------------------------------

    def add_repo(self, repo_path, switch_to=True):
        """Add a repository tab."""
        repo_name = Path(repo_path).name
        tab_name = repo_name
        counter = 1
        while tab_name in self.tabs:
            counter += 1
            tab_name = f"{repo_name} ({counter})"

        display_name = self.get_tab_display_name(repo_path)

        tab_content = RepoTabContent(self.content_container, repo_path, self, tab_name)
        self.tab_frames[tab_name] = tab_content
        self.tabs[tab_name] = tab_content
        self.tab_paths[tab_name] = repo_path

        self.tab_bar.add_tab(tab_name, display_name, status="default")

        if switch_to:
            self.switch_tab(tab_name)
        self.after(100, self.update_title)

        if self.global_settings.get("auto_start_polling", False) and not self.global_settings.get("restore_polling", False):
            self.after(500, tab_content.toggle_polling)

    def on_tab_click(self, tab_name):
        """Single click: switch. In advanced mode, clicking the already-
        active tab toggles polling (with a short delay so a double-click
        can cancel it and sync instead)."""
        if self.global_settings.get("advanced_mode", False):
            if getattr(self, "_click_timer", None):
                try:
                    self.after_cancel(self._click_timer)
                except Exception:
                    pass
                self._click_timer = None

            def do_single():
                self._click_timer = None
                if self.current_tab == tab_name:
                    tab = self.tabs.get(tab_name)
                    if tab and tab.git_healthy:
                        tab.toggle_polling()
                else:
                    self.switch_tab(tab_name)

            self._click_timer = self.after(300, do_single)
        else:
            self.switch_tab(tab_name)

    def on_tab_double_click(self, tab_name):
        """Advanced mode: double-click a tab → sync now."""
        if self.global_settings.get("advanced_mode", False):
            if getattr(self, "_click_timer", None):
                try:
                    self.after_cancel(self._click_timer)
                except Exception:
                    pass
                self._click_timer = None
            tab = self.tabs.get(tab_name)
            if tab and tab.git_healthy:
                tab.manual_sync()

    def switch_tab(self, tab_name):
        """Switch to specified tab."""
        if tab_name not in self.tabs:
            return
        if self.current_tab and self.current_tab in self.tab_frames:
            self.tab_frames[self.current_tab].pack_forget()

        self.tab_frames[tab_name].pack(fill="both", expand=True)
        self.current_tab = tab_name
        self.tab_bar.set_active(tab_name)

        tab = self.tabs[tab_name]
        if tab.has_update:
            tab.has_update = False
            self.update_tab_color(tab)

        self.update_repo_menu()

    def close_tab(self, tab_name):
        """Close a repository tab."""
        if tab_name not in self.tabs:
            return
        tab = self.tabs[tab_name]
        if tab.polling:
            tab.polling = False
            tab.stop_event.set()
        tab.stop_countdown()
        tab.wait_for_polling_thread(timeout=5)

        self.tab_bar.remove_tab(tab_name)
        self.tab_frames.pop(tab_name, None)
        try:
            tab.destroy()
        except Exception:
            pass
        self.tabs.pop(tab_name, None)
        self.tab_paths.pop(tab_name, None)

        if self.current_tab == tab_name:
            self.current_tab = None
            if self.tabs:
                self.switch_tab(next(iter(self.tabs)))

        self.save_current_repos()
        self.update_title()

    def close_current_tab(self):
        if not self.tabs or not self.current_tab:
            return
        self.close_tab(self.current_tab)

    def on_tab_right_click(self, event, tab_name):
        """Right-click context menu for a tab."""
        tab = self.tabs.get(tab_name)
        menu = tk.Menu(
            self, tearoff=0,
            font=getattr(self, "menu_font", None),
            bg=self.menu_colors["bg"] if hasattr(self, "menu_colors") else None,
            fg=self.menu_colors["fg"] if hasattr(self, "menu_colors") else None,
            activebackground=(self.menu_colors["active_bg"] if hasattr(self, "menu_colors") else None),
            activeforeground=(self.menu_colors["active_fg"] if hasattr(self, "menu_colors") else None),
        )
        menu.add_command(
            label="Run",
            command=lambda: tab.manual_sync() if tab else None,
            state="normal" if tab and tab.git_healthy else "disabled",
        )
        polling_label = "Stop polling" if (tab and tab.polling) else "Start polling"
        menu.add_command(
            label=polling_label,
            command=lambda: tab.toggle_polling() if tab else None,
            state="normal" if tab and tab.git_healthy else "disabled",
        )
        menu.add_command(
            label="Options...",
            command=lambda: tab.show_config_dialog() if tab else None,
        )
        menu.add_separator()
        menu.add_command(label="Hide tab", command=lambda: self.hide_repo(tab_name))
        menu.add_command(label="Close", command=lambda: self.close_tab(tab_name))
        menu.tk_popup(event.x_root, event.y_root)

    def hide_repo(self, tab_name):
        """Hide a repo (make it inactive) - stop polling but keep in settings."""
        if tab_name not in self.tabs:
            return
        repo_path = self.tab_paths.get(tab_name)
        if not repo_path:
            return

        tab = self.tabs[tab_name]
        if tab.polling:
            tab.polling = False
            tab.stop_event.set()
        tab.stop_countdown()
        tab.wait_for_polling_thread(timeout=2)

        hidden = self.global_settings.get("hidden_repos", [])
        if repo_path not in hidden:
            hidden.append(repo_path)
            self.global_settings["hidden_repos"] = hidden
            save_global_settings(self.global_settings)

        self.tab_bar.remove_tab(tab_name)
        self.tab_frames.pop(tab_name, None)
        try:
            tab.destroy()
        except Exception:
            pass
        self.tabs.pop(tab_name, None)
        self.tab_paths.pop(tab_name, None)

        if self.current_tab == tab_name:
            self.current_tab = None
            if self.tabs:
                self.switch_tab(next(iter(self.tabs)))

        self.update_repo_menu()
        self.update_title()

    def show_repo(self, repo_path):
        """Show a hidden repo (make it active again)."""
        hidden = self.global_settings.get("hidden_repos", [])
        if repo_path in hidden:
            hidden.remove(repo_path)
            self.global_settings["hidden_repos"] = hidden
            save_global_settings(self.global_settings)
        self.add_repo(repo_path, switch_to=True)
        self.update_repo_menu()

    # ------------------------------------------------------------------
    # Aliases / display names / directory change
    # ------------------------------------------------------------------

    def set_tab_alias(self, tab_name, alias):
        repo_path = self.tab_paths.get(tab_name)
        if not repo_path:
            return
        aliases = self.global_settings.get("tab_aliases", {})
        if alias:
            aliases[repo_path] = alias
        elif repo_path in aliases:
            del aliases[repo_path]
        self.global_settings["tab_aliases"] = aliases
        save_global_settings(self.global_settings)

        tab = self.tabs.get(tab_name)
        if tab is not None:
            self._refresh_tab_label(tab)
            if hasattr(tab, "refresh_tab_name_label"):
                tab.refresh_tab_name_label()

    def get_tab_display_name(self, repo_path):
        aliases = self.global_settings.get("tab_aliases", {})
        return aliases.get(repo_path, Path(repo_path).name)

    def find_known_repo(self, path):
        """Return (existing_raw_path, kind) if `path` matches an
        already-known repo, else None. `kind` is 'open' or 'hidden'."""
        def norm(p):
            try:
                return str(Path(p).resolve())
            except Exception:
                return str(p).rstrip("/\\")

        target = norm(path)
        for raw in self.tab_paths.values():
            if norm(raw) == target:
                return raw, "open"
        for raw in self.global_settings.get("hidden_repos", []):
            if norm(raw) == target:
                return raw, "hidden"
        return None

    def change_repo_directory(self, tab_name, new_path):
        """Re-point an open tab to a different repo folder in place."""
        from tkinter import messagebox

        new_path = str(Path(new_path))
        old_path = str(self.tab_paths.get(tab_name, ""))
        if not old_path or new_path == old_path:
            return True

        tab = self.tabs.get(tab_name)
        if tab is None:
            return False

        git = self.global_settings.get("git_binary", "git")
        if not is_git_repo(new_path, git):
            messagebox.showerror(
                "Error", f"'{new_path}' is not a valid Git repository.",
                parent=self,
            )
            return False
        if new_path in self.tab_paths.values():
            messagebox.showinfo(
                "Info", "This repository is already open in another tab.",
                parent=self,
            )
            return False

        tab.repo_path = Path(new_path)
        tab.base_tab_name = Path(new_path).name
        self.tab_paths[tab_name] = new_path

        s = self.global_settings
        for key in ("branch_update_enabled", "tab_aliases", "polling_states"):
            d = s.get(key)
            if isinstance(d, dict) and old_path in d:
                d[new_path] = d.pop(old_path)
        hidden = s.get("hidden_repos", [])
        if old_path in hidden:
            hidden[hidden.index(old_path)] = new_path
        save_global_settings(s)

        self._refresh_tab_label(tab)
        if hasattr(tab, "refresh_tab_name_label"):
            tab.refresh_tab_name_label()

        self.save_current_repos()
        return True
