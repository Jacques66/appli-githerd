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
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = Path.cwd() / "githerd.toml"

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            f"Create a githerd.toml in the current directory."
        )
    return tomllib.load(open(CONFIG_FILE, "rb"))

cfg = load_config()

GIT = cfg.get("git", {}).get("binary", "git")
REMOTE = cfg.get("git", {}).get("remote", "origin")
MAIN = cfg.get("git", {}).get("main_branch", "main")
BRANCH_PREFIX = cfg.get("git", {}).get("branch_prefix", "claude/")
INTERVAL = cfg.get("sync", {}).get("interval_seconds", 60)
FONT_ZOOM = cfg.get("ui", {}).get("font_zoom", 1.6)

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
│ 1 branche en avance (pas divergente)    │ Fast-forward + push │
│ 1+ branche divergente, fichiers disjoint│ 🟡 Bouton merge     │
│ 1+ branche divergente, fichiers communs │ 🔴 STOP             │
│ 2+ branches en avance, fichiers disjoint│ 🟡 Bouton merge     │
│ 2+ branches en avance, fichiers communs │ 🔴 STOP             │
└─────────────────────────────────────────┴─────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FONCTIONNEMENT DÉTAILLÉ :

1. Polling régulier (configurable) avec git fetch

2. Si main local est en avance sur origin/main :
   → git push origin main + sync toutes les branches

3. Détection des branches origin/<prefix>* en avance sur main

4. Si UNE SEULE branche est en avance (et pas divergente) :
   → git pull --ff-only + git push + sync autres branches

5. Si PLUSIEURS branches ont avancé, ou si une branche a DIVERGÉ :
   → STOP — action humaine requise
   → SI fichiers disjoints : bouton "Merge" disponible

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONFIGURATION : githerd.toml

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

def run_git(cmd):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def commits_ahead(base, tip):
    """Retourne le nombre de commits que tip a en avance sur base."""
    code, out, err = run_git(
        [GIT, "rev-list", "--count", f"{base}..{tip}"]
    )
    if code != 0:
        raise RuntimeError(err)
    return int(out)

def commits_behind(base, tip):
    """Retourne le nombre de commits que tip a en retard sur base."""
    code, out, err = run_git(
        [GIT, "rev-list", "--count", f"{tip}..{base}"]
    )
    if code != 0:
        return 0
    return int(out)

def get_tracked_branches():
    """Liste toutes les branches remote avec le préfixe configuré."""
    code, out, err = run_git(
        [GIT, "for-each-ref", "--format=%(refname:short)",
         f"refs/remotes/{REMOTE}/{BRANCH_PREFIX}"]
    )
    if code != 0:
        raise RuntimeError(err)
    return out.splitlines() if out else []

def get_changed_files(base, tip):
    """Retourne l'ensemble des fichiers modifiés entre base et tip."""
    code, out, err = run_git(
        [GIT, "diff", "--name-only", f"{base}...{tip}"]
    )
    if code != 0:
        return set()
    return set(out.splitlines()) if out else set()

def are_files_disjoint(branches, main_ref):
    """Vérifie si les fichiers modifiés par chaque branche sont disjoints."""
    all_files = []
    for branch in branches:
        files = get_changed_files(main_ref, f"{REMOTE}/{branch}")
        all_files.append(files)
    
    for i in range(len(all_files)):
        for j in range(i + 1, len(all_files)):
            if all_files[i] & all_files[j]:
                return False
    return True

def local_main_ahead():
    """Vérifie si main local est en avance sur origin/main."""
    try:
        return commits_ahead(f"{REMOTE}/{MAIN}", MAIN)
    except:
        return 0

