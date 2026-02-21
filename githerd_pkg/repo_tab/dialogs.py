# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab dialogs mixin.

Handles configuration dialog and other repo-specific dialogs.
"""

import subprocess
from tkinter import messagebox, filedialog
from datetime import datetime
import customtkinter as ctk

from ..config import save_repo_config
from ..git_utils import delete_remote_branch


class RepoTabDialogsMixin:
    """Mixin for repo-specific dialogs."""

    def show_config_dialog(self):
        """Show repository configuration dialog."""
        dialog = ctk.CTkToplevel(self.app)
        dialog.title(f"Options — {self.repo_path.name}")
        dialog.geometry("450x380")
        dialog.transient(self.app)
        dialog.resizable(False, False)
        self.app.ensure_dialog_on_screen(dialog)

        # Main frame with internal padding
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Section title
        ctk.CTkLabel(main_frame, text="Repository settings",
                    font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        # Remote
        ctk.CTkLabel(main_frame, text="Remote:").grid(
            row=1, column=0, sticky="w", padx=15, pady=8)
        remote_entry = ctk.CTkEntry(main_frame, width=250)
        remote_entry.insert(0, self.remote)
        remote_entry.grid(row=1, column=1, sticky="ew", padx=(10, 15), pady=8)

        # Main branch
        ctk.CTkLabel(main_frame, text="Main branch:").grid(
            row=2, column=0, sticky="w", padx=15, pady=8)
        main_entry = ctk.CTkEntry(main_frame, width=250)
        main_entry.insert(0, self.main)
        main_entry.grid(row=2, column=1, sticky="ew", padx=(10, 15), pady=8)

        # Branch prefix
        ctk.CTkLabel(main_frame, text="Branch prefix:").grid(
            row=3, column=0, sticky="w", padx=15, pady=8)
        prefix_entry = ctk.CTkEntry(main_frame, width=250)
        prefix_entry.insert(0, self.prefix)
        prefix_entry.grid(row=3, column=1, sticky="ew", padx=(10, 15), pady=8)

        # Interval
        ctk.CTkLabel(main_frame, text="Interval (sec):").grid(
            row=4, column=0, sticky="w", padx=15, pady=8)
        interval_entry = ctk.CTkEntry(main_frame, width=100)
        interval_entry.insert(0, str(self.interval))
        interval_entry.grid(row=4, column=1, sticky="w", padx=(10, 15), pady=8)

        main_frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)

        def save_config():
            self.remote = remote_entry.get().strip()
            self.main = main_entry.get().strip()
            self.prefix = prefix_entry.get().strip()
            try:
                self.interval = int(interval_entry.get().strip())
            except ValueError:
                self.interval = 60

            self.repo_config = {
                "remote": self.remote,
                "main_branch": self.main,
                "branch_prefix": self.prefix,
                "interval_seconds": self.interval
            }

            try:
                save_repo_config(self.repo_path, self.repo_config)
                self.log_msg("Configuration saved")
                self.check_and_update_health()
            except Exception as e:
                messagebox.showerror("Error", f"Unable to save: {e}", parent=dialog)
                return

            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Save", command=save_config).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

        # Grab focus after widgets are created
        dialog.wait_visibility()
        dialog.grab_set()

    def open_folder(self):
        """Open the repository folder in file manager."""
        try:
            subprocess.run(["xdg-open", str(self.repo_path)],
                          stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except:
            pass

    def delete_branch(self, branch_name):
        """Delete a remote branch."""
        # Skip confirmation in advanced mode
        if not self.app.global_settings.get("advanced_mode", False):
            if not messagebox.askyesno(
                "Confirm deletion",
                f"Delete remote branch '{branch_name}'?\n\nThis action is irreversible.",
                parent=self
            ):
                return

        self.log_msg(f"Deleting {branch_name}…")
        success, err = delete_remote_branch(branch_name, self.remote,
                                           cwd=self.repo_path, git=self.git)

        if success:
            self.log_msg(f"Branch {branch_name} deleted")
            self.app.update_repo_menu()
            self.manual_sync()
        else:
            self.log_msg(f"Error: {err}")

    def _on_log_right_click(self, event):
        """Show context menu on log right-click."""
        import tkinter as tk
        menu = tk.Menu(self.app, tearoff=0)
        menu.add_command(label="Copy", command=self.copy_log)
        menu.tk_popup(event.x_root, event.y_root)

    def copy_log(self):
        """Copy selected text, or all log content if no selection."""
        try:
            # Check for selection in the internal text widget
            sel_ranges = self.log._textbox.tag_ranges("sel")
            if sel_ranges:
                text = self.log._textbox.get(sel_ranges[0], sel_ranges[1])
            else:
                text = self.log.get("1.0", "end").strip()
        except Exception:
            text = self.log.get("1.0", "end").strip()

        if text:
            self.app.clipboard_clear()
            self.app.clipboard_append(text)

    def log_msg(self, txt):
        """Log a message with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {txt}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def export_log(self):
        """Export log to file."""
        filename = filedialog.asksaveasfilename(
            title="Export log",
            defaultextension=".txt",
            initialfile=f"githerd-{self.repo_path.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                content = self.log.get("1.0", "end")
                with open(filename, "w") as f:
                    f.write(f"GitHerd Log - {self.repo_path}\n")
                    f.write(f"Exported: {datetime.now()}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(content)
                self.log_msg(f"Log exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Unable to export: {e}", parent=self)
