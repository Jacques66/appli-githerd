#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHerd — Real-time Git branch synchronizer

Keeps multiple Git branches aligned in real-time.
Ideal for parallel AI coding sessions (Claude Code, Cursor, etc.)
or any workflow with multiple active branches.

Copyright (c) 2026 InZeMobile
Licensed under the MIT License. See LICENSE file for details.

https://github.com/Jacques66/GitHerd
"""

import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
from datetime import datetime
import json
import os

# ============================================================
# CONFIG & PERSISTENCE
# ============================================================

CONFIG_DIR = Path.home() / ".config" / "githerd"
REPOS_FILE = CONFIG_DIR / "repos.json"

DEFAULT_CONFIG = {
    "git": {
        "binary": "git",
        "remote": "origin",
        "main_branch": "main",
        "branch_prefix": "claude/"
    },
    "sync": {
        "interval_seconds": 60
    },
    "ui": {
        "font_zoom": 1.6
    }
}

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def load_repo_config(repo_path):
    """Charge la config depuis githerd.toml du repo, ou utilise les valeurs par défaut."""
    config_file = Path(repo_path) / "githerd.toml"
    if config_file.exists():
        try:
            return tomllib.load(open(config_file, "rb"))
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def load_saved_repos():
    """Charge la liste des repos sauvegardés."""
    if REPOS_FILE.exists():
        try:
            with open(REPOS_FILE, "r") as f:
                data = json.load(f)
                return data.get("repos", [])
        except Exception:
            pass
    return []


def save_repos(repos):
    """Sauvegarde la liste des repos."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPOS_FILE, "w") as f:
        json.dump({"repos": repos}, f, indent=2)


HELP_TEXT = """GitHerd — Real-time Git branch synchronizer

Keeps multiple Git branches aligned in real-time.
Ideal for parallel AI coding sessions or any workflow
with multiple active branches.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLEAU DES CAS GÉRÉS :

┌─────────────────────────────────────────┬─────────────────────┐
│ Situation                               │ Action              │
├─────────────────────────────────────────┼─────────────────────┤
│ Rien à faire                            │ 🟢 Idle             │
│ main local en avance                    │ Push auto           │
│ Branches en retard sur main             │ Push auto to sync   │
│ 1 branche en avance (pas divergente)    │ Fast-forward + push │
│ 1+ branche divergente, fichiers disjoint│ 🟡 Bouton merge     │
│ 1+ branche divergente, fichiers communs │ 🔴 STOP             │
│ 2+ branches en avance, fichiers disjoint│ 🟡 Bouton merge     │
│ 2+ branches en avance, fichiers communs │ 🔴 STOP             │
└─────────────────────────────────────────┴─────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MULTI-REPO :

- Cliquez sur "+" pour ajouter un dépôt Git
- Chaque onglet gère un dépôt indépendamment
- Les repos sont sauvegardés entre les sessions
- Clic droit sur un onglet pour le fermer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONFIGURATION : githerd.toml (optionnel, dans chaque repo)

[git]
binary = "git"
remote = "origin"
main_branch = "main"
branch_prefix = "claude/"

[sync]
interval_seconds = 10

[ui]
font_zoom = 1.6

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUT : Éviter les merges quand plusieurs instances
travaillent sur le même repo. L'outil garde toutes
les branches alignées en temps réel.

Déterministe. Pas d'heuristique. Pas de magie.

https://github.com/Jacques66/GitHerd
"""

# ============================================================
# GIT HELPERS
# ============================================================

def run_git(cmd, cwd=None):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def commits_ahead(base, tip, cwd=None, git="git"):
    """Retourne le nombre de commits que tip a en avance sur base."""
    code, out, err = run_git([git, "rev-list", "--count", f"{base}..{tip}"], cwd=cwd)
    if code != 0:
        raise RuntimeError(err)
    return int(out)


def commits_behind(base, tip, cwd=None, git="git"):
    """Retourne le nombre de commits que tip a en retard sur base."""
    code, out, err = run_git([git, "rev-list", "--count", f"{tip}..{base}"], cwd=cwd)
    if code != 0:
        return 0
    return int(out)


