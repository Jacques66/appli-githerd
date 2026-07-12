#!/usr/bin/env bash
#
# build_windows.sh — build a Windows GitHerd.exe from WSL.
#
# PyInstaller cannot cross-compile: to get a real .exe we must drive the
# *Windows* Python interpreter (python.exe under /mnt/c), not the Linux
# one. This script does exactly that.
#
# Usage:
#   ./build_windows.sh                # auto-detect Windows Python
#   PYWIN=/mnt/c/.../python.exe ./build_windows.sh   # explicit interpreter
#
# Output: dist/GitHerd.exe
#
set -euo pipefail

cd "$(dirname "$0")"

# --- locate the Windows Python interpreter --------------------------------
if [[ -z "${PYWIN:-}" ]]; then
    # Try the Windows `py` launcher first, then `python`, via WSL interop.
    if command -v py.exe >/dev/null 2>&1; then
        PYWIN="$(py.exe -0p 2>/dev/null | awk 'NF{print $NF; exit}' | tr -d '\r')"
    fi
    if [[ -z "${PYWIN:-}" ]] && command -v where.exe >/dev/null 2>&1; then
        PYWIN="$(where.exe python 2>/dev/null | head -n1 | tr -d '\r')"
    fi
fi

if [[ -z "${PYWIN:-}" ]]; then
    echo "ERROR: could not find a Windows Python interpreter." >&2
    echo "Install Python from python.org (Windows), then either:" >&2
    echo "  - re-run this script, or" >&2
    echo "  - set it explicitly: PYWIN='/mnt/c/.../python.exe' ./build_windows.sh" >&2
    exit 1
fi

# Convert a Windows path (C:\...) to a WSL path if needed.
if [[ "$PYWIN" == *:\\* || "$PYWIN" == *:/* ]]; then
    if command -v wslpath >/dev/null 2>&1; then
        PYWIN="$(wslpath -u "$PYWIN")"
    fi
fi

echo ">> Using Windows Python: $PYWIN"
"$PYWIN" --version

# --- dependencies ---------------------------------------------------------
echo ">> Installing/upgrading build dependencies (into the Windows Python)…"
"$PYWIN" -m pip install --upgrade pip >/dev/null
"$PYWIN" -m pip install --upgrade pyinstaller customtkinter

# --- build ----------------------------------------------------------------
# --collect-all customtkinter is REQUIRED: CTk ships theme/asset data files
# that PyInstaller misses otherwise, which crashes the exe at startup.
# --windowed hides the console window (GUI app).
echo ">> Building GitHerd.exe…"
"$PYWIN" -m PyInstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name GitHerd \
    --collect-all customtkinter \
    main.py

echo
echo ">> Done. Executable at: dist/GitHerd.exe"
echo "   (First launch may be slow — one-file builds unpack to a temp dir.)"
