# -*- coding: utf-8 -*-
"""
GitHerd — TabBar widget.

A single-canvas tab strip drawn as overlapping, rounded-top trapezoids.
The active tab is drawn last so it sits in front of its neighbours.
Per-repo status is the tab's fill colour (green = polling, red = error/
STOP, neutral = idle); the active tab also gets a top accent bar. The
countdown and update marker live in the tab label.

The widget is presentation-only: it reports user actions through the
callbacks passed at construction and never touches app state directly.
"""

import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk


class TabBar(tk.Canvas):
    """Canvas-drawn trapezoidal tab strip."""

    # Geometry (validated as a mockup): flat tabs, angled sides, rounded top.
    TAB_H = 18          # inactive tab height
    ACTIVE_EXTRA = 4    # active tab is this much taller
    TOP_PAD = 8         # space above the tabs (the strip)
    SLANT = 15          # angled side width
    OVERLAP = 13        # how much each tab tucks under the previous
    RADIUS = 6          # top-corner radius
    LEFT_PAD = 10
    INNER_PAD = 8       # horizontal padding inside a tab (top edge)
    DOT_R = 4           # status dot radius
    GAP = 6             # gap between dot and label

    def __init__(self, master, font_zoom=1.0,
                 on_click=None, on_double=None, on_middle=None,
                 on_right=None, on_reorder=None, **kwargs):
        self._pal = self._palette()
        h = self.TOP_PAD + self.TAB_H + self.ACTIVE_EXTRA
        super().__init__(master, height=h, highlightthickness=0,
                         bg=self._pal["strip"], **kwargs)

        self._on_click = on_click
        self._on_double = on_double
        self._on_middle = on_middle
        self._on_right = on_right
        self._on_reorder = on_reorder

        self.font_zoom = font_zoom
        try:
            self._font = tkfont.nametofont("TkDefaultFont").copy()
            self._font.configure(size=max(9, int(11 * font_zoom)))
        except Exception:
            self._font = tkfont.Font(size=max(9, int(11 * font_zoom)))

        self.tabs = []          # list of dicts (order = display order)
        self.active_name = None

        # drag state
        self._press_name = None
        self._press_x = 0
        self._dragged = False

        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<Button-2>", self._middle)
        self.bind("<Button-3>", self._right)

    # ---- palette -----------------------------------------------------
    def _palette(self):
        dark = (ctk.get_appearance_mode() == "Dark")
        if dark:
            return dict(
                # tray lighter than the (dark) tabs so they read as chips
                strip="#454d59", panel="#1b2027",
                idle="#232a33", idle_active="#2b333d",
                green="#173a26", green_active="#1f5033",
                red="#3a1d20", red_active="#54282d",
                text="#e6edf3", text_dim="#8b949e",
                accent="#58a6ff", dot_green="#3fb950", dot_red="#f85149",
                dot_idle="#6e7681",
                t_green="#dcffe8", t_green_dim="#8fbf9f",
                t_red="#ffdede", t_red_dim="#c99",
            )
        return dict(
            strip="#d0d0d0", panel="#dbdbdb",
            idle="#c4c4c4", idle_active="#ececec",
            green="#bfe3c9", green_active="#d6f5df",
            red="#e9c4c4", red_active="#f6d9d9",
            text="#111111", text_dim="#5a5a5a",
            accent="#3a7ebf", dot_green="#2e9e46", dot_red="#c0362f",
            dot_idle="#8a8a8a",
            t_green="#12481f", t_green_dim="#356b40",
            t_red="#5a1e1e", t_red_dim="#7a3a3a",
        )

    def restyle(self, font_zoom=None):
        """Re-read the theme (e.g. after an appearance change) and redraw."""
        if font_zoom is not None:
            self.font_zoom = font_zoom
            self._font.configure(size=max(9, int(11 * font_zoom)))
        self._pal = self._palette()
        self.configure(bg=self._pal["strip"])
        self._redraw()

    # ---- public API --------------------------------------------------
    def add_tab(self, name, label, status="default"):
        if any(t["name"] == name for t in self.tabs):
            return
        self.tabs.append(dict(name=name, label=label, status=status,
                              countdown=0, has_update=False))
        self._redraw()

    def remove_tab(self, name):
        self.tabs = [t for t in self.tabs if t["name"] != name]
        if self.active_name == name:
            self.active_name = None
        self._redraw()

    def set_active(self, name):
        self.active_name = name
        self._redraw()

    def update_tab(self, name, label=None, status=None,
                   countdown=None, has_update=None):
        for t in self.tabs:
            if t["name"] == name:
                if label is not None:
                    t["label"] = label
                if status is not None:
                    t["status"] = status
                if countdown is not None:
                    t["countdown"] = countdown
                if has_update is not None:
                    t["has_update"] = has_update
                self._redraw()
                return

    def order(self):
        return [t["name"] for t in self.tabs]

    def set_order(self, names):
        by_name = {t["name"]: t for t in self.tabs}
        self.tabs = [by_name[n] for n in names if n in by_name]
        self._redraw()

    # ---- geometry / drawing -----------------------------------------
    def _tab_text(self, t):
        txt = t["label"]
        secs = t.get("countdown", 0)
        if t["status"] == "green" and secs and secs > 0:
            txt = f"{txt}  {secs}"
        if t.get("has_update"):
            txt = "● " + txt
        return txt

    def _tab_width(self, t):
        text_w = self._font.measure(self._tab_text(t))
        # bottom width = top content width + 2*inner pad + 2*slant
        return int(text_w + self.DOT_R * 2 + self.GAP + self.INNER_PAD * 2 + self.SLANT * 2)

    def _fill_for(self, t, active):
        s = t["status"]
        p = self._pal
        if s == "green":
            return p["green_active"] if active else p["green"]
        if s == "red":
            return p["red_active"] if active else p["red"]
        return p["idle_active"] if active else p["idle"]

    def _text_for(self, t, active):
        s = t["status"]
        p = self._pal
        if s == "green":
            return p["t_green"] if active else p["t_green_dim"]
        if s == "red":
            return p["t_red"] if active else p["t_red_dim"]
        return p["text"] if active else p["text_dim"]

    def _rounded_trap(self, x0, W, H, baseline):
        """Point list for a rounded-top trapezoid whose bottom edge is at
        y=baseline, spanning [x0, x0+W], with height H."""
        s, r = self.SLANT, self.RADIUS
        top = baseline - H
        # corner control points (mirror the mockup's quadratic béziers)
        import math
        length = math.hypot(s, H)
        ux, uy = s / length, H / length
        l1 = (x0 + s - r * ux, top + r * uy)
        lc = (x0 + s, top)
        l2 = (x0 + s + r, top)
        r1 = (x0 + W - s - r, top)
        rc = (x0 + W - s, top)
        r2 = (x0 + W - s + r * ux, top + r * uy)

        def bez(p0, p1, p2, n=6):
            out = []
            for i in range(n + 1):
                tt = i / n
                mt = 1 - tt
                out.append((mt * mt * p0[0] + 2 * mt * tt * p1[0] + tt * tt * p2[0],
                            mt * mt * p0[1] + 2 * mt * tt * p1[1] + tt * tt * p2[1]))
            return out

        pts = [(x0, baseline)]
        pts += bez(l1, lc, l2)
        pts += bez(r1, rc, r2)
        pts += [(x0 + W, baseline)]
        flat = []
        for (px, py) in pts:
            flat += [px, py]
        return flat

    def _layout(self):
        """Compute (x0, W) for each tab in display order."""
        x = self.LEFT_PAD
        for t in self.tabs:
            t["_w"] = self._tab_width(t)
            t["_x"] = x
            x += t["_w"] - self.OVERLAP
        return x

    def _redraw(self):
        self.delete("all")
        if not self.tabs:
            return
        self._layout()
        baseline = self.TOP_PAD + self.TAB_H + self.ACTIVE_EXTRA
        p = self._pal

        # inactive first (left→right), then the active one on top
        order = [t for t in self.tabs if t["name"] != self.active_name]
        active = next((t for t in self.tabs if t["name"] == self.active_name), None)
        if active is not None:
            order.append(active)

        for t in order:
            is_active = (t["name"] == self.active_name)
            H = self.TAB_H + (self.ACTIVE_EXTRA if is_active else 0)
            x0, W = t["_x"], t["_w"]
            tag = f"tab:{t['name']}"

            pts = self._rounded_trap(x0, W, H, baseline)
            self.create_polygon(pts, fill=self._fill_for(t, is_active),
                                outline="", tags=(tag,))

            top = baseline - H
            cy = (top + baseline) / 2 + 1

            # accent bar on the active tab
            if is_active:
                acc = p["accent"]
                if t["status"] == "green":
                    acc = p["dot_green"]
                elif t["status"] == "red":
                    acc = p["dot_red"]
                self.create_rectangle(
                    x0 + self.SLANT + 2, top, x0 + W - self.SLANT - 2, top + 3,
                    fill=acc, outline="", tags=(tag,))

            # status dot
            dot = p["dot_idle"]
            if t["status"] == "green":
                dot = p["dot_green"]
            elif t["status"] == "red":
                dot = p["dot_red"]
            dx = x0 + self.SLANT + self.INNER_PAD + self.DOT_R
            self.create_oval(dx - self.DOT_R, cy - self.DOT_R,
                             dx + self.DOT_R, cy + self.DOT_R,
                             fill=dot, outline="", tags=(tag,))

            # label
            self.create_text(
                dx + self.DOT_R + self.GAP, cy, anchor="w",
                text=self._tab_text(t), font=self._font,
                fill=self._text_for(t, is_active), tags=(tag,))

    # ---- hit testing / events ---------------------------------------
    def _name_at(self, x, y):
        items = self.find_overlapping(x, y, x, y)
        for it in reversed(items):  # topmost first
            for tg in self.gettags(it):
                if tg.startswith("tab:"):
                    return tg[4:]
        return None

    def _press(self, event):
        self._press_name = self._name_at(event.x, event.y)
        self._press_x = event.x
        self._dragged = False

    def _motion(self, event):
        if self._press_name is None:
            return
        if not self._dragged and abs(event.x - self._press_x) < 6:
            return
        self._dragged = True
        # find target index by comparing pointer to each tab's bottom center
        names = [t["name"] for t in self.tabs]
        try:
            cur = names.index(self._press_name)
        except ValueError:
            return
        target = cur
        for i, t in enumerate(self.tabs):
            center = t["_x"] + t["_w"] / 2
            if event.x < center:
                target = i
                break
        else:
            target = len(self.tabs) - 1
        if target != cur:
            t = self.tabs.pop(cur)
            self.tabs.insert(target, t)
            self._redraw()

    def _release(self, event):
        if self._dragged:
            if self._on_reorder:
                self._on_reorder(self.order())
        elif self._press_name is not None:
            name = self._name_at(event.x, event.y)
            if name and name == self._press_name and self._on_click:
                self._on_click(name)
        self._press_name = None
        self._dragged = False

    def _double(self, event):
        name = self._name_at(event.x, event.y)
        if name and self._on_double:
            self._on_double(name)

    def _middle(self, event):
        name = self._name_at(event.x, event.y)
        if name and self._on_middle:
            self._on_middle(name)

    def _right(self, event):
        name = self._name_at(event.x, event.y)
        if name and self._on_right:
            self._on_right(event, name)