def get_tracked_branches(remote, prefix, cwd=None, git="git"):
    """Liste toutes les branches remote avec le préfixe configuré."""
    code, out, err = run_git(
        [git, "for-each-ref", "--format=%(refname:short)",
         f"refs/remotes/{remote}/{prefix}"],
        cwd=cwd
    )
    if code != 0:
        raise RuntimeError(err)
    return out.splitlines() if out else []


def get_changed_files(base, tip, cwd=None, git="git"):
    """Retourne l'ensemble des fichiers modifiés entre base et tip."""
    code, out, err = run_git([git, "diff", "--name-only", f"{base}...{tip}"], cwd=cwd)
    if code != 0:
        return set()
    return set(out.splitlines()) if out else set()


def are_files_disjoint(branches, main_ref, remote, cwd=None, git="git"):
    """Vérifie si les fichiers modifiés par chaque branche sont disjoints."""
    all_files = []
    for branch in branches:
        files = get_changed_files(main_ref, f"{remote}/{branch}", cwd=cwd, git=git)
        all_files.append(files)

    for i in range(len(all_files)):
        for j in range(i + 1, len(all_files)):
            if all_files[i] & all_files[j]:
                return False
    return True


def local_main_ahead(remote, main, cwd=None, git="git"):
    """Vérifie si main local est en avance sur origin/main."""
    try:
        return commits_ahead(f"{remote}/{main}", main, cwd=cwd, git=git)
    except:
        return 0


def delete_remote_branch(branch_name, remote, cwd=None, git="git"):
    """Supprime une branche remote."""
    code, out, err = run_git([git, "push", remote, "--delete", branch_name], cwd=cwd)
    return code == 0, err


def is_git_repo(path):
    """Vérifie si un chemin est un dépôt Git."""
    code, _, _ = run_git(["git", "rev-parse", "--git-dir"], cwd=path)
    return code == 0


# ============================================================
# SOUND
# ============================================================

