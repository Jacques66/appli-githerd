# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab polling mixin.

Handles polling loop, countdown, and initial scan.
"""

import time
import threading

from ..config import load_repo_config
from ..git_utils import (
    run_git, get_tracked_branches, commits_ahead, commits_behind,
    local_main_ahead, are_files_disjoint, check_git_health, get_short_head,
    get_remote_url
)


class RepoTabPollingMixin:
    """Mixin for polling and initial scan operations."""

    def check_and_update_health(self):
        """Check git health and update UI accordingly.

        On failure, dump diagnostic context to the log textbox so the
        user can see WHY the health check failed (which command, what
        stderr, the remote URL, the git binary used).
        """
        ok, err = check_git_health(self.repo_path, self.remote, self.main, self.git)
        self.git_healthy = ok
        self.git_error = err

        if not ok:
            self.log_msg(f"Health check FAILED: {err}")
            self.log_msg(f"  repo path : {self.repo_path}")
            self.log_msg(f"  git binary: {self.git}")
            self.log_msg(f"  remote    : {self.remote}")
            url = get_remote_url(self.remote, cwd=self.repo_path, git=self.git)
            if url:
                self.log_msg(f"  remote URL: {url}")
            else:
                self.log_msg(f"  remote URL: (could not resolve)")
            self.disable_tab(err)
        else:
            self.enable_tab()

        return ok

    def initial_scan(self):
        """Perform initial repository scan."""
        if not self.check_and_update_health():
            self.log_msg(f"Error: {self.git_error}")
            return

        try:
            run_git([self.git, "fetch", self.remote], cwd=self.repo_path)

            local_ahead = local_main_ahead(self.remote, self.main,
                                          cwd=self.repo_path, git=self.git)
            if local_ahead > 0:
                self.state_label.configure(text="Local main ahead")
                self.info_label.configure(text=f"+{local_ahead} commits to push — click Sync now")
                return

            branches = get_tracked_branches(self.remote, self.prefix,
                                           cwd=self.repo_path, git=self.git)

            ahead_list = []
            diverged_list = []

            for b in branches:
                ahead = commits_ahead(f"{self.remote}/{self.main}", b,
                                     cwd=self.repo_path, git=self.git)
                behind = commits_behind(f"{self.remote}/{self.main}", b,
                                       cwd=self.repo_path, git=self.git)

                if ahead > 0:
                    short_name = b.replace(f"{self.remote}/", "")
                    self.last_commit_count[short_name] = ahead

                    if behind > 0:
                        diverged_list.append((short_name, ahead, behind))
                    else:
                        ahead_list.append(short_name)

            total = len(ahead_list) + len(diverged_list)

            if total == 0:
                behind_list = []
                for b in branches:
                    behind = commits_behind(f"{self.remote}/{self.main}", b,
                                           cwd=self.repo_path, git=self.git)
                    if behind > 0:
                        short_name = b.replace(f"{self.remote}/", "")
                        behind_list.append((short_name, behind))

                if behind_list:
                    names = [f"{b[0]} (-{b[1]})" for b in behind_list]
                    self.state_label.configure(text="Branches behind")
                    self.info_label.configure(text=f"To synchronize: {', '.join(names)}")
                else:
                    self.state_label.configure(text="Idle")
                    self.info_label.configure(text="All branches are synchronized")
            elif len(diverged_list) == 0 and len(ahead_list) == 1:
                self.state_label.configure(text="1 branch ahead")
                self.info_label.configure(text=f"Ready to sync: {ahead_list[0]}")
            else:
                all_names = [b[0] for b in diverged_list] + ahead_list
                self.pending_branches = all_names

                disjoint = are_files_disjoint(all_names, f"{self.remote}/{self.main}",
                                             self.remote, cwd=self.repo_path, git=self.git)

                if len(diverged_list) > 0:
                    diverged_info = [f"{b[0]} (+{b[1]}/-{b[2]})" for b in diverged_list]
                    msg = f"Diverged: {', '.join(diverged_info)}"
                else:
                    msg = f"Multiple branches: {', '.join(all_names)}"

                if disjoint:
                    self.state_label.configure(text="STOP — Merge possible")
                    self.info_label.configure(text=f"Disjoint files. {msg}")
                    self.after(100, self.show_merge_button)
                    self.app.record_event(self.tab_name, get_short_head(self.repo_path, self.git))
                else:
                    self.state_label.configure(text="STOP — Human action required")
                    self.info_label.configure(text=msg)
                    self.app.record_event(self.tab_name, get_short_head(self.repo_path, self.git))

                self.after(0, lambda: self.app.update_tab_color(self))

        except Exception as e:
            self.state_label.configure(text="ERROR")
            self.info_label.configure(text=str(e))
            self.after(0, lambda: self.app.update_tab_color(self))

    def polling_loop(self):
        """Polling loop running in its own thread.

        Uses stop_event for clean shutdown:
        - Thread waits for either timeout or stop signal
        - Current sync always completes before stopping
        """
        while not self.stop_event.is_set():
            self.sync()  # Blocking - completes before checking stop_event

            # Reload interval (may have changed)
            try:
                cfg = load_repo_config(self.repo_path)
                interval = cfg.get("interval_seconds", self.interval)
            except:
                interval = self.interval

            self.next_poll_time = time.time() + interval

            # Wait for interval OR stop signal
            # wait() returns True if event is set, False on timeout
            if self.stop_event.wait(timeout=interval):
                break  # Stop signal received

    def toggle_polling(self):
        """Toggle polling on/off."""
        if not self.git_healthy:
            return

        if self.polling:
            # Stop polling
            self.polling = False
            self.stop_event.set()  # Signal thread to stop
            self.btn_poll.configure(text="▶ Start polling")
            self.stop_countdown()
        else:
            # Start polling
            self.polling = True
            self.stop_event.clear()  # Reset event
            self.btn_poll.configure(text="⏸ Stop polling")
            self.next_poll_time = time.time() + self.interval
            self.start_countdown()
            self.polling_thread = threading.Thread(
                target=self.polling_loop,
                daemon=True,
                name=f"polling-{self.tab_name}"
            )
            self.polling_thread.start()

        self.app.update_tab_color(self)
        self.app.update_title()

    def stop_polling(self):
        """Stop polling."""
        self.polling = False
        self.btn_poll.configure(text="▶ Start polling")
        self.stop_countdown()
        self.after(0, lambda: self.app.update_tab_color(self))

    def wait_for_polling_thread(self, timeout=None):
        """Wait for polling thread to finish.

        Args:
            timeout: Max wait time in seconds (None = infinite)
        Returns:
            True if thread stopped, False if timeout
        """
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=timeout)
            return not self.polling_thread.is_alive()
        return True

    def start_countdown(self):
        """Start the countdown display."""
        self.update_countdown()

    def stop_countdown(self):
        """Stop the countdown display."""
        if self.countdown_job:
            self.after_cancel(self.countdown_job)
            self.countdown_job = None
        self.countdown_label.configure(text="")
        self._set_button_countdown(0)

    def update_countdown(self):
        """Update the countdown display."""
        if not self.polling:
            self.countdown_label.configure(text="")
            self._set_button_countdown(0)
            return

        remaining = int(self.next_poll_time - time.time())
        if remaining > 0:
            self.countdown_label.configure(text=f"(next sync: {remaining}s)")
            self._set_button_countdown(remaining)
        else:
            self.countdown_label.configure(text="(sync...)")
            self._set_button_countdown(0)

        self.countdown_job = self.after(1000, self.update_countdown)

    def _set_button_countdown(self, seconds):
        """Push countdown to the corresponding TabButton if it exists."""
        btn = self.app.tab_buttons.get(self.tab_name)
        if btn and hasattr(btn, "set_countdown"):
            btn.set_countdown(seconds)

    def _mark_if_not_active(self):
        """Mark tab as updated if not active."""
        try:
            if self.app.current_tab != self.tab_name:
                self.app.mark_tab_updated(self)
        except Exception:
            pass
