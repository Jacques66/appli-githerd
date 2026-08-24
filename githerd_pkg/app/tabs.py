# -*- coding: utf-8 -*-
"""
GitHerd — App tabs mixin.

Real OS-style tabs via ttk.Notebook. Per-tab polling/health status is
shown as a colored dot on the tab (green = polling, red = error/STOP,
gray = idle); the countdown and update marker live in the tab label.
"""

import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import customtkinter as ctk

from ..config import (
    load_global_settings, save_global_settings, load_repo_config,
    save_repo_config
)
from ..git_utils import is_git_repo, detect_repo_settings
from ..repo_tab import RepoTabContent


class AppTabsMixin:
    """Mixin for tab management."""

    # ------------------------------------------------------------------
    # Notebook container, style, and status dots
    # ------------------------------------------------------------------

    def _build_tabs_container(self):
        """Create the ttk.Notebook that hosts all repo tabs. Called from
        App.__init__ and rebuild_ui (replaces the old tab_bar + content
        container)."""
        self._style_notebook()
        self._init_status_dots()

        self.notebook = ttk.Notebook(self, style="GitHerd.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
        # DnD reorder + advanced double-click + middle/right click
        self.notebook.bind("<ButtonPress-1>", self._on_nb_press, add="+")
        self.notebook.bind("<B1-Motion>", self._on_nb_motion, add="+")
        self.notebook.bind("<ButtonRelease-1>", self._on_nb_release, add="+")
        self.notebook.bind("<Double-Button-1>", self._on_nb_double, add="+")
        self.notebook.bind("<Button-2>", self._on_nb_middle, add="+")
        self.notebook.bind("<Button-3>", self._on_nb_right, add="+")

    def _style_notebook(self):
        """Style ttk.Notebook to match the CustomTkinter dark/light theme."""
        dark = (ctk.get_appearance_mode() == "Dark")
        if dark:
            bg = "#2b2b2b"
            tab_bg = "#3d3d3d"
            tab_fg = "#dddddd"
            sel_bg = "#1f6aa5"
            sel_fg = "#ffffff"
        else:
            bg = "#dbdbdb"
            tab_bg = "#c8c8c8"
            tab_fg = "#000000"
            sel_bg = "#3a7ebf"
            sel_fg = "#ffffff"

        style = ttk.Style(self)
        try:
            style.theme_use("default")  # most restylable base theme
        except Exception:
            pass
        style.configure("GitHerd.TNotebook", background=bg, borderwidth=0)
        style.configure(
            "GitHerd.TNotebook.Tab",
            background=tab_bg, foreground=tab_fg,
            padding=[12, 5], borderwidth=0,
        )
        style.map(
            "GitHerd.TNotebook.Tab",
            background=[("selected", sel_bg), ("active", "#4a4a4a" if dark else "#bcbcbc")],
            foreground=[("selected", sel_fg)],
        )

    def _init_status_dots(self):
        """Create (once) the small colored status-dot images used on
        each tab. Kept referenced on self so Tk doesn't GC them."""
        if getattr(self, "_status_dots", None):
            return
        self._status_dots = {
            "green": self._make_status_dot("#4ade80"),
            "red": self._make_status_dot("#ff5555"),
            "default": self._make_status_dot("#888888"),
        }

    def _make_status_dot(self, color, size=12):
        """Return a small filled-circle PhotoImage of `color`."""
        img = tk.PhotoImage(width=size, height=size)
        cx = cy = (size - 1) / 2.0
        r = size / 2.0 - 0.5
        for y in range(size):
            for x in range(size):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    img.put(color, to=(x, y))
                else:
                    try:
                        img.transparency_set(x, y, True)
                    except Exception:
                        pass
        return img

    def _status_dot_for(self, bg_state):
        dots = getattr(self, "_status_dots", None) or {}
        return dots.get(bg_state, dots.get("default"))

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
        """Log entering/leaving the red state to the tab's own log:
        orange when it turns red (with the reason), green when it
        recovers. Other transitions are not logged."""
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

    def _tab_label(self, tab):
        """Build the tab's text: [update marker] alias [countdown]."""
        name = self.get_tab_display_name(str(tab.repo_path))
        secs = getattr(tab, "_countdown_secs", 0)
        if tab.polling and secs and secs > 0:
            name = f"{name}  {secs}"
        if getattr(tab, "has_update", False):
            name = "● " + name
        return name

    def _refresh_tab_label(self, tab):
        """Update just the tab's text (alias / countdown / marker)."""
        content = self.tab_frames.get(tab.tab_name)
        if content is None:
            return
        try:
            self.notebook.tab(content, text=self._tab_label(tab))
        except Exception:
            pass

    def set_tab_countdown(self, tab_name, seconds):
        """Called (main thread) from the polling countdown to refresh the
        seconds shown in the tab label."""
        tab = self.tabs.get(tab_name)
        if tab is None:
            return
        tab._countdown_secs = seconds or 0
        self._refresh_tab_label(tab)

    def update_tab_color(self, tab):
        """Re-derive the tab's status dot + label from polling/health.

        Skips the dot image write when the state hasn't changed (cheap
        enough for the 1.5s reconciler); the label is always refreshed
        (setting the same text is a no-op)."""
        content = self.tab_frames.get(tab.tab_name)
        if content is None:
            return

        bg_state = self.get_tab_bg_state(tab)

        # Log red<->recovery transitions once, keyed on bg_state alone.
        prev_bg = getattr(tab, "_last_bg_state", None)
        if bg_state != prev_bg:
            tab._last_bg_state = bg_state
            if prev_bg is not None:  # skip the very first paint at startup
                self._log_color_transition(tab, prev_bg, bg_state)
            dot = self._status_dot_for(bg_state)
            try:
                self.notebook.tab(content, image=dot, compound="left")
            except Exception:
                pass

        self._refresh_tab_label(tab)
        self.update_title()

    def _reconcile_tab_colors(self):
        """Periodic safety net: re-derive every tab's status from the
        live polling/health/error state, so the dot can never disagree
        with reality even if a code path forgot to call update_tab_color.
        """
        try:
            for tab in self.tabs.values():
                self.update_tab_color(tab)
        except Exception:
            pass
        self.after(1500, self._reconcile_tab_colors)

    # ------------------------------------------------------------------
    # Periodic automation loops (unchanged behavior)
    # ------------------------------------------------------------------

    def _tab_in_error(self, tab):
        """True if the tab is in a recoverable error state — git
        unhealthy (connection/remote problem) or a mid-sync failure.
        The STOP-merge state (pending_branches) is deliberately
        excluded: it needs a human decision, not a reconnect."""
        return (not tab.git_healthy) or getattr(tab, "sync_error", False)

    def _retry_errored_repos(self):
        """Periodic recovery loop. When enabled, spawns a worker per
        errored repo to re-check health and re-sync."""
        settings = self.global_settings
        if settings.get("auto_retry_errored", False) and not getattr(self, "_polling_circuit_open", False):
            for tab in self.tabs.values():
                if self._tab_in_error(tab) and not tab.lock.locked():
                    threading.Thread(target=tab.retry_recovery, daemon=True).start()
        interval = max(5, int(settings.get("auto_retry_interval_seconds", 60)))
        self.after(interval * 1000, self._retry_errored_repos)

    def _watch_idle_repos(self):
        """Periodic idle-watch loop. When enabled (interval > 0), spawns
        a worker per idle healthy repo to detect pending work and
        auto-start polling."""
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
        """Stop polling on repos inactive for `inactivity_disable_hours`
        hours (0 = off). Clean stop; the idle-watch can restart them."""
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
        """Mark tab as having an update."""
        if not tab.has_update:
            tab.has_update = True
            self.update_tab_color(tab)

    def clear_tab_marker(self, tab):
        """Clear update marker from tab."""
        if tab.has_update:
            tab.has_update = False
            self.update_tab_color(tab)

    # ------------------------------------------------------------------
    # Add / switch / close / hide tabs
    # ------------------------------------------------------------------

    def add_repo(self, repo_path, switch_to=True):
        """Add a repository tab."""
        repo_name = Path(repo_path).name

        # Handle duplicate names
        tab_name = repo_name
        counter = 1
        while tab_name in self.tabs:
            counter += 1
            tab_name = f"{repo_name} ({counter})"

        display_name = self.get_tab_display_name(repo_path)

        # Content is a page of the notebook.
        tab_content = RepoTabContent(self.notebook, repo_path, self, tab_name)
        self.tab_frames[tab_name] = tab_content
        self.tabs[tab_name] = tab_content
        self.tab_paths[tab_name] = repo_path

        self.notebook.add(
            tab_content, text=display_name,
            image=self._status_dot_for("default"), compound="left",
        )

        if switch_to:
            self.switch_tab(tab_name)
        self.after(100, self.update_title)

        # Auto-start polling if enabled AND restore_polling disabled
        if self.global_settings.get("auto_start_polling", False) and not self.global_settings.get("restore_polling", False):
            self.after(500, tab_content.toggle_polling)

    def _name_from_widget(self, widget_id):
        """Map a notebook tab id (widget path) back to a tab name."""
        wid = str(widget_id)
        for name, content in self.tab_frames.items():
            if str(content) == wid:
                return name
        return None

    def _on_notebook_tab_changed(self, event=None):
        """Native tab selection changed → track current tab, clear the
        update marker, refresh the Repository menu."""
        try:
            current = self.notebook.select()
        except Exception:
            return
        if not current:
            self.current_tab = None
            return
        name = self._name_from_widget(current)
        if not name:
            return
        self.current_tab = name
        tab = self.tabs.get(name)
        if tab is not None and getattr(tab, "has_update", False):
            tab.has_update = False
            self.update_tab_color(tab)
        try:
            self.update_repo_menu()
        except Exception:
            pass

    def switch_tab(self, tab_name):
        """Select the given tab (fires <<NotebookTabChanged>>)."""
        content = self.tab_frames.get(tab_name)
        if content is None:
            return
        try:
            self.notebook.select(content)
        except Exception:
            pass

    def on_tab_double_click(self, tab_name):
        """Advanced mode: double-click a tab → sync now."""
        if self.global_settings.get("advanced_mode", False):
            tab = self.tabs.get(tab_name)
            if tab and tab.git_healthy:
                tab.manual_sync()

    def _forget_tab(self, tab_name):
        """Remove a tab from the notebook and destroy its content."""
        content = self.tab_frames.get(tab_name)
        if content is not None:
            try:
                self.notebook.forget(content)
            except Exception:
                pass

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

        self._forget_tab(tab_name)
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
        """Close current repository tab."""
        if not self.tabs or not self.current_tab:
            return
        self.close_tab(self.current_tab)

    # ------------------------------------------------------------------
    # Notebook mouse handling: click identify, DnD, middle/right menu
    # ------------------------------------------------------------------

    def _notebook_tab_name_at(self, event):
        """Return the tab name under the pointer, or None if not on a tab."""
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return None
        try:
            tid = self.notebook.tabs()[idx]
        except Exception:
            return None
        return self._name_from_widget(tid)

    def _on_nb_double(self, event):
        name = self._notebook_tab_name_at(event)
        if name:
            self.on_tab_double_click(name)

    def _on_nb_middle(self, event):
        name = self._notebook_tab_name_at(event)
        if name:
            self.hide_repo(name)

    def _on_nb_right(self, event):
        name = self._notebook_tab_name_at(event)
        if name:
            self.on_tab_right_click(event, name)

    def _on_nb_press(self, event):
        """Start of a potential drag-reorder."""
        try:
            self._drag_index = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            self._drag_index = None
        self._drag_moved = False

    def _on_nb_motion(self, event):
        """Live-reorder: move the dragged tab to the slot under the pointer."""
        if getattr(self, "_drag_index", None) is None:
            return
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return
        if idx != self._drag_index:
            try:
                widget = self.notebook.tabs()[self._drag_index]
                self.notebook.insert(idx, widget)
                self._drag_index = idx
                self._drag_moved = True
            except Exception:
                pass

    def _on_nb_release(self, event):
        """Persist the new order if a drag actually happened."""
        if getattr(self, "_drag_moved", False):
            self._sync_order_from_notebook()
            self.save_current_repos()
        self._drag_index = None
        self._drag_moved = False

    def _sync_order_from_notebook(self):
        """Rebuild the tab dicts in the notebook's current tab order so
        persistence (repos.json) reflects the visible order."""
        order = []
        for tid in self.notebook.tabs():
            name = self._name_from_widget(tid)
            if name:
                order.append(name)

        def reorder(d):
            return {n: d[n] for n in order if n in d}
        self.tabs = reorder(self.tabs)
        self.tab_paths = reorder(self.tab_paths)
        self.tab_frames = reorder(self.tab_frames)

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

        self._forget_tab(tab_name)
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
        """Set or clear tab alias."""
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
        """Get display name for a repo (alias or folder name)."""
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