def play_beep():
    """Joue un son de notification."""
    try:
        subprocess.run(
            ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print("\a", end="", flush=True)


# ============================================================
# REPO TAB
# ============================================================

class RepoTab(ttk.Frame):
    """Un onglet gérant un seul dépôt Git."""

    def __init__(self, parent, repo_path, app, font_zoom=1.6):
        super().__init__(parent)

        self.repo_path = Path(repo_path)
        self.app = app
        self.cfg = load_repo_config(repo_path)

        # Config values
        self.git = self.cfg.get("git", {}).get("binary", "git")
        self.remote = self.cfg.get("git", {}).get("remote", "origin")
        self.main = self.cfg.get("git", {}).get("main_branch", "main")
        self.prefix = self.cfg.get("git", {}).get("branch_prefix", "claude/")
        self.interval = self.cfg.get("sync", {}).get("interval_seconds", 60)
        font_zoom = self.cfg.get("ui", {}).get("font_zoom", font_zoom)

        self.lock = threading.Lock()
        self.polling = False
        self.log_visible = True
        self.last_commit_count = {}
        self.pending_branches = []

        f_ui = int(11 * font_zoom)
        f_title = int(12 * font_zoom)
        f_log = int(11 * font_zoom)
        self.f_ui = f_ui

        # TOP BAR (status + menu)
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=6)

        # STATUS (left)
        status = ttk.Frame(top_bar)
        status.pack(side="left", fill="x", expand=True)

        self.state_var = tk.StringVar(value="⏳ Démarrage…")
        self.info_var = tk.StringVar(value="Analyse en cours…")

        tk.Label(status, textvariable=self.state_var,
                 font=("Segoe UI", f_title, "bold")).pack(anchor="w", padx=5)
        tk.Label(status, textvariable=self.info_var,
                 font=("Segoe UI", f_ui), wraplength=700).pack(anchor="w", padx=5)

        # MENU BUTTON (right)
        self.menu_btn = tk.Menubutton(
            top_bar, text="☰", font=("Segoe UI", int(14 * font_zoom)),
            relief="flat", cursor="hand2"
        )
        self.menu_btn.pack(side="right", padx=5)

        self.dropdown = tk.Menu(self.menu_btn, tearoff=0, font=("Segoe UI", f_ui))
        self.menu_btn["menu"] = self.dropdown

        self.rebuild_menu()

        # BUTTONS
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=8)

        self.btn_poll = tk.Button(
            buttons, text="▶ Start polling",
            font=("Segoe UI", f_ui),
            command=self.toggle_polling
        )
        self.btn_poll.pack(side="left", padx=6)

        tk.Button(
            buttons, text="⚡ Sync now",
            font=("Segoe UI", f_ui),
            command=self.manual_sync
        ).pack(side="left", padx=6)

        self.btn_merge = tk.Button(
            buttons, text="🔀 Merge (fichiers disjoints)",
            font=("Segoe UI", f_ui),
            command=self.manual_merge,
            bg="#ffcc00"
        )

        # LOG SECTION (collapsible)
        self.log_header = ttk.Frame(self)
        self.log_header.pack(fill="x", padx=10, pady=(10, 0))

        self.toggle_arrow = tk.StringVar(value="▼")
        self.btn_toggle_log = tk.Button(
            self.log_header,
            textvariable=self.toggle_arrow,
            font=("Segoe UI", f_ui),
            width=2,
            relief="flat",
            command=self.toggle_log
        )
        self.btn_toggle_log.pack(side="left")

        tk.Label(
            self.log_header,
            text="Log",
            font=("Segoe UI", f_ui, "bold")
        ).pack(side="left", padx=4)

        # LOG
        self.log_frame = ttk.Frame(self)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.log = ScrolledText(self.log_frame, state="disabled",
                                font=("Consolas", f_log), height=15)
        self.log.pack(fill="both", expand=True)
        self.log.bind("<Control-a>", self.select_all)

        # DÉMARRAGE
        threading.Thread(target=self.initial_scan, daemon=True).start()

    # --------------------------------------------------------
    # DYNAMIC MENU
    # --------------------------------------------------------

    def rebuild_menu(self):
        """Reconstruit le menu avec les branches actuelles."""
        self.dropdown.delete(0, "end")

        try:
            branches = get_tracked_branches(self.remote, self.prefix,
                                           cwd=self.repo_path, git=self.git)
        except:
            branches = []

        if branches:
            for b in branches:
                short_name = b.replace(f"{self.remote}/", "")
                self.dropdown.add_command(
                    label=f"🗑 Supprimer {short_name}",
                    command=lambda bn=short_name: self.delete_branch(bn)
                )
            self.dropdown.add_separator()

        self.dropdown.add_command(
            label="🔔 Test son",
            command=lambda: threading.Thread(target=play_beep, daemon=True).start()
        )
        self.dropdown.add_command(label="📂 Ouvrir dossier", command=self.open_folder)
        self.dropdown.add_command(label="ℹ️ Aide", command=self.app.show_help)

    def open_folder(self):
        """Ouvre le dossier du repo dans le gestionnaire de fichiers."""
        try:
            subprocess.run(["xdg-open", str(self.repo_path)],
                          stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except:
            pass

    def delete_branch(self, branch_name):
        """Supprime une branche remote après confirmation."""
        if not messagebox.askyesno(
            "Confirmer suppression",
            f"Supprimer la branche remote '{branch_name}' ?\n\nCette action est irréversible.",
            parent=self
        ):
            return

        self.log_msg(f"Suppression de {branch_name}…")
        success, err = delete_remote_branch(branch_name, self.remote,
                                           cwd=self.repo_path, git=self.git)

        if success:
            self.log_msg(f"✅ Branche {branch_name} supprimée")
            self.rebuild_menu()
            self.manual_sync()
        else:
            self.log_msg(f"❌ Erreur: {err}")

    # --------------------------------------------------------
    # TOGGLE LOG
    # --------------------------------------------------------

    def toggle_log(self):
        if self.log_visible:
            self.log_frame.pack_forget()
            self.toggle_arrow.set("▶")
        else:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)
            self.toggle_arrow.set("▼")
        self.log_visible = not self.log_visible

    # --------------------------------------------------------
    # MERGE BUTTON VISIBILITY
    # --------------------------------------------------------

    def show_merge_button(self):
        self.btn_merge.pack(side="left", padx=6)

    def hide_merge_button(self):
        self.btn_merge.pack_forget()

    # --------------------------------------------------------
    # POLLING CONTROL
    # --------------------------------------------------------

    def stop_polling(self):
        """Arrête le polling et met à jour le bouton."""
        self.polling = False
        self.btn_poll.config(text="▶ Start polling")

    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    def log_msg(self, txt):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {txt}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def select_all(self, _):
        self.log.tag_add("sel", "1.0", "end")
        return "break"

    # --------------------------------------------------------
    # PUSH ALL BRANCHES
    # --------------------------------------------------------

    def push_main_and_branches(self):
        """Push main vers origin et sync toutes les branches."""
        self.log_msg(f"git push {self.remote} {self.main}")
        code, out, err = run_git([self.git, "push", self.remote, self.main],
                                cwd=self.repo_path)
        if code != 0:
            self.log_msg(f"ERREUR push main: {err}")
            self.state_var.set("🔴 ERREUR")
            self.stop_polling()
            return False
        self.log_msg(out if out else "  (ok)")

        branches = get_tracked_branches(self.remote, self.prefix,
                                        cwd=self.repo_path, git=self.git)
        for b in branches:
            target = b.replace(f"{self.remote}/", "")
            refspec = f"{self.main}:{target}"
            self.log_msg(f"git push {self.remote} {refspec}")
            code, out, err = run_git([self.git, "push", self.remote, refspec],
                                    cwd=self.repo_path)
            if code != 0:
                self.log_msg(f"ERREUR push {target}: {err}")
                self.state_var.set("🔴 STOP — Push failed")
                self.info_var.set(f"Push vers {target} a échoué")
                self.stop_polling()
                return False
            self.log_msg(out if out else "  (ok)")

        return True

    # --------------------------------------------------------
    # CORE LOGIC
    # --------------------------------------------------------

    def sync(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._do_sync()
        finally:
            self.lock.release()

    def _do_sync(self):
        self.state_var.set("🔄 Sync…")
        self.hide_merge_button()
        self.pending_branches = []

        self.log_msg(f"git fetch {self.remote}")
        code, _, err = run_git([self.git, "fetch", self.remote], cwd=self.repo_path)
        if code != 0:
            self.log_msg(f"ERREUR fetch: {err}")
            self.state_var.set("🔴 ERREUR")
            self.stop_polling()
            return

        self.rebuild_menu()

        local_ahead = local_main_ahead(self.remote, self.main,
                                       cwd=self.repo_path, git=self.git)
        if local_ahead > 0:
            self.log_msg(f"main local en avance de {local_ahead} commits → push")
            if self.push_main_and_branches():
                self.state_var.set("🟢 Sync OK")
                self.info_var.set(f"Push de {local_ahead} commits locaux")
                self.log_msg("✅ Push terminé avec succès")
            return

        branches = get_tracked_branches(self.remote, self.prefix,
                                        cwd=self.repo_path, git=self.git)
        self.log_msg(f"Branches {self.prefix}*: {len(branches)}")

        ahead_branches = []
        diverged_branches = []
        new_commits_detected = False

        for b in branches:
            ahead = commits_ahead(f"{self.remote}/{self.main}", b,
                                 cwd=self.repo_path, git=self.git)
            behind = commits_behind(f"{self.remote}/{self.main}", b,
                                   cwd=self.repo_path, git=self.git)

            if ahead > 0:
                short_name = b.replace(f"{self.remote}/", "")

                if behind > 0:
                    diverged_branches.append((short_name, ahead, behind))
                    self.log_msg(f"  {short_name}: +{ahead}/-{behind} (DIVERGÉE)")
                else:
                    ahead_branches.append((short_name, ahead))
                    self.log_msg(f"  {short_name}: +{ahead} commits")

                prev = self.last_commit_count.get(short_name, 0)
                if ahead > prev:
                    new_commits_detected = True
                self.last_commit_count[short_name] = ahead

        if new_commits_detected:
            self.log_msg("🔔 Nouveau commit détecté!")
            threading.Thread(target=play_beep, daemon=True).start()

        total_problematic = len(ahead_branches) + len(diverged_branches)

        if total_problematic == 0:
            # Vérifier si des branches sont en retard sur origin/main
            behind_branches = []
            for b in branches:
                behind = commits_behind(f"{self.remote}/{self.main}", b,
                                       cwd=self.repo_path, git=self.git)
                if behind > 0:
                    short_name = b.replace(f"{self.remote}/", "")
                    behind_branches.append((short_name, behind))
                    self.log_msg(f"  {short_name}: -{behind} commits (en retard)")

            if behind_branches:
                self.log_msg(f"Synchronisation de {len(behind_branches)} branches en retard…")
                for branch_name, _ in behind_branches:
                    refspec = f"{self.main}:{branch_name}"
                    self.log_msg(f"git push {self.remote} {refspec}")
                    code, out, err = run_git(
                        [self.git, "push", self.remote, refspec],
                        cwd=self.repo_path
                    )
                    if code != 0:
                        self.log_msg(f"ERREUR push {branch_name}: {err}")
                        self.state_var.set("🔴 ERREUR")
                        self.stop_polling()
                        return
                    self.log_msg(out if out else "  (ok)")

                self.state_var.set("🟢 Sync OK")
                self.info_var.set(f"{len(behind_branches)} branches synchronisées")
                self.log_msg("✅ Branches en retard synchronisées")
                return

            self.state_var.set("🟢 Idle")
            self.info_var.set("Toutes les branches sont synchronisées")
            self.log_msg("✓ Rien à faire")
            self.last_commit_count.clear()
            return

        if len(diverged_branches) > 0 or len(ahead_branches) > 1:
            all_names = [b[0] for b in diverged_branches] + [b[0] for b in ahead_branches]
            self.pending_branches = all_names

            self.log_msg("Vérification des fichiers modifiés…")
            disjoint = are_files_disjoint(all_names, f"{self.remote}/{self.main}",
                                         self.remote, cwd=self.repo_path, git=self.git)

            if len(diverged_branches) > 0:
                diverged_names = [f"{b[0]} (+{b[1]}/-{b[2]})" for b in diverged_branches]
                msg = f"Branches divergées: {', '.join(diverged_names)}"
            else:
                msg = f"Plusieurs branches: {', '.join(all_names)}"

            if disjoint:
                self.state_var.set("🟡 STOP — Merge possible")
                self.info_var.set(f"Fichiers disjoints. {msg}")
                self.log_msg("✓ Fichiers disjoints — merge manuel possible")
                self.show_merge_button()
            else:
                self.state_var.set("🔴 STOP — Action humaine requise")
                self.info_var.set(f"Fichiers en conflit potentiel. {msg}")
                self.log_msg("⛔ STOP: fichiers en commun détectés")
            self.stop_polling()
            return

        leader, _ = ahead_branches[0]
        self.log_msg(f"git pull --ff-only {self.remote} {leader}")
        code, out, err = run_git(
            [self.git, "pull", "--ff-only", self.remote, leader],
            cwd=self.repo_path
        )
        if code != 0:
            self.log_msg(f"ERREUR pull: {err}")
            self.state_var.set("🔴 ERREUR")
            self.info_var.set(f"Pull failed: {err[:100]}")
            self.stop_polling()
            return
        self.log_msg(out if out else "  (ok)")

        if not self.push_main_and_branches():
            return

        self.last_commit_count[leader] = 0
        self.state_var.set("🟢 Sync OK")
        branches = get_tracked_branches(self.remote, self.prefix,
                                        cwd=self.repo_path, git=self.git)
        other_count = len(branches) - 1
        self.info_var.set(f"Pull de {leader}, push vers {other_count} autres branches")
        self.log_msg("✅ Sync terminé avec succès")

    # --------------------------------------------------------
    # MANUAL MERGE (fichiers disjoints)
    # --------------------------------------------------------

    def manual_merge(self):
        threading.Thread(target=self._do_merge, daemon=True).start()

    def _do_merge(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._do_merge_impl()
        finally:
            self.lock.release()

    def _do_merge_impl(self):
        if not self.pending_branches:
            self.log_msg("Aucune branche en attente de merge")
            return

        self.state_var.set("🔀 Merge en cours…")
        self.hide_merge_button()

        branches = self.pending_branches[:]
        self.log_msg(f"Merge de {len(branches)} branches: {', '.join(branches)}")

        for branch in branches:
            self.log_msg(f"git merge {self.remote}/{branch}")
            code, out, err = run_git(
                [self.git, "merge", f"{self.remote}/{branch}", "-m", f"Merge {branch}"],
                cwd=self.repo_path
            )
            if code != 0:
                self.log_msg(f"ERREUR merge {branch}: {err}")
                self.state_var.set("🔴 ERREUR — Merge échoué")
                self.info_var.set(f"Merge de {branch} a échoué")
                run_git([self.git, "merge", "--abort"], cwd=self.repo_path)
                self.stop_polling()
                return
            self.log_msg(out if out else "  (ok)")

        if not self.push_main_and_branches():
            return

        self.pending_branches = []
        self.last_commit_count.clear()
        self.state_var.set("🟢 Merge OK")
        self.info_var.set(f"Merge de {len(branches)} branches terminé")
        self.log_msg("✅ Merge terminé avec succès")

        self.rebuild_menu()

    # --------------------------------------------------------
    # INITIAL SCAN (read-only)
    # --------------------------------------------------------

    def initial_scan(self):
        try:
            run_git([self.git, "fetch", self.remote], cwd=self.repo_path)

            self.rebuild_menu()

            local_ahead = local_main_ahead(self.remote, self.main,
                                          cwd=self.repo_path, git=self.git)
            if local_ahead > 0:
                self.state_var.set("🟡 main local en avance")
                self.info_var.set(f"+{local_ahead} commits à pusher — cliquer Sync now")
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
                # Vérifier si des branches sont en retard
                behind_list = []
                for b in branches:
                    behind = commits_behind(f"{self.remote}/{self.main}", b,
                                           cwd=self.repo_path, git=self.git)
                    if behind > 0:
                        short_name = b.replace(f"{self.remote}/", "")
                        behind_list.append((short_name, behind))

                if behind_list:
                    names = [f"{b[0]} (-{b[1]})" for b in behind_list]
                    self.state_var.set("🟡 Branches en retard")
                    self.info_var.set(f"À synchroniser: {', '.join(names)}")
                else:
                    self.state_var.set("🟢 Idle")
                    self.info_var.set("Toutes les branches sont synchronisées")
            elif len(diverged_list) == 0 and len(ahead_list) == 1:
                self.state_var.set("🟡 1 branche en avance")
                self.info_var.set(f"Prêt à sync: {ahead_list[0]}")
            else:
                all_names = [b[0] for b in diverged_list] + ahead_list
                self.pending_branches = all_names

                disjoint = are_files_disjoint(all_names, f"{self.remote}/{self.main}",
                                             self.remote, cwd=self.repo_path, git=self.git)

                if len(diverged_list) > 0:
                    diverged_info = [f"{b[0]} (+{b[1]}/-{b[2]})" for b in diverged_list]
                    msg = f"Divergées: {', '.join(diverged_info)}"
                else:
                    msg = f"Plusieurs branches: {', '.join(all_names)}"

                if disjoint:
                    self.state_var.set("🟡 STOP — Merge possible")
                    self.info_var.set(f"Fichiers disjoints. {msg}")
                    self.after(100, self.show_merge_button)
                else:
                    self.state_var.set("🔴 STOP — Action humaine requise")
                    self.info_var.set(msg)

        except Exception as e:
            self.state_var.set("🔴 ERREUR")
            self.info_var.set(str(e))

    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------

    def polling_loop(self):
        next_tick = time.time()
        while self.polling:
            self.sync()
            try:
                cfg = load_repo_config(self.repo_path)
                interval = cfg.get("sync", {}).get("interval_seconds", self.interval)
            except:
                interval = self.interval

            next_tick += interval
            sleep_time = max(0, next_tick - time.time())
            time.sleep(sleep_time)

    def toggle_polling(self):
        self.polling = not self.polling
        self.btn_poll.config(
            text="⏸ Stop polling" if self.polling else "▶ Start polling"
        )
        if self.polling:
            threading.Thread(target=self.polling_loop, daemon=True).start()

    def manual_sync(self):
        threading.Thread(target=self.sync, daemon=True).start()


# ============================================================
# MAIN APP
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("GitHerd")
        self.geometry("1000x700")

        self.tabs = {}  # repo_path -> RepoTab

        # Style
        style = ttk.Style()
        style.configure("TNotebook.Tab", padding=[10, 5])

        # NOTEBOOK (onglets)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Bind right-click pour fermer un onglet
        self.notebook.bind("<Button-3>", self.on_tab_right_click)

        # BOTTOM BAR
        bottom_bar = ttk.Frame(self)
        bottom_bar.pack(fill="x", padx=10, pady=5)

        tk.Button(
            bottom_bar, text="➕ Ajouter un repo",
            font=("Segoe UI", 11),
            command=self.add_repo_dialog
        ).pack(side="left", padx=5)

        tk.Button(
            bottom_bar, text="ℹ️ Aide",
            font=("Segoe UI", 11),
            command=self.show_help
        ).pack(side="right", padx=5)

        # Charger les repos sauvegardés
        self.load_saved_repos()

        # Si aucun repo, ouvrir le dialogue
        if not self.tabs:
            self.after(100, self.add_repo_dialog)

        # Sauvegarder à la fermeture
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # ALWAYS ON TOP
        self.after(500, self.set_always_on_top)

    def set_always_on_top(self):
        self.attributes("-topmost", True)
        try:
            subprocess.run(
                ["wmctrl", "-r", self.title(), "-b", "add,above"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        except FileNotFoundError:
            pass

    def load_saved_repos(self):
        """Charge les repos sauvegardés."""
        repos = load_saved_repos()
        for repo_path in repos:
            if Path(repo_path).exists() and is_git_repo(repo_path):
                self.add_repo(repo_path)

    def save_current_repos(self):
        """Sauvegarde la liste des repos actuels."""
        repos = list(self.tabs.keys())
        save_repos(repos)

    def add_repo_dialog(self):
        """Ouvre un dialogue pour sélectionner un dépôt Git."""
        path = filedialog.askdirectory(
            title="Sélectionner un dépôt Git",
            mustexist=True
        )
        if path:
            if not is_git_repo(path):
                messagebox.showerror(
                    "Erreur",
                    f"'{path}' n'est pas un dépôt Git valide.",
                    parent=self
                )
                return
            if path in self.tabs:
                messagebox.showinfo(
                    "Info",
                    f"Ce dépôt est déjà ouvert.",
                    parent=self
                )
                # Sélectionner l'onglet existant
                self.notebook.select(self.tabs[path])
                return
            self.add_repo(path)
            self.save_current_repos()

    def add_repo(self, repo_path):
        """Ajoute un onglet pour un dépôt."""
        tab = RepoTab(self.notebook, repo_path, self)
        repo_name = Path(repo_path).name
        self.notebook.add(tab, text=repo_name)
        self.tabs[repo_path] = tab
        self.notebook.select(tab)

    def on_tab_right_click(self, event):
        """Gère le clic droit sur un onglet."""
        try:
            index = self.notebook.index(f"@{event.x},{event.y}")
            tab = self.notebook.nametowidget(self.notebook.tabs()[index])

            menu = tk.Menu(self, tearoff=0)
            menu.add_command(
                label="❌ Fermer cet onglet",
                command=lambda: self.close_tab(tab)
            )
            menu.tk_popup(event.x_root, event.y_root)
        except tk.TclError:
            pass

    def close_tab(self, tab):
        """Ferme un onglet."""
        # Trouver le repo_path correspondant
        repo_path = None
        for path, t in self.tabs.items():
            if t == tab:
                repo_path = path
                break

        if repo_path:
            # Arrêter le polling
            tab.polling = False

            # Supprimer de la liste
            del self.tabs[repo_path]

            # Supprimer l'onglet
            self.notebook.forget(tab)

            # Sauvegarder
            self.save_current_repos()

    def show_help(self):
        help_win = tk.Toplevel(self)
        help_win.title("Aide — GitHerd")
        help_win.geometry("650x600")
        help_win.transient(self)
        help_win.grab_set()

        text = ScrolledText(help_win, font=("Consolas", 11), wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")

        tk.Button(
            help_win, text="Fermer", font=("Segoe UI", 11),
            command=help_win.destroy
        ).pack(pady=10)

    def on_close(self):
        """Appelé à la fermeture de l'application."""
        # Arrêter tous les pollings
        for tab in self.tabs.values():
            tab.polling = False

        # Sauvegarder
        self.save_current_repos()

        # Fermer
        self.destroy()


# ============================================================

if __name__ == "__main__":
    App().mainloop()
