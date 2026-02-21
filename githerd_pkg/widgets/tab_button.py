# -*- coding: utf-8 -*-
"""
GitHerd — Custom tab button widget.

A tab button with indicator overlay and rounded corners.
"""

import tkinter as tk
import customtkinter as ctk

from ..config import load_global_settings


class TabButton(tk.Frame):
    """Tab button with indicator overlay.

    The indicator is drawn to the left of centered text,
    without shifting the text itself.
    Rounded corners drawn on canvas.
    """

    def __init__(self, master, text, command=None, **kwargs):
        # Extract specific parameters
        self.fg_color = kwargs.pop("fg_color", "#333333")
        self.hover_color = kwargs.pop("hover_color", "#444444")
        base_corner_radius = kwargs.pop("corner_radius", 8)
        base_height = kwargs.pop("height", 32)

        self.text = text
        self.command = command
        self.indicator = ""
        self.indicator_margin = 8

        self._hover = False
        self._border_width = 0
        self._border_color = None

        # Get font_zoom from global settings
        self.font_zoom = load_global_settings().get("font_zoom", 1.0)
        self.base_font_size = 13

        # Apply zoom to height and corner radius
        self.btn_height = int(base_height * self.font_zoom)
        self.corner_radius = int(base_corner_radius * self.font_zoom)

        # Calculate width: text + indicator space + padding
        font = self._get_font()
        text_width = font.measure(text) if text else 50
        indicator_space = font.measure("⭯") + self.indicator_margin
        padding = int(30 * self.font_zoom)
        self.btn_width = text_width + indicator_space + padding

        # Parent background color (for transparent corners)
        try:
            self.parent_bg = master.cget("bg")
        except:
            self.parent_bg = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0"

        # Initialize tk.Frame with parent color
        super().__init__(master, bg=self.parent_bg, height=self.btn_height, width=self.btn_width)

        # Prevent automatic resizing
        self.pack_propagate(False)

        # Canvas for drawing rounded button, text and indicator
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bg=self.parent_bg,
            height=self.btn_height,
            width=self.btn_width
        )
        self.canvas.pack(fill="both", expand=True)

        # Bindings
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Map>", self._on_map)
        self.canvas.bind("<Configure>", self._on_configure)

    def _on_map(self, event=None):
        """Called when widget becomes visible."""
        self.after(50, self._draw)

    def _on_configure(self, event=None):
        """Called when widget changes size."""
        self._draw()

    def _get_font(self):
        """Return font with zoom applied."""
        size = int(self.base_font_size * self.font_zoom)
        return ctk.CTkFont(size=size)

    def _draw_rounded_rect(self, x1, y1, x2, y2, radius, fill, outline=""):
        """Draw a rounded rectangle with arcs."""
        r = min(radius, (x2-x1)//2, (y2-y1)//2)
        if r < 2:
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline)
            return

        d = 2 * r  # diameter

        # Horizontal center rectangle
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", width=0)
        # Vertical center rectangle
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", width=0)

        # Rounded corners with create_arc
        # Top-left
        self.canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, fill=fill, outline="", style="pieslice")
        # Top-right
        self.canvas.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90, fill=fill, outline="", style="pieslice")
        # Bottom-right
        self.canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90, fill=fill, outline="", style="pieslice")
        # Bottom-left
        self.canvas.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90, fill=fill, outline="", style="pieslice")

    def _draw_rounded_border(self, x1, y1, x2, y2, radius, color, width):
        """Draw a rounded border (outline only)."""
        r = min(radius, (x2-x1)//2, (y2-y1)//2)
        if r < 2:
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=width)
            return

        # Straight lines
        # Top
        self.canvas.create_line(x1 + r, y1, x2 - r, y1, fill=color, width=width)
        # Bottom
        self.canvas.create_line(x1 + r, y2, x2 - r, y2, fill=color, width=width)
        # Left
        self.canvas.create_line(x1, y1 + r, x1, y2 - r, fill=color, width=width)
        # Right
        self.canvas.create_line(x2, y1 + r, x2, y2 - r, fill=color, width=width)

        d = 2 * r
        # Corner arcs (style=ARC for outline only)
        self.canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, outline=color, width=width, style="arc")
        self.canvas.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90, outline=color, width=width, style="arc")
        self.canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90, outline=color, width=width, style="arc")
        self.canvas.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90, outline=color, width=width, style="arc")

    def _on_click(self, event=None):
        """Handle click."""
        if self.command:
            self.command()

    def _on_enter(self, event=None):
        """Hover - change color."""
        self._hover = True
        self._draw()

    def _on_leave(self, event=None):
        """End hover - restore color."""
        self._hover = False
        self._draw()

    def _draw(self):
        """Draw rounded button, centered text and indicator."""
        self.canvas.delete("all")

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width <= 1 or height <= 1:
            return

        # Button background color
        bg_color = self.hover_color if self._hover else self.fg_color

        # Draw rounded rectangle (button background)
        self._draw_rounded_rect(1, 1, width - 1, height - 1, self.corner_radius, fill=bg_color)

        # Text color
        text_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"

        font = self._get_font()

        # Calculate main text width
        text_width = font.measure(self.text)

        # Centered Y position
        y_center = height // 2

        # Centered X position for text
        x_text = width // 2

        # Draw main text (centered)
        self.canvas.create_text(
            x_text, y_center,
            text=self.text,
            fill=text_color,
            font=font,
            anchor="center"
        )

        # Draw indicator if present
        if self.indicator:
            char_width = font.measure(self.indicator)
            x_indicator = (width // 2) - (text_width // 2) - self.indicator_margin - (char_width // 2)

            self.canvas.create_text(
                x_indicator, y_center,
                text=self.indicator,
                fill=text_color,
                font=font,
                anchor="center"
            )

        # Draw rounded border if active
        if self._border_width > 0 and self._border_color:
            self._draw_rounded_border(1, 1, width - 1, height - 1, self.corner_radius, self._border_color, self._border_width)

    def configure(self, **kwargs):
        """Configure the button."""
        text_changed = False
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            text_changed = True
        if "fg_color" in kwargs:
            self.fg_color = kwargs.pop("fg_color")
        if "hover_color" in kwargs:
            self.hover_color = kwargs.pop("hover_color")
        if "border_width" in kwargs:
            self._border_width = kwargs.pop("border_width")
        if "border_color" in kwargs:
            self._border_color = kwargs.pop("border_color")

        # Recalculate width if text changed
        if text_changed:
            font = self._get_font()
            text_width = font.measure(self.text) if self.text else 50
            indicator_space = font.measure("⭯") + self.indicator_margin
            padding = int(30 * self.font_zoom)
            self.btn_width = text_width + indicator_space + padding
            # Resize frame and canvas
            super().configure(width=self.btn_width)
            self.canvas.configure(width=self.btn_width)

        if kwargs:
            super().configure(**kwargs)
        self._draw()

    def set_indicator(self, indicator=""):
        """Set indicator to display (e.g., '⭯', '●', '')."""
        self.indicator = indicator
        self._draw()

    def bind(self, sequence, func, add=None):
        """Bind on canvas too."""
        super().bind(sequence, func, add)
        self.canvas.bind(sequence, func, add)

    def destroy(self):
        """Destroy widget properly."""
        self.canvas.destroy()
        super().destroy()
