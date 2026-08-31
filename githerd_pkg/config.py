# -*- coding: utf-8 -*-
"""
GitHerd — Configuration and persistence module.

Handles global settings, repository configuration, and persistence.
"""

import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# ============================================================
# DURATION PARSING
# ============================================================

# Accept a bare number (= seconds) or a number with a unit suffix
# s/m/h/d (seconds/minutes/hours/days), case-insensitive, whitespace
# tolerant. Decimals allowed (rounded to whole seconds).
_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhdSMHD]?)\s*$")
_DURATION_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text):
    """Parse a duration string into whole seconds.

    Returns an int number of seconds, or None if the text is empty or
    invalid. A bare number is seconds; a trailing s/m/h/d applies the
    corresponding unit. 0 is valid (used by the "0 = off" fields).
    """
    if text is None:
        return None
    m = _DURATION_RE.match(str(text))
    if not m:
        return None
    value, unit = m.group(1), m.group(2).lower()
    try:
        seconds = float(value) * _DURATION_UNITS[unit]
    except (ValueError, KeyError):
        return None
    return int(round(seconds))

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
    "git_timeout_text": "30",   # Raw duration text as typed (display), e.g. "30", "2m"
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
    "active_interval_text": "60",
    "default_interval_seconds": 60,  # DEPRECATED: legacy per-repo seed; kept only to migrate to active_interval_seconds
    "hibernate_after_seconds": 900,  # After this inactivity, an active repo drops to slow "hibernation" polling (0 = off)
    "hibernate_after_text": "15m",
    "hibernate_interval_seconds": 300,  # Slow polling interval used while hibernating
    "hibernate_interval_text": "5m",
    "auto_retry_errored": False,  # Periodically try to recover repos that are in an error state
    "auto_retry_interval_seconds": 60,  # How often (seconds) to attempt recovery of errored repos
    "auto_retry_interval_text": "60",
    "watch_idle_interval_seconds": 0,  # Watch non-polling repos and auto-start polling on change (0 = off)
    "watch_idle_text": "0",
    "inactivity_disable_seconds": 0,  # Auto-STOP polling after this long without activity (0 = off; idle now hibernates instead)
    "inactivity_disable_text": "0"
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
                # For any duration field whose file lacks its *_text (older
                # files), seed the display text from the stored seconds value.
                # Done BEFORE the unit migrations below so those can override.
                for sec_key, text_key in (
                    ("git_timeout_seconds", "git_timeout_text"),
                    ("active_interval_seconds", "active_interval_text"),
                    ("hibernate_after_seconds", "hibernate_after_text"),
                    ("hibernate_interval_seconds", "hibernate_interval_text"),
                    ("auto_retry_interval_seconds", "auto_retry_interval_text"),
                    ("watch_idle_interval_seconds", "watch_idle_text"),
                    ("inactivity_disable_seconds", "inactivity_disable_text"),
                ):
                    if sec_key in data and text_key not in data:
                        settings[text_key] = str(settings.get(sec_key, 0))
                # Unit migrations: hibernate_after_minutes → *_seconds,
                # inactivity_disable_hours → *_seconds. Convert the value and
                # set a readable display text (overrides the generic seed above).
                if "hibernate_after_seconds" not in data and "hibernate_after_minutes" in data:
                    try:
                        mins = float(data["hibernate_after_minutes"])
                        settings["hibernate_after_seconds"] = int(mins * 60)
                        settings["hibernate_after_text"] = f"{mins:g}m" if mins else "0"
                    except (TypeError, ValueError):
                        pass
                if "inactivity_disable_seconds" not in data and "inactivity_disable_hours" in data:
                    try:
                        hours = float(data["inactivity_disable_hours"])
                        settings["inactivity_disable_seconds"] = int(hours * 3600)
                        settings["inactivity_disable_text"] = f"{hours:g}h" if hours else "0"
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
