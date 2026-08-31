# -*- coding: utf-8 -*-
"""
GitHerd — Configuration and persistence module.

Handles global settings, repository configuration, and persistence.
"""

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# ============================================================
# PATHS
# ============================================================

CONFIG_DIR = Path.home() / ".config" / "githerd"
REPOS_FILE = CONFIG_DIR / "repos.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_GLOBAL_SETTINGS = {
    "git_binary": "git",
    "git_timeout_seconds": 30,  # Timeout (seconds) for each git command before it is aborted
    "font_zoom": 1.0,
    "auto_start_polling": False,
    "start_collapsed": False,
    "advanced_mode": False,
    "desktop_notifications": True,
    "appearance_mode": "dark",
    "color_theme": "blue",
    "last_active_tab": "",
    "restore_polling": False,
    "polling_states": {},
    "hibernation_states": {},  # {repo_path: bool} — was the repo hibernating at last save
    "branch_update_enabled": {},
    "sync_new_branches_by_default": False,
    "hidden_repos": [],  # List of hidden (inactive) repo paths
    "tab_aliases": {},  # {repo_path: "alias"} for custom tab names
    "recent_sync_limit": 5,  # Number of recent meaningful syncs kept in the status bar
    "active_interval_seconds": 60,  # Global active (fast) polling interval, applies to every repo
    "default_interval_seconds": 60,  # DEPRECATED: legacy per-repo seed; kept only to migrate to active_interval_seconds
    "hibernate_after_minutes": 15,  # After this inactivity, an active repo drops to slow "hibernation" polling (0 = off)
    "hibernate_interval_seconds": 300,  # Slow polling interval used while hibernating
    "auto_retry_errored": False,  # Periodically try to recover repos that are in an error state
    "auto_retry_interval_seconds": 60,  # How often (seconds) to attempt recovery of errored repos
    "watch_idle_interval_seconds": 0,  # Watch non-polling repos and auto-start polling on change (0 = off)
    "inactivity_disable_hours": 0  # Auto-STOP polling after this many hours without activity (0 = off; idle now hibernates instead)
}

APPEARANCE_MODES = ["dark", "light", "system"]
COLOR_THEMES = ["blue", "dark-blue", "green"]

DEFAULT_REPO_CONFIG = {
    "remote": "origin",
    "main_branch": "main",
    "branch_prefix": "claude/",
    "interval_seconds": 60
}

# ============================================================
# GLOBAL SETTINGS
# ============================================================


def load_global_settings():
    """Load global settings from file."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                settings = DEFAULT_GLOBAL_SETTINGS.copy()
                settings.update(data)
                # Migration: the global active interval replaces the old
                # per-repo interval seeded from default_interval_seconds. If
                # a settings file predates active_interval_seconds, carry the
                # user's old default over so their cadence is preserved.
                if "active_interval_seconds" not in data and "default_interval_seconds" in data:
                    try:
                        settings["active_interval_seconds"] = int(data["default_interval_seconds"])
                    except (TypeError, ValueError):
                        pass
                return settings
        except Exception:
            pass
    return DEFAULT_GLOBAL_SETTINGS.copy()


def save_global_settings(settings):
    """Save global settings to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ============================================================
# REPO CONFIG
# ============================================================


def load_repo_config(repo_path):
    """Load repo config from githerd.toml, or use defaults."""
    config_file = Path(repo_path) / "githerd.toml"
    if config_file.exists():
        try:
            cfg = tomllib.load(open(config_file, "rb"))
            return {
                "remote": cfg.get("git", {}).get("remote", DEFAULT_REPO_CONFIG["remote"]),
                "main_branch": cfg.get("git", {}).get("main_branch", DEFAULT_REPO_CONFIG["main_branch"]),
                "branch_prefix": cfg.get("git", {}).get("branch_prefix", DEFAULT_REPO_CONFIG["branch_prefix"]),
                "interval_seconds": cfg.get("sync", {}).get("interval_seconds", DEFAULT_REPO_CONFIG["interval_seconds"])
            }
        except Exception:
            pass
    return DEFAULT_REPO_CONFIG.copy()


def save_repo_config(repo_path, config):
    """Save repo config to githerd.toml."""
    config_file = Path(repo_path) / "githerd.toml"
    # interval_seconds is legacy (the polling cadence is now a global setting,
    # active_interval_seconds). We still emit a value for backward/forward
    # compatibility with older builds, but it is no longer read by this one.
    interval = config.get("interval_seconds", DEFAULT_REPO_CONFIG["interval_seconds"])
    toml_content = f'''[git]
remote = "{config['remote']}"
main_branch = "{config['main_branch']}"
branch_prefix = "{config['branch_prefix']}"

[sync]
interval_seconds = {interval}
'''
    with open(config_file, "w") as f:
        f.write(toml_content)


# ============================================================
# REPOS LIST
# ============================================================


def load_saved_repos():
    """Load list of saved repositories."""
    if REPOS_FILE.exists():
        try:
            with open(REPOS_FILE, "r") as f:
                data = json.load(f)
                return data.get("repos", [])
        except Exception:
            pass
    return []


def save_repos(repos):
    """Save list of repositories."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPOS_FILE, "w") as f:
        json.dump({"repos": repos}, f, indent=2)


# ============================================================
# THEME
# ============================================================


def apply_theme_settings():
    """Apply saved theme settings at startup."""
    import customtkinter as ctk

    settings = load_global_settings()
    ctk.set_appearance_mode(settings.get("appearance_mode", "dark"))
    ctk.set_default_color_theme(settings.get("color_theme", "blue"))
    # Apply font/widget scaling
    font_zoom = settings.get("font_zoom", 1.0)
    ctk.set_widget_scaling(font_zoom)
    ctk.set_window_scaling(font_zoom)
