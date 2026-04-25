# GitHerd

**Real-time Git branch synchronizer**

Keep multiple Git branches aligned in real-time. Ideal for parallel AI coding sessions (Claude Code, Cursor, Copilot) or any workflow with multiple active branches.

## Features

- 🔄 **Real-time polling** — Configurable interval per repo with countdown display
- ⚡ **Auto fast-forward** — Single branch ahead? Sync automatically
- 🔀 **Smart merge detection** — Multiple branches? Check for disjoint files
- 🔔 **Sound notifications** — Different sounds for commits, success, and errors
- 🔔 **Desktop notifications** — System notifications via notify-send
- 🗑 **Branch cleanup** — Delete branches from the UI
- 🔘 **Per-branch toggle** — Enable/disable sync per branch with persistence
- 📌 **Always on top** — Never lose sight of your sync status
- 📂 **Multi-repo support** — Manage multiple repositories in tabs
- 💾 **Session persistence** — Repos are remembered between sessions
- ⚙️ **GUI configuration** — Edit settings without touching config files
- 🔍 **Auto-detection** — Remote and main branch detected automatically
- 📊 **Status in title** — Window title shows repo count and polling status
- 📝 **Log export** — Save logs to file for debugging
- 🎛️ **Compact mode** — Hide buttons and logs for minimal UI

## How it works

| Situation | Action |
|-----------|--------|
| Nothing to do | 🟢 Idle |
| Empty remote (no main branch) | Bootstrap push main |
| Local main ahead | Auto push |
| Branches behind main | Auto push to sync |
| 1 branch ahead (no divergence) | Fast-forward + push |
| 1+ diverged branch, disjoint files | 🟡 Merge button |
| 1+ diverged branch, common files | 🔴 STOP |
| 2+ branches ahead, disjoint files | 🟡 Merge button |
| 2+ branches ahead, common files | 🔴 STOP |
| Git error (remote not found, etc.) | 🔴 Tab disabled |

**Deterministic. No heuristics. No magic.**

## Installation
```bash
git clone https://github.com/Jacques66/GitHerd.git
```

## Usage

Simply run GitHerd from anywhere:
```bash
/path/to/GitHerd/githerd
```

Or add GitHerd to your PATH and run:
```bash
githerd
```

### Adding repositories

1. **Menu Fichier > Ajouter un repo** (or `Ctrl+O`)
2. Select a Git repository folder
3. Remote and main branch are **auto-detected**
4. A `githerd.toml` config file is created with detected values
5. A new tab opens with that repository

### Managing tabs

- **Middle-click** on a tab to hide it (make it inactive — stops polling, keeps settings)
- **Right-click** on a tab to show the context menu:
  - **Run** — trigger an immediate sync for this repo
  - **Options...** — open the repo configuration dialog
  - **Rename tab...** — set a custom alias for the tab
  - **Hide tab** — same as middle-click
  - **Close** — remove the tab
- Repositories are saved automatically and restored on next launch
- Hidden (inactive) repos can be reactivated from **Repository > Inactive repos**
- Each tab has its own polling, status, and log

#### Tab renaming

Right-click on any tab to rename it with a custom alias:
- Aliases are persistent across restarts
- Leave empty to reset to original folder name
- Aliases appear in both the tab and the Inactive repos submenu

**Tab indicators (background colors):**
- Green background = Polling active
- Gray background = Polling inactive
- Red background = STOP (action required or error)
- `● Name` = Update detected (click tab to clear)

### Recent activity status bar

A thin bar at the bottom of the main window shows the **most recent meaningful sync event** across all repositories — useful for identifying which repo just beeped.

Format: `HH:MM:SS  repo-alias  —  <event>`

Events recorded include: new commit detected, pull/push completed, branches synced, merges, STOP states, and remote initialization. Idle "nothing to do" syncs are skipped.

