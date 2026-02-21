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
    "branch_update_enabled": {},
    "sync_new_branches_by_default": False,
    "hidden_repos": [],  # List of hidden (inactive) repo paths
    "tab_aliases": {}  # {repo_path: "alias"} for custom tab names
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
    toml_content = f'''[git]
remote = "{config['remote']}"
main_branch = "{config['main_branch']}"
branch_prefix = "{config['branch_prefix']}"

[sync]
interval_seconds = {config['interval_seconds']}
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