def delete_remote_branch(branch_name):
    """Supprime une branche remote."""
    code, out, err = run_git([GIT, "push", REMOTE, "--delete", branch_name])
    return code == 0, err

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
# UI
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"GitHerd — {Path.cwd().name}")
        self.geometry("980x640")

        self.lock = threading.Lock()
        self.polling = False
        self.log_visible = True
        self.last_commit_count = {}
        self.pending_branches = []

        f_ui = int(11 * FONT_ZOOM)
        f_title = int(12 * FONT_ZOOM)
        f_log = int(11 * FONT_ZOOM)
        self.f_ui = f_ui

        # TOP BAR (status + menu)
        top_bar = tk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=6)

        # STATUS (left)
        status = tk.Frame(top_bar, bd=2, relief="groove")
        status.pack(side="left", fill="x", expand=True)

        self.state_var = tk.StringVar(value="⏳ Démarrage…")
        self.info_var = tk.StringVar(value="Analyse en cours…")

        tk.Label(status, textvariable=self.state_var,
                 font=("Segoe UI", f_title, "bold")).pack(anchor="w", padx=5)
        tk.Label(status, textvariable=self.info_var,
                 font=("Segoe UI", f_ui), wraplength=800).pack(anchor="w", padx=5)

        # MENU BUTTON (right)
        self.menu_btn = tk.Menubutton(
            top_bar, text="☰", font=("Segoe UI", int(14 * FONT_ZOOM)),
            relief="flat", cursor="hand2"
        )
        self.menu_btn.pack(side="right", padx=5)

        self.dropdown = tk.Menu(self.menu_btn, tearoff=0, font=("Segoe UI", f_ui))
        self.menu_btn["menu"] = self.dropdown
        
        self.rebuild_menu()

        # BUTTONS
        buttons = tk.Frame(self)
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
        self.log_header = tk.Frame(self)
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
        self.log_frame = tk.Frame(self)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.log = ScrolledText(self.log_frame, state="disabled",
                                font=("Consolas", f_log))
        self.log.pack(fill="both", expand=True)
        self.log.bind("<Control-a>", self.select_all)

        # ALWAYS ON TOP
        self.after(500, self.set_always_on_top)

        # DÉMARRAGE
        threading.Thread(target=self.initial_scan, daemon=True).start()

    # --------------------------------------------------------
    # DYNAMIC MENU
    # --------------------------------------------------------

    def rebuild_menu(self):
        """Reconstruit le menu avec les branches actuelles."""
        self.dropdown.delete(0, "end")
        
        branches = get_tracked_branches()
        if branches:
            for b in branches:
                short_name = b.replace(f"{REMOTE}/", "")
                self.dropdown.add_command(
                    label=f"🗑 Supprimer {short_name}",
                    command=lambda bn=short_name: self.delete_branch(bn)
                )
            self.dropdown.add_separator()
        
        self.dropdown.add_command(label="🔔 Test son", command=lambda: threading.Thread(target=play_beep, daemon=True).start())
        self.dropdown.add_command(label="ℹ️ Aide", command=self.show_help)
        self.dropdown.add_separator()
        self.dropdown.add_command(label="❌ Quitter", command=self.destroy)

    def delete_branch(self, branch_name):
        """Supprime une branche remote après confirmation."""
        from tkinter import messagebox
        
        if not messagebox.askyesno(
            "Confirmer suppression",
            f"Supprimer la branche remote '{branch_name}' ?\n\nCette action est irréversible."
        ):
            return
        
        self.log_msg(f"Suppression de {branch_name}…")
        success, err = delete_remote_branch(branch_name)
        
        if success:
            self.log_msg(f"✅ Branche {branch_name} supprimée")
            self.rebuild_menu()
            self.manual_sync()
        else:
            self.log_msg(f"❌ Erreur: {err}")

    # --------------------------------------------------------
    # HELP DIALOG
    # --------------------------------------------------------

    def show_help(self):
        help_win = tk.Toplevel(self)
        help_win.title("Aide — GitHerd")
        help_win.geometry("620x580")
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

    # --------------------------------------------------------
    # ALWAYS ON TOP
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TOGGLE LOG
    # --------------------------------------------------------

    def toggle_log(self):
        if self.log_visible:
            self.log_frame.pack_forget()
            self.toggle_arrow.set("▶")
            self.geometry("980x150")
        else:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)
            self.toggle_arrow.set("▼")
            self.geometry("980x640")
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
        self.log_msg(f"git push {REMOTE} {MAIN}")
        code, out, err = run_git([GIT, "push", REMOTE, MAIN])
        if code != 0:
            self.log_msg(f"ERREUR push main: {err}")
            self.state_var.set("🔴 ERREUR")
            self.stop_polling()
            return False
        self.log_msg(out if out else "  (ok)")

        branches = get_tracked_branches()
        for b in branches:
            target = b.replace(f"{REMOTE}/", "")
            refspec = f"{MAIN}:{target}"
            self.log_msg(f"git push {REMOTE} {refspec}")
            code, out, err = run_git([GIT, "push", REMOTE, refspec])
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

        self.log_msg(f"git fetch {REMOTE}")
        code, _, err = run_git([GIT, "fetch", REMOTE])
        if code != 0:
            self.log_msg(f"ERREUR fetch: {err}")
            self.state_var.set("🔴 ERREUR")
            self.stop_polling()
            return

        self.rebuild_menu()

        local_ahead = local_main_ahead()
        if local_ahead > 0:
            self.log_msg(f"main local en avance de {local_ahead} commits → push")
            if self.push_main_and_branches():
                self.state_var.set("🟢 Sync OK")
                self.info_var.set(f"Push de {local_ahead} commits locaux")
                self.log_msg("✅ Push terminé avec succès")
            return

        branches = get_tracked_branches()
        self.log_msg(f"Branches {BRANCH_PREFIX}*: {len(branches)}")

        ahead_branches = []
        diverged_branches = []
        new_commits_detected = False

        for b in branches:
            ahead = commits_ahead(f"{REMOTE}/{MAIN}", b)
            behind = commits_behind(f"{REMOTE}/{MAIN}", b)
            
            if ahead > 0:
                short_name = b.replace(f"{REMOTE}/", "")
                
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
            self.state_var.set("🟢 Idle")
            self.info_var.set("Aucune branche en avance")
            self.log_msg("✓ Rien à faire")
            self.last_commit_count.clear()
            return

        if len(diverged_branches) > 0 or len(ahead_branches) > 1:
            all_names = [b[0] for b in diverged_branches] + [b[0] for b in ahead_branches]
            self.pending_branches = all_names
            
            self.log_msg("Vérification des fichiers modifiés…")
            disjoint = are_files_disjoint(all_names, f"{REMOTE}/{MAIN}")
            
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
        self.log_msg(f"git pull --ff-only {REMOTE} {leader}")
        code, out, err = run_git([GIT, "pull", "--ff-only", REMOTE, leader])
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
        branches = get_tracked_branches()
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
            self.log_msg(f"git merge {REMOTE}/{branch}")
            code, out, err = run_git([GIT, "merge", f"{REMOTE}/{branch}", "-m", f"Merge {branch}"])
            if code != 0:
                self.log_msg(f"ERREUR merge {branch}: {err}")
                self.state_var.set("🔴 ERREUR — Merge échoué")
                self.info_var.set(f"Merge de {branch} a échoué")
                run_git([GIT, "merge", "--abort"])
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
            run_git([GIT, "fetch", REMOTE])
            
            self.rebuild_menu()
            
            local_ahead = local_main_ahead()
            if local_ahead > 0:
                self.state_var.set("🟡 main local en avance")
                self.info_var.set(f"+{local_ahead} commits à pusher — cliquer Sync now")
                return

            branches = get_tracked_branches()

            ahead_list = []
            diverged_list = []
            
            for b in branches:
                ahead = commits_ahead(f"{REMOTE}/{MAIN}", b)
                behind = commits_behind(f"{REMOTE}/{MAIN}", b)
                
                if ahead > 0:
                    short_name = b.replace(f"{REMOTE}/", "")
                    self.last_commit_count[short_name] = ahead
                    
                    if behind > 0:
                        diverged_list.append((short_name, ahead, behind))
                    else:
                        ahead_list.append(short_name)

            total = len(ahead_list) + len(diverged_list)
            
            if total == 0:
                self.state_var.set("🟢 Idle")
                self.info_var.set("Aucune branche en avance")
            elif len(diverged_list) == 0 and len(ahead_list) == 1:
                self.state_var.set("🟡 1 branche en avance")
                self.info_var.set(f"Prêt à sync: {ahead_list[0]}")
            else:
                all_names = [b[0] for b in diverged_list] + ahead_list
                self.pending_branches = all_names
                
                disjoint = are_files_disjoint(all_names, f"{REMOTE}/{MAIN}")
                
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
                cfg = load_config()
                interval = cfg.get("sync", {}).get("interval_seconds", INTERVAL)
            except:
                interval = INTERVAL
            
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

if __name__ == "__main__":
    App().mainloop()