- **Click the bar** to open a popup listing the last N events (with timestamps and repo names).
- The number of entries kept is configurable in **Global Settings → "Recent activity entries kept"** (default 5, choices: 3 / 5 / 10 / 20).
- Events are kept in memory only and reset on restart.

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Add a repository |
| `Ctrl+S` | Stop all polling |
| `Ctrl+R` | Restart (if no action is active) |
| `Ctrl+Q` | Quit |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+M` | Toggle compact mode |

### Menu Repository

The **Repository** menu changes dynamically based on the currently selected tab:
- **Options / Open folder** — Edit repo settings, open in file manager
- **Sync now / Polling** — Control sync operations
- **Branch toggles** — Enable/disable sync per branch (✓ = enabled)
- **Delete branches** — Remove tracked branches
- **Close** — Close current tab
- **Inactive repos (N)** — Submenu listing hidden repos; click to reactivate

#### Per-branch sync toggle

Each tracked branch appears in the menu with a checkmark indicating its sync status:
- `✓ claude/branch-name` — Branch sync **enabled**
- `   claude/branch-name` — Branch sync **disabled** (default for new branches)

Click on a branch to toggle its status. Disabled branches are:
- Excluded from all sync operations (including push after merge)
- Still visible in the menu for re-enabling
- Persisted across restarts in `settings.json`

**Note:** Newly discovered branches are **disabled by default**. Enable "Enable sync for newly discovered branches" in Settings to change this behavior.

Non-existent branches are automatically cleaned from persistence on each sync.

### Configuration

#### Global settings (Menu ? > Settings)

| Setting | Description |
|---------|-------------|
| Mode (dark/light/system) | Appearance mode |
| Color theme | Color theme (blue, dark-blue, green) |
| Font zoom | UI font scale factor (default: `1.0`) |
| Git binary | Path to git executable (default: `git`) |
| Auto-start polling | Start polling automatically when adding a repo |
| Start collapsed | Start with log panel hidden |
| Advanced mode | Compact UI with tab interactions (see below) |
| Desktop notifications | Enable system notifications (notify-send) |
| Restore polling state on restart | Remember and restore polling state per repo |
| Enable sync for newly discovered branches | Enable sync by default for new branches (default: **off**) |

Stored in `~/.config/githerd/settings.json`

### Advanced mode

When enabled, the UI is simplified:
- **Single click** on a tab: select it, or toggle polling if already selected
- **Double click** on a tab: sync now (works on any tab, not just the active one)
- Buttons (Start/Stop polling, Sync now, Options, Close) are hidden
- Log toggle button is moved next to the status line
- **Branch deletion**: no confirmation dialog (branches are deleted immediately)

#### Per-repo settings (Menu Repository > Configuration)

| Setting | Description |
|---------|-------------|
| Remote | Git remote name (auto-detected) |
| Main branch | Main branch name (auto-detected) |
| Branch prefix | Prefix of branches to track (default: `claude/`) |
| Interval | Polling interval in seconds (default: `60`) |

Stored in `<repo>/githerd.toml`

### Config file format

```toml
[git]
remote = "origin"
main_branch = "main"
branch_prefix = "claude/"

[sync]
interval_seconds = 60
```

### Persistence

| File | Content |
|------|---------|
| `~/.config/githerd/repos.json` | List of open repositories |
| `~/.config/githerd/settings.json` | Global settings + polling states + branch sync states |
| `<repo>/githerd.toml` | Per-repo settings |

The `settings.json` file includes:
- `polling_states`: per-repo polling state (for restore on restart)
- `branch_update_enabled`: per-repo, per-branch sync enabled state
- `hidden_repos`: list of inactive repo paths
- `tab_aliases`: custom tab names (`{repo_path: "alias"}`)

## Requirements

### Python
- Python 3.11+
- tkinter (usually included with Python, or `sudo apt install python3-tk`)

### Installing Python dependencies
```bash
pip install -r requirements.txt
```

Or manually :
```bash
pip install customtkinter>=5.2.0
```

### Système
- Git

### Optional (Linux)
- `wmctrl` — For the mode "always-on-top"
- `pulseaudio-utils` — For audio notifications
- `libnotify-bin` — For desktop notifications

```bash
sudo apt install wmctrl pulseaudio-utils libnotify-bin
```

## Error handling

If Git is not functional in a repository (wrong remote, network error, etc.):

- The tab shows 🔴 **ERREUR — Git non fonctionnel**
- Polling and Sync buttons are **disabled**
- You can still access **Configuration** to fix settings
- After saving new settings, Git health is re-checked

## Why GitHerd?

When running multiple AI coding sessions (or multiple developers) on the same repository, branches can quickly diverge. Manual synchronization is tedious and error-prone.

GitHerd watches your branches and:
- **Automatically syncs** when safe (single branch, fast-forward possible)
- **Alerts you immediately** when intervention is needed
- **Helps you merge safely** when files don't overlap

Catch divergences early (a few commits) instead of late (dozens of conflicts).

## License

MIT — Copyright (c) 2025 InZeMobile

## Author

Jacques Lovi. - [InZeMobile](https://github.com/Jacques66)
