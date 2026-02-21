# -*- coding: utf-8 -*-
"""
GitHerd — RepoTab UI mixin.

Handles UI construction and log visibility.
"""

import re
import customtkinter as ctk


class RepoTabUIMixin:
    """Mixin for UI construction and log management."""

    def _build_ui(self):
        """Build the UI for this repo tab."""
        if self.advanced_mode:
            self._build_advanced_ui()
        else:
            self._build_normal_ui()

        # LOG TEXTBOX
        self.log_frame = ctk.CTkFrame(self, fg_color="transparent")
        if self.log_visible:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.log = ctk.CTkTextbox(
            self.log_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            height=250,
            state="disabled"
        )
        self.log.pack(fill="both", expand=True)

        # Right-click context menu on log
        self.log.bind("<Button-3>", self._on_log_right_click)
        # Also bind on internal text widget for clicks directly on text
        self.log._textbox.bind("<Button-3>", self._on_log_right_click)

    def _build_advanced_ui(self):
        """Build compact UI for advanced mode."""
        # Combined frame: Log button left, status right
        combined_frame = ctk.CTkFrame(self, fg_color="transparent")
        combined_frame.pack(fill="x", padx=10, pady=6)

        # Log toggle left
        self.btn_toggle_log = ctk.CTkButton(
            combined_frame,
            text="▼ Log" if self.log_visible else "▶ Log",
            width=70,
            command=self.toggle_log
        )
        self.btn_toggle_log.pack(side="left", padx=(0, 15))

        # Status right
        status_frame = ctk.CTkFrame(combined_frame, fg_color="transparent")
        status_frame.pack(side="left", fill="x", expand=True)

        self.state_label = ctk.CTkLabel(
            status_frame,
            text="Starting…",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.state_label.pack(anchor="w")

        info_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        info_frame.pack(anchor="w", fill="x")

        self.info_label = ctk.CTkLabel(
            info_frame,
            text="Analyzing…",
            font=ctk.CTkFont(size=13),
            wraplength=500
        )
        self.info_label.pack(side="left")

        self.countdown_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        self.countdown_label.pack(side="left", padx=10)

        # Hidden buttons frame in advanced mode
        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        # Don't pack

        self.btn_poll = ctk.CTkButton(self.buttons_frame, text="", width=1)
        self.btn_sync = ctk.CTkButton(self.buttons_frame, text="", width=1)
        self.btn_config = ctk.CTkButton(self.buttons_frame, text="", width=1)
        self.btn_close = ctk.CTkButton(self.buttons_frame, text="", width=1)
        self.btn_merge = ctk.CTkButton(
            self.buttons_frame,
            text="🔀 Merge",
            command=self.manual_merge,
            width=100,
            fg_color="#DAA520",
            hover_color="#B8860B"
        )

    def _build_normal_ui(self):
        """Build full UI for normal mode."""
        # TOP BAR (status)
        top_bar = ctk.CTkFrame(self)
        top_bar.pack(fill="x", padx=10, pady=6)

        self.state_label = ctk.CTkLabel(
            top_bar,
            text="Starting…",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.state_label.pack(anchor="w", padx=5)

        # Info + countdown
        info_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        info_frame.pack(anchor="w", fill="x")

        self.info_label = ctk.CTkLabel(
            info_frame,
            text="Analyzing…",
            font=ctk.CTkFont(size=13),
            wraplength=600
        )
        self.info_label.pack(side="left", padx=5)

        self.countdown_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        self.countdown_label.pack(side="left", padx=10)

        # BUTTONS (with log toggle at start)
        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(fill="x", padx=10, pady=8)

        # Log toggle at the beginning
        self.btn_toggle_log = ctk.CTkButton(
            self.buttons_frame,
            text="▼ Log" if self.log_visible else "▶ Log",
            width=70,
            command=self.toggle_log
        )
        self.btn_toggle_log.pack(side="left", padx=(0, 10))

        self.btn_poll = ctk.CTkButton(
            self.buttons_frame,
            text="▶ Start polling",
            command=self.toggle_polling,
            width=140
        )
        self.btn_poll.pack(side="left", padx=6)

        self.btn_sync = ctk.CTkButton(
            self.buttons_frame,
            text="⚡ Sync now",
            command=self.manual_sync,
            width=120
        )
        self.btn_sync.pack(side="left", padx=6)

        self.btn_merge = ctk.CTkButton(
            self.buttons_frame,
            text="🔀 Merge",
            command=self.manual_merge,
            width=100,
            fg_color="#DAA520",
            hover_color="#B8860B"
        )
        # Hidden by default

        self.btn_config = ctk.CTkButton(
            self.buttons_frame,
            text="⚙ Options",
            command=self.show_config_dialog,
            width=100
        )
        self.btn_config.pack(side="right", padx=6)

        self.btn_close = ctk.CTkButton(
            self.buttons_frame,
            text="✕ Close",
            command=lambda: self.app.close_tab(self.tab_name),
            width=100,
            fg_color="#8B0000",
            hover_color="#CD5C5C"
        )
        self.btn_close.pack(side="right", padx=6)

    def toggle_log(self):
        """Toggle log visibility."""
        # Force geometry update and get position BEFORE any changes
        self.app.update_idletasks()
        geo = self.app.geometry()
        match = re.match(r'(\d+)x(\d+)\+(\d+)\+(\d+)', geo)
        if match:
            x, y = match.group(3), match.group(4)
        else:
            x, y = 100, 100

        # Collapsed height: 189px normal, 151px advanced
        collapsed_height = 151 if self.advanced_mode else 189

        if self.log_visible:
            self.log_frame.pack_forget()
            self.btn_toggle_log.configure(text="▶ Log")
            self.app.geometry(f"710x{collapsed_height}+{x}+{y}")
        else:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=6)
            self.btn_toggle_log.configure(text="▼ Log")
            self.app.geometry(f"710x750+{x}+{y}")
        self.log_visible = not self.log_visible

    def show_merge_button(self):
        """Show the merge button."""
        self.btn_merge.pack(side="left", padx=6)

    def hide_merge_button(self):
        """Hide the merge button."""
        self.btn_merge.pack_forget()

    def disable_tab(self, error_msg):
        """Disable tab due to error."""
        self.state_label.configure(text="ERROR — Git not working")
        self.info_label.configure(text=error_msg)
        self.btn_poll.configure(state="disabled")
        self.btn_sync.configure(state="disabled")
        self.polling = False
        self.btn_poll.configure(text="▶ Start polling")
        self.after(0, lambda: self.app.update_tab_color(self))

    def enable_tab(self):
        """Enable tab."""
        self.btn_poll.configure(state="normal")
        self.btn_sync.configure(state="normal")
