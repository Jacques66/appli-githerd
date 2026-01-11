# GitHerd

**Real-time Git branch synchronizer**

Keep multiple Git branches aligned in real-time. Ideal for parallel AI coding sessions (Claude Code, Cursor, Copilot) or any workflow with multiple active branches.

## Features

- 🔄 **Real-time polling** — Configurable interval (default 60s)
- ⚡ **Auto fast-forward** — Single branch ahead? Sync automatically
- 🔀 **Smart merge detection** — Multiple branches? Check for disjoint files
- 🔔 **Sound notification** — Know instantly when commits arrive
- 🗑 **Branch cleanup** — Delete branches from the UI
- 📌 **Always on top** — Never lose sight of your sync status
- 📂 **Multi-repo support** — Manage multiple repositories in tabs
- 💾 **Session persistence** — Repos are remembered between sessions

## How it works

| Situation | Action |
|-----------|--------|
| Nothing to do | 🟢 Idle |
| Local main ahead | Auto push |
| Branches behind main | Auto push to sync |
| 1 branch ahead (no divergence) | Fast-forward + push |
| 1+ diverged branch, disjoint files | 🟡 Merge button |
| 1+ diverged branch, common files | 🔴 STOP |
| 2+ branches ahead, disjoint files | 🟡 Merge button |
| 2+ branches ahead, common files | 🔴 STOP |

**Deterministic. No heuristics. No magic.**

## Installation
```bash
git clone https://github.com/Jacques66/GitHerd.git
```

## Usage

Simply run GitHerd from anywhere:
```bash
python /path/to/GitHerd/githerd.py
```

Or add GitHerd to your PATH and run:
```bash
githerd
```

### Adding repositories

1. Click **"➕ Ajouter un repo"** to open the folder selector
2. Select a Git repository folder
3. A new tab opens with that repository

### Managing tabs

- **Right-click** on a tab to close it
- Repositories are saved automatically and restored on next launch
- Each tab has its own polling, status, and log

### Per-repo configuration (optional)

For custom settings, copy `githerd-template.toml` to your project as `githerd.toml`:
```bash
cp /path/to/GitHerd/githerd-template.toml /path/to/your-project/githerd.toml
```

If no `githerd.toml` exists in a repo, default settings are used.

## Configuration

```toml
[git]
binary = "git"
remote = "origin"
main_branch = "main"
branch_prefix = "claude/"

[sync]
interval_seconds = 60

[ui]
font_zoom = 1.6
```

### Options

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `git` | `binary` | `git` | Path to Git executable |
| `git` | `remote` | `origin` | Remote name |
| `git` | `main_branch` | `main` | Main branch name |
| `git` | `branch_prefix` | `claude/` | Prefix of branches to track |
| `sync` | `interval_seconds` | `60` | Polling interval in seconds |
| `ui` | `font_zoom` | `1.6` | UI font scale factor |

### Persistence

Open repositories are saved to `~/.config/githerd/repos.json` and automatically restored on startup.

## Requirements

- Python 3.11+
- tkinter (usually included with Python)
- Git

### Optional (Linux)

- `wmctrl` — For always-on-top window
- `pulseaudio-utils` — For sound notifications
```bash
sudo apt install wmctrl pulseaudio-utils
```

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
