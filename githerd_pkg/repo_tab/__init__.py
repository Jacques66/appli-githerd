# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab module.

Main class for repository tab content.
"""

import threading
from pathlib import Path
import customtkinter as ctk

from ..config import load_repo_config
from .ui import RepoTabUIMixin
from .sync import RepoTabSyncMixin
from .polling import RepoTabPollingMixin
from .dialogs import RepoTabDialogsMixin


class RepoTabContent(
    RepoTabUIMixin,
    RepoTabSyncMixin,
    RepoTabPollingMixin,
    RepoTabDialogsMixin,
    ctk.CTkFrame
):
    """Content of a tab managing a single Git repository."""

    def __init__(self, parent, repo_path, app, tab_name):
        super().__init__(parent)

        self.repo_path = Path(repo_path)
        self.app = app
        self.tab_name = tab_name
        self.git = app.global_settings.get("git_binary", "git")

        # Load repo config
        self.repo_config = load_repo_config(repo_path)
        self.remote = self.repo_config["remote"]
        self.main = self.repo_config["main_branch"]
        self.prefix = self.repo_config["branch_prefix"]
        self.interval = self.repo_config["interval_seconds"]

        # State
        self.lock = threading.Lock()
        self.polling = False
        self.polling_thread = None
        self.stop_event = threading.Event()
        self.log_visible = not self.app.global_settings.get("start_collapsed", False)
        self.last_commit_count = {}
        self.pending_branches = []
        self.git_healthy = True
        self.git_error = ""
        self.sync_error = False  # red tab on mid-sync failures (pull/push refused, etc.)
        self.next_poll_time = 0
        self.countdown_job = None
        self.has_update = False
        self.syncing = False
        self.base_tab_name = Path(repo_path).name
        self.advanced_mode = self.app.global_settings.get("advanced_mode", False)

        # Build UI
        self._build_ui()

        # Start initial scan
        threading.Thread(target=self.initial_scan, daemon=True).start()


__all__ = ["RepoTabContent"]
