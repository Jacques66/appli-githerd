# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab dialogs mixin.

Handles configuration dialog and other repo-specific dialogs.
"""

import subprocess
from pathlib import Path
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
        dialog.geometry("520x480")
        dialog.transient(self.app)
        dialog.resizable(False, False)
        self.app.ensure_dialog_on_screen(dialog)

        # Main frame with internal padding
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Section title
        ctk.CTkLabel(main_frame, text="Repository settings",
                    font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10))

        # Alias (display name of the tab; leave empty to use the folder name)
        ctk.CTkLabel(main_frame, text="Alias:").grid(
            row=1, column=0, sticky="w", padx=15, pady=8)
        current_alias = self.app.global_settings.get("tab_aliases", {}).get(
            str(self.repo_path), ""
        )
        alias_entry = ctk.CTkEntry(main_frame, width=250)
        alias_entry.insert(0, current_alias)
        alias_entry.grid(row=1, column=1, columnspan=2, sticky="ew",
                         padx=(10, 15), pady=8)

        # Directory (re-point the tab to a different folder)
        ctk.CTkLabel(main_frame, text="Directory:").grid(
            row=2, column=0, sticky="w", padx=15, pady=8)
        dir_var = ctk.StringVar(value=str(self.repo_path))
        dir_entry = ctk.CTkEntry(main_frame, textvariable=dir_var, width=250)
        dir_entry.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=8)

        def browse_dir():
            path = filedialog.askdirectory(
                title="Select repository folder",
                initialdir=str(self.repo_path),
                mustexist=True,
            )
            if path:
                dir_var.set(path)

        ctk.CTkButton(main_frame, text="Browse…", width=80,
                      command=browse_dir).grid(
            row=2, column=2, sticky="w", padx=(0, 15), pady=8)

        # Remote
        ctk.CTkLabel(main_frame, text="Remote:").grid(
            row=3, column=0, sticky="w", padx=15, pady=8)
        remote_entry = ctk.CTkEntry(main_frame, width=250)
        remote_entry.insert(0, self.remote)
        remote_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(10, 15), pady=8)

        # Main branch
        ctk.CTkLabel(main_frame, text="Main branch:").grid(
            row=4, column=0, sticky="w", padx=15, pady=8)
        main_entry = ctk.CTkEntry(main_frame, width=250)
        main_entry.insert(0, self.main)
        main_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 15), pady=8)

        # Branch prefix
        ctk.CTkLabel(main_frame, text="Branch prefix:").grid(
            row=5, column=0, sticky="w", padx=15, pady=8)
        prefix_entry = ctk.CTkEntry(main_frame, width=250)
        prefix_entry.insert(0, self.prefix)
        prefix_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(10, 15), pady=8)

        # Interval
        ctk.CTkLabel(main_frame, text="Interval (sec):").grid(
            row=6, column=0, sticky="w", padx=15, pady=8)
        interval_entry = ctk.CTkEntry(main_frame, width=100)
        interval_entry.insert(0, str(self.interval))
        interval_entry.grid(row=6, column=1, sticky="w", padx=(10, 15), pady=8)

        main_frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)

        def save_config():
            # Re-point directory first so the config is written to the
            # new location and path-keyed state is migrated.
            new_dir = dir_var.get().strip()
            if new_dir and str(Path(new_dir)) != str(self.repo_path):
                if not self.app.change_repo_directory(self.tab_name, new_dir):
                    return  # validation error already surfaced

            # Alias (display name); empty string clears the alias and
            # falls back to the folder name on display.
            self.app.set_tab_alias(self.tab_name, alias_entry.get().strip())

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
        # Inherit the menubar font/colors for size+style consistency.
        colors = getattr(self.app, "menu_colors", None)
        menu = tk.Menu(
            self.app, tearoff=0,
            font=getattr(self.app, "menu_font", None),
            bg=colors["bg"] if colors else None,
            fg=colors["fg"] if colors else None,
            activebackground=colors["active_bg"] if colors else None,
            activeforeground=colors["active_fg"] if colors else None,
        )
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

    def log_msg(self, txt, color=None):
        """Log a message with timestamp.

        color: optional hex string (e.g. "#ff9500"); when given, the
        line is rendered in that color via a Tk text tag.
        """
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        line = f"[{ts}] {txt}\n"
        tag = None
        if color:
            tag = "c" + color.lstrip("#")
            try:
                self.log._textbox.tag_config(tag, foreground=color)
            except Exception:
                tag = None
        try:
            if tag:
                self.log.insert("end", line, tag)
            else:
                self.log.insert("end", line)
        except Exception:
            self.log.insert("end", line)
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
