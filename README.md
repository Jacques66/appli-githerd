# GitHerd

**Real-time Git branch synchronizer**

Keep multiple Git branches aligned in real-time. Ideal for parallel AI coding sessions (Claude Code, Cursor, Copilot) or any workflow with multiple active branches.

## Features

- 🔄 **Real-time polling** — Configurable interval (default 10s)
- ⚡ **Auto fast-forward** — Single branch ahead? Sync automatically
- 🔀 **Smart merge detection** — Multiple branches? Check for disjoint files
- 🔔 **Sound notification** — Know instantly when commits arrive
- 🗑 **Branch cleanup** — Delete branches from the UI
- 📌 **Always on top** — Never lose sight of your sync status

## How it works

| Situation | Action |
|-----------|--------|
| Nothing to do | 🟢 Idle |
| Local main ahead | Auto push |
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

1. Copy `githerd.toml` to your project root
2. Edit the configuration as needed
3. Run from your project directory:
```bash
python /path/to/GitHerd/githerd.py
```

Or add GitHerd to your PATH and run:
```bash
cd your-project
githerd
```

## Configuration

Create `githerd.toml` in your project root:
```toml
[git]
binary = "git"
remote = "origin"
main_branch = "main"
branch_prefix = "claude/"

[sync]
interval_seconds = 10

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
