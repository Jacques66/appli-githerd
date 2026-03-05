# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab sync mixin.

Handles synchronization logic, push, and merge operations.
"""

import threading

from ..config import load_global_settings, save_global_settings, load_repo_config
from ..git_utils import (
    run_git, get_tracked_branches, commits_ahead, commits_behind,
    local_main_ahead, are_files_disjoint
)
from ..notifications import play_sound, send_notification


class RepoTabSyncMixin:
    """Mixin for sync and merge operations."""

    def sync(self):
        """Main sync entry point with lock."""
        if not self.lock.acquire(blocking=False):
            return
        try:
            # Show sync indicator on tab
            self.syncing = True
            self.after(0, lambda: self.app.update_tab_color(self))
            self._do_sync()
        finally:
            # Hide sync indicator
            self.syncing = False
            self.after(0, lambda: self.app.update_tab_color(self))
            # Update Repository menu if this tab is active
            self.after(0, lambda: self.app.update_repo_menu() if self.app.get_current_tab() == self else None)
            self.lock.release()

    def _do_sync(self):
        """Perform the actual sync operation."""
        self.state_label.configure(text="Sync…")
        self.hide_merge_button()
        self.pending_branches = []

        self.log_msg(f"git fetch {self.remote}")
        code, _, err = run_git([self.git, "fetch", self.remote], cwd=self.repo_path)
        if code != 0:
            self.log_msg(f"ERROR fetch: {err}")
            self.state_label.configure(text="ERROR")
            self.stop_polling()
            return

        local_ahead = local_main_ahead(self.remote, self.main,
                                       cwd=self.repo_path, git=self.git)

        if local_ahead == -1:
            # Remote main doesn't exist - bootstrap push
            self.log_msg(f"Remote {self.remote}/{self.main} not found → bootstrap push")
            code, out, err = run_git(
                [self.git, "push", "-u", self.remote, self.main],
                cwd=self.repo_path
            )
            if code == 0:
                self.log_msg(out if out else "  (ok)")
                self.log_msg("Main branch pushed, remote initialized")
                self.state_label.configure(text="Sync OK")
                self.info_label.configure(text="Remote initialized with main branch")
            else:
                self.log_msg(f"ERROR bootstrap push: {err}")
                self.state_label.configure(text="ERROR")
                self.stop_polling()
            return

        if local_ahead > 0:
            self.log_msg(f"Local main ahead by {local_ahead} commits → push")
            if self.push_main_and_branches():
                self.state_label.configure(text="Sync OK")
                self.info_label.configure(text=f"Pushed {local_ahead} local commits")
                self.log_msg("Push completed successfully")
            return

        all_branches = get_tracked_branches(self.remote, self.prefix,
                                        cwd=self.repo_path, git=self.git)

        # Filter out disabled branches
        settings = load_global_settings()
        branch_states = settings.get("branch_update_enabled", {}).get(str(self.repo_path), {})
        default_enabled = settings.get("sync_new_branches_by_default", False)
        branches = []
        disabled_count = 0
        for b in all_branches:
            short_name = b.replace(f"{self.remote}/", "")
            if branch_states.get(short_name, default_enabled):
                branches.append(b)
            else:
                disabled_count += 1

        # Clean up non-existent branches from persistence
        existing_short_names = {b.replace(f"{self.remote}/", "") for b in all_branches}
        repo_path_str = str(self.repo_path)
        if repo_path_str in settings.get("branch_update_enabled", {}):
            saved_branches = list(settings["branch_update_enabled"][repo_path_str].keys())
            cleaned = False
            for saved_branch in saved_branches:
                if saved_branch not in existing_short_names:
                    del settings["branch_update_enabled"][repo_path_str][saved_branch]
                    cleaned = True
            if cleaned:
                save_global_settings(settings)

        if disabled_count > 0:
            self.log_msg(f"Branches {self.prefix}*: {len(all_branches)} ({disabled_count} disabled)")
        else:
            self.log_msg(f"Branches {self.prefix}*: {len(all_branches)}")

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
                    self.log_msg(f"  {short_name}: +{ahead}/-{behind} (DIVERGED)")
                else:
                    ahead_branches.append((short_name, ahead))
                    self.log_msg(f"  {short_name}: +{ahead} commits")

                prev = self.last_commit_count.get(short_name, 0)
                if ahead > prev:
                    new_commits_detected = True
                self.last_commit_count[short_name] = ahead

        if new_commits_detected:
            self.log_msg("New commit detected!")
            threading.Thread(target=lambda: play_sound("commit"), daemon=True).start()
            if self.app.global_settings.get("desktop_notifications", True):
                send_notification(
                    f"GitHerd — {self.repo_path.name}",
                    "New commit detected!",
                    "normal"
                )
            self.after(0, self._mark_if_not_active)

        total_problematic = len(ahead_branches) + len(diverged_branches)

        if total_problematic == 0:
            behind_branches = []
            for b in branches:
                behind = commits_behind(f"{self.remote}/{self.main}", b,
                                       cwd=self.repo_path, git=self.git)
                if behind > 0:
                    short_name = b.replace(f"{self.remote}/", "")
                    behind_branches.append((short_name, behind))
                    self.log_msg(f"  {short_name}: -{behind} commits (behind)")

            if behind_branches:
                self.log_msg(f"Synchronizing {len(behind_branches)} branches behind…")
                for branch_name, _ in behind_branches:
                    refspec = f"{self.main}:{branch_name}"
                    self.log_msg(f"git push {self.remote} {refspec}")
                    code, out, err = run_git(
                        [self.git, "push", self.remote, refspec],
                        cwd=self.repo_path
                    )
                    if code != 0:
                        self.log_msg(f"ERROR push {branch_name}: {err}")
                        self.state_label.configure(text="ERROR")
                        self.stop_polling()
                        return
                    self.log_msg(out if out else "  (ok)")

                self.state_label.configure(text="Sync OK")
                self.info_label.configure(text=f"{len(behind_branches)} branches synchronized")
                self.log_msg("Behind branches synchronized")
                return

            self.state_label.configure(text="Idle")
            self.info_label.configure(text="All branches are synchronized")
            self.log_msg("Nothing to do")
            self.last_commit_count.clear()
            return

        if len(diverged_branches) > 0 or len(ahead_branches) > 1:
            all_names = [b[0] for b in diverged_branches] + [b[0] for b in ahead_branches]
            self.pending_branches = all_names

            self.log_msg("Checking modified files…")
            disjoint = are_files_disjoint(all_names, f"{self.remote}/{self.main}",
                                         self.remote, cwd=self.repo_path, git=self.git)

            if len(diverged_branches) > 0:
                diverged_names = [f"{b[0]} (+{b[1]}/-{b[2]})" for b in diverged_branches]
                msg = f"Diverged branches: {', '.join(diverged_names)}"
            else:
                msg = f"Multiple branches: {', '.join(all_names)}"

            if disjoint:
                self.state_label.configure(text="STOP — Merge possible")
                self.info_label.configure(text=f"Disjoint files. {msg}")
                self.log_msg("Disjoint files — manual merge possible")
                self.show_merge_button()
            else:
                self.state_label.configure(text="STOP — Human action required")
                self.info_label.configure(text=f"Potential file conflict. {msg}")
                self.log_msg("STOP: common files detected")
            self.stop_polling()
            return

        leader, _ = ahead_branches[0]
        self.log_msg(f"git pull --ff-only {self.remote} {leader}")
        code, out, err = run_git(
            [self.git, "pull", "--ff-only", self.remote, leader],
            cwd=self.repo_path
        )
        if code != 0:
            self.log_msg(f"ERROR pull: {err}")
            self.state_label.configure(text="ERROR")
            self.info_label.configure(text=f"Pull failed: {err[:100]}")
            self.stop_polling()
            return
        self.log_msg(out if out else "  (ok)")

        if not self.push_main_and_branches():
            return

        self.last_commit_count[leader] = 0
        self.state_label.configure(text="Sync OK")
        branches = get_tracked_branches(self.remote, self.prefix,
                                        cwd=self.repo_path, git=self.git)
        other_count = len(branches) - 1
        self.info_label.configure(text=f"Pull from {leader}, push to {other_count} other branches")
        self.log_msg("Sync completed successfully")

    def push_main_and_branches(self):
        """Push main and all enabled branches."""
        self.log_msg(f"git push {self.remote} {self.main}")
        code, out, err = run_git([self.git, "push", self.remote, self.main],
                                cwd=self.repo_path)
        if code != 0:
            self.log_msg(f"ERROR push main: {err}")
            self.state_label.configure(text="ERROR")
            self.stop_polling()
            return False
        self.log_msg(out if out else "  (ok)")

        all_branches = get_tracked_branches(self.remote, self.prefix,
                                            cwd=self.repo_path, git=self.git)

        # Filter out disabled branches
        settings = load_global_settings()
        branch_states = settings.get("branch_update_enabled", {}).get(str(self.repo_path), {})
        default_enabled = settings.get("sync_new_branches_by_default", False)

        for b in all_branches:
            target = b.replace(f"{self.remote}/", "")
            # Skip disabled branches
            if not branch_states.get(target, default_enabled):
                self.log_msg(f"  {target}: skipped (sync disabled)")
                continue
            refspec = f"{self.main}:{target}"
            self.log_msg(f"git push {self.remote} {refspec}")
            code, out, err = run_git([self.git, "push", self.remote, refspec],
                                    cwd=self.repo_path)
            if code != 0:
                self.log_msg(f"ERROR push {target}: {err}")
                self.state_label.configure(text="STOP — Push failed")
                self.info_label.configure(text=f"Push to {target} failed")
                self.stop_polling()
                return False
            self.log_msg(out if out else "  (ok)")

        return True

    def manual_merge(self):
        """Start manual merge in separate thread."""
        threading.Thread(target=self._do_merge, daemon=True).start()

    def _do_merge(self):
        """Merge entry point with lock."""
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._do_merge_impl()
        finally:
            self.lock.release()

    def _do_merge_impl(self):
        """Perform the actual merge operation."""
        if not self.pending_branches:
            self.log_msg("No branches pending merge")
            return

        self.state_label.configure(text="Merging…")
        self.hide_merge_button()

        branches = self.pending_branches[:]
        self.log_msg(f"Merging {len(branches)} branches: {', '.join(branches)}")

        for branch in branches:
            self.log_msg(f"git merge {self.remote}/{branch}")
            code, out, err = run_git(
                [self.git, "merge", f"{self.remote}/{branch}", "-m", f"Merge {branch}"],
                cwd=self.repo_path
            )
            if code != 0:
                self.log_msg(f"ERROR merge {branch}: {err}")
                self.state_label.configure(text="ERROR — Merge failed")
                self.info_label.configure(text=f"Merge of {branch} failed")
                run_git([self.git, "merge", "--abort"], cwd=self.repo_path)
                self.stop_polling()
                return
            self.log_msg(out if out else "  (ok)")

        if not self.push_main_and_branches():
            return

        self.pending_branches = []
        self.last_commit_count.clear()
        self.state_label.configure(text="Merge OK")
        self.info_label.configure(text=f"Merged {len(branches)} branches")
        self.log_msg("Merge completed successfully")

        self.after(0, lambda: self.app.update_tab_color(self))

    def manual_sync(self):
        """Trigger a manual sync."""
        if not self.git_healthy:
            return
        threading.Thread(target=self.sync, daemon=True).start()
