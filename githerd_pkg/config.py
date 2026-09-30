# -*- coding: utf-8 -*-
"""
GitHerd — Configuration and persistence module.

Handles global settings, repository configuration, and persistence.
"""

import json
import os
import re
import shutil
import sys
import threading
from pathlib import Path

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

# The ONE file GitHerd persists to: global settings + every known repo
# (one entry per repo). Always in the user's home, whatever directory
# GitHerd is launched from — nothing is ever written inside the repos.
CONFIG_FILE = Path.home() / ".githerd.json"

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
    # Per-repo state: {repo_path: value} maps in memory, stored inside
    # each repo's entry in the config file (see _REPO_STATE_FIELDS).
    "polling_states": {},
    "hibernation_states": {},  # {repo_path: bool} — was the repo hibernating at last save
    "branch_update_enabled": {},
    "hidden_repos": [],  # List of hidden (inactive) repo paths
    "tab_aliases": {},  # {repo_path: "alias"} for custom tab names
    "sync_new_branches_by_default": False,
    "recent_sync_limit": 5,  # Number of recent meaningful syncs kept in the status bar
    "active_interval_seconds": 60,  # Global active (fast) polling interval, applies to every repo
    "active_interval_text": "60",
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
}

# In-memory settings key → field of a repo entry in the config file.
_REPO_STATE_FIELDS = {
    "tab_aliases": "alias",
    "hidden_repos": "hidden",
    "polling_states": "polling",
    "hibernation_states": "hibernating",
    "branch_update_enabled": "branches",
}

# ============================================================
# CONFIG FILE
# ============================================================

# Settings and repo list share one file and are saved from several
# threads (polling threads save branch toggles), so every
# read-modify-write goes through this lock.
_file_lock = threading.RLock()


def _read_config():
    """Return the config file content as {"settings": {}, "repos": []}."""
    data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            # Keep a copy of the unreadable file: the next save would
            # otherwise replace it with an empty config.
            bad = CONFIG_FILE.with_name(CONFIG_FILE.name + ".bad")
            try:
                shutil.copyfile(CONFIG_FILE, bad)
            except OSError:
                pass
            print(f"[GitHerd] Unreadable {CONFIG_FILE} ({e!r}), copy kept as {bad}",
                  file=sys.stderr, flush=True)
            data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("settings", {})
    data.setdefault("repos", [])
    return data


def _write_config(data):
    """Write the config file atomically (never leaves a half-written file)."""
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, CONFIG_FILE)


def _new_repo_entry(repo_path):
    return {
        "path": repo_path,
        "alias": "",
        "hidden": False,
        **DEFAULT_REPO_CONFIG,
        "polling": False,
        "hibernating": False,
        "branches": {},
    }


def _find_repo(data, repo_path):
    repo_path = str(repo_path)
    for entry in data["repos"]:
        if entry.get("path") == repo_path:
            return entry
    return None

# ============================================================
# GLOBAL SETTINGS
# ============================================================


def load_global_settings():
    """Load global settings.

    Per-repo state stored in the repo entries is exposed as the
    {repo_path: value} maps (hidden_repos: list of paths) the UI uses.
    """
    with _file_lock:
        data = _read_config()
    settings = DEFAULT_GLOBAL_SETTINGS.copy()
    settings.update(data["settings"])
    repos = data["repos"]
    settings["tab_aliases"] = {e["path"]: e["alias"] for e in repos if e.get("alias")}
    settings["hidden_repos"] = [e["path"] for e in repos if e.get("hidden")]
    settings["polling_states"] = {e["path"]: bool(e.get("polling")) for e in repos}
    settings["hibernation_states"] = {e["path"]: bool(e.get("hibernating")) for e in repos}
    settings["branch_update_enabled"] = {
        e["path"]: dict(e["branches"]) for e in repos if e.get("branches")
    }
    return settings


def save_global_settings(settings):
    """Save global settings, and the per-repo state into each repo entry.

    State for a path that is not a known repo is dropped: the repo list
    (save_repos) decides which repos exist.
    """
    with _file_lock:
        data = _read_config()
        data["settings"] = {
            k: v for k, v in settings.items() if k not in _REPO_STATE_FIELDS
        }
        aliases = settings.get("tab_aliases", {})
        hidden = set(settings.get("hidden_repos", []))
        polling = settings.get("polling_states", {})
        hibernating = settings.get("hibernation_states", {})
        branches = settings.get("branch_update_enabled", {})
        for entry in data["repos"]:
            path = entry["path"]
            entry["alias"] = aliases.get(path, "")
            entry["hidden"] = path in hidden
            entry["polling"] = bool(polling.get(path, False))
            entry["hibernating"] = bool(hibernating.get(path, False))
            entry["branches"] = dict(branches.get(path, {}))
        _write_config(data)


# ============================================================
# REPO CONFIG
# ============================================================


def load_repo_config(repo_path):
    """Load a repo's git settings (remote, main branch, prefix), or defaults."""
    with _file_lock:
        entry = _find_repo(_read_config(), repo_path) or {}
    return {k: entry.get(k, v) for k, v in DEFAULT_REPO_CONFIG.items()}


def save_repo_config(repo_path, config):
    """Save a repo's git settings, creating its entry if it is new."""
    with _file_lock:
        data = _read_config()
        entry = _find_repo(data, repo_path)
        if entry is None:
            entry = _new_repo_entry(str(repo_path))
            data["repos"].append(entry)
        for k, v in DEFAULT_REPO_CONFIG.items():
            entry[k] = config.get(k, v)
        _write_config(data)


# ============================================================
# REPOS LIST
# ============================================================


def load_saved_repos():
    """Load the list of known repository paths (in tab order)."""
    with _file_lock:
        data = _read_config()
    return [e["path"] for e in data["repos"]]


def save_repos(repos):
    """Save the list of known repositories, in that order.

    Known repos keep their entry; a new path gets a default entry; a repo
    no longer listed is forgotten along with its settings.
    """
    with _file_lock:
        data = _read_config()
        existing = {e["path"]: e for e in data["repos"]}
        data["repos"] = [
            existing.get(path) or _new_repo_entry(path)
            for path in dict.fromkeys(str(p) for p in repos)
        ]
        _write_config(data)


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
