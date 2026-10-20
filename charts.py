"""
charts.py
---------
Exp 7 : GUI - small chart widgets drawn on a Tkinter Canvas.
(No matplotlib needed, so the project runs with plain Python.)

    LineChart  - several series + optional dashed reference lines
    BarChart   - grouped / single bars with value labels
    GanttChart - pump schedule timeline
Each chart redraws itself when the window is resized (<Configure> event).
"""
import tkinter as tk

PALETTE = ["#2a78d6", "#e8743b", "#19a979", "#945ecf", "#d64a8c", "#8c6d1f", "#13a4b4", "#6c8893"]
GRID = "#e6e9e4"
AXIS = "#6b7280"
TEXT = "#1f2933"


def nice_max(value):
    """Round an axis maximum up to 1, 2, 2.5 or 5 x 10^n."""
    if value <= 0:
        return 1
    exp = 10 ** (len(str(int(value))) - 1)
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp


def short(n):
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1000:
        return f"{n / 1000:.0f}k" if abs(n) >= 10_000 else f"{n / 1000:.1f}k"
    return f"{n:g}" if isinstance(n, float) and n != int(n) else f"{int(n)}"


class _Chart(tk.Canvas):
    PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 30, 34

    def __init__(self, master, title="", height=220, font=("Helvetica", 9), **kw):
        super().__init__(master, height=height, bg="white", highlightthickness=1,
                         highlightbackground="#dfe3dc", **kw)
        self.title = title
        self.font = font
        self.bold = (font[0], font[1], "bold")
        self.bind("<Configure>", lambda e: self.redraw())

    def _frame(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if self.title:
            self.create_text(10, 8, text=self.title, anchor="nw", font=self.bold, fill=TEXT)
        return w, h, self.PAD_L, w - self.PAD_R, self.PAD_T, h - self.PAD_B

    def _y_axis(self, x0, x1, y0, y1, vmin, vmax, ticks=4, unit=""):
        for i in range(ticks + 1):
            v = vmin + (vmax - vmin) * i / ticks
            y = y1 - (y1 - y0) * i / ticks
            self.create_line(x0, y, x1, y, fill=GRID)
            self.create_text(x0 - 6, y, text=short(round(v, 1)) + unit, anchor="e",
                             font=self.font, fill=AXIS)

    def redraw(self):
        raise NotImplementedError


class LineChart(_Chart):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.series = []          # (label, values, color)
        self.refs = []            # (label, value, color)
        self.labels = []
        self.unit = ""
        self.fixed_range = None

    def set_data(self, series, x_labels=None, refs=None, unit="", y_range=None):
        self.series = [(lbl, vals, col or PALETTE[i % len(PALETTE)])
                       for i, (lbl, vals, col) in enumerate(series)]
        self.labels = x_labels or []
        self.refs = refs or []
        self.unit = unit
        self.fixed_range = y_range
        self.redraw()

    def redraw(self):
        w, h, x0, x1, y0, y1 = self._frame()
        if w < 50 or not any(v for _, v, _ in self.series):
            self.create_text(w / 2, h / 2, text="Waiting for data...", fill=AXIS, font=self.font)
            return
        values = [v for _, vals, _ in self.series for v in vals] + [r[1] for r in self.refs]
        if self.fixed_range:
            vmin, vmax = self.fixed_range
        else:
            vmin, vmax = min(values), max(values)
            pad = (vmax - vmin) * 0.15 or 1
            vmin, vmax = max(0, vmin - pad), vmax + pad
        self._y_axis(x0, x1, y0, y1, vmin, vmax, unit=self.unit)
        n = max(len(v) for _, v, _ in self.series)

        def px(i):
            return x0 + (x1 - x0) * (i / max(n - 1, 1))

        def py(v):
            return y1 - (y1 - y0) * (v - vmin) / ((vmax - vmin) or 1)

        for label, value, color in self.refs:
            self.create_line(x0, py(value), x1, py(value), fill=color, dash=(5, 3), width=1.5)
            self.create_text(x1 - 4, py(value) - 7, text=label, anchor="e", font=self.font, fill=color)

        legend_x = x0 + 4 + (self.bold[1] * 0 if not self.title else len(self.title) * 7 + 20)
        for label, vals, color in self.series:
            if len(vals) >= 2:
                pts = []
                offset = n - len(vals)
                for i, v in enumerate(vals):
                    pts += [px(i + offset), py(v)]
                self.create_line(*pts, fill=color, width=2, smooth=False)
            if vals:
                lx, ly = px(n - 1), py(vals[-1])
                self.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill=color, outline="white")
            if len(self.series) > 1 and legend_x < w - 80:
                self.create_line(legend_x, 15, legend_x + 14, 15, fill=color, width=3)
                tid = self.create_text(legend_x + 18, 15, text=label, anchor="w", font=self.font, fill=TEXT)
                legend_x = self.bbox(tid)[2] + 14

        if self.labels:
            step = max(1, len(self.labels) // 6)
            for i in range(0, len(self.labels), step):
                self.create_text(px(i), y1 + 12, text=self.labels[i], font=self.font, fill=AXIS)


class BarChart(_Chart):
    def __init__(self, master, horizontal=False, **kw):
        super().__init__(master, **kw)
        self.horizontal = horizontal
        self.categories, self.groups, self.unit = [], [], ""
        self.bar_colors = None

    def set_data(self, categories, groups, unit="", bar_colors=None):
        """groups = [(label, values, color), ...]; bar_colors overrides per-category colour."""
        self.categories = categories
        self.groups = [(lbl, vals, col or PALETTE[i % len(PALETTE)])
                       for i, (lbl, vals, col) in enumerate(groups)]
        self.unit = unit
        self.bar_colors = bar_colors
        self.redraw()

    def redraw(self):
        w, h, x0, x1, y0, y1 = self._frame()
        if w < 50 or not self.categories:
            return
        if self.horizontal:
            return self._draw_horizontal(w, h)
        vmax = nice_max(max((v for _, vals, _ in self.groups for v in vals), default=1))
        self._y_axis(x0, x1, y0, y1, 0, vmax, unit=self.unit)
        slot = (x1 - x0) / len(self.categories)
        bw = min(34, slot * 0.7 / len(self.groups))
        for ci, cat in enumerate(self.categories):
            cx = x0 + slot * (ci + 0.5)
            start = cx - bw * len(self.groups) / 2
            for gi, (_, vals, color) in enumerate(self.groups):
                v = vals[ci]
                if self.bar_colors and len(self.groups) == 1:
                    color = self.bar_colors[ci]
                top = y1 - (y1 - y0) * v / vmax
                bx = start + gi * bw
                self.create_rectangle(bx + 1, top, bx + bw - 1, y1, fill=color, outline="")
                if bw >= 16:
                    self.create_text(bx + bw / 2, top - 7, text=short(round(v, 1)), font=self.font, fill=TEXT)
            limit = max(4, int(slot / 7.5))
            self.create_text(cx, y1 + 12, text=cat if len(cat) <= limit else cat[:limit - 1] + "\u2026",
                             font=self.font, fill=AXIS)
        if len(self.groups) > 1:
            lx = w - 12
            for label, _, color in reversed(self.groups):
                tid = self.create_text(lx, 15, text=label, anchor="e", font=self.font, fill=TEXT)
                bx = self.bbox(tid)[0]
                self.create_rectangle(bx - 14, 10, bx - 4, 20, fill=color, outline="")
                lx = bx - 24

    def _draw_horizontal(self, w, h):
        label_w = 100
        x0, x1, y0, y1 = label_w, w - 60, self.PAD_T, h - 10
        values = self.groups[0][1]
        vmax = nice_max(max(values, default=1))
        row = (y1 - y0) / len(self.categories)
        bh = min(22, row * 0.65)
        for i, cat in enumerate(self.categories):
            cy = y0 + row * (i + 0.5)
            color = self.bar_colors[i] if self.bar_colors else self.groups[0][2]
            x_end = x0 + (x1 - x0) * values[i] / vmax
            self.create_text(x0 - 8, cy, text=cat, anchor="e", font=self.font, fill=TEXT)
            self.create_rectangle(x0, cy - bh / 2, max(x0 + 2, x_end), cy + bh / 2, fill=color, outline="")
            self.create_text(max(x0 + 2, x_end) + 6, cy, text=f"{short(round(values[i], 1))}{self.unit}",
                             anchor="w", font=self.font, fill=TEXT)


class GanttChart(_Chart):
    PAD_L = 110

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.rows = []      # (label, start_dt, end_dt, color, text)

    def set_data(self, rows):
        self.rows = rows
        self.redraw()

    def redraw(self):
        w, h, x0, x1, y0, y1 = self._frame()
        if not self.rows:
            self.create_text(w / 2, h / 2, text="No plot needs irrigation in this window",
                             fill=AXIS, font=self.font)
            return
        t0 = min(r[1] for r in self.rows).replace(minute=0)
        t1 = max(r[2] for r in self.rows)
        hours = max(1, int((t1 - t0).total_seconds() // 3600) + 1)
        step = 1 if hours <= 12 else 2 if hours <= 24 else 4

        def px(t):
            return x0 + (x1 - x0) * (t - t0).total_seconds() / (hours * 3600)

        for i in range(0, hours + 1, step):
            x = x0 + (x1 - x0) * i / hours
            self.create_line(x, y0, x, y1, fill=GRID)
            hh = (t0.hour + i) % 24
            self.create_text(x, y1 + 12, text=f"{hh:02d}:00", font=self.font, fill=AXIS)
        row_h = (y1 - y0) / len(self.rows)
        for i, (label, start, end, color, text) in enumerate(self.rows):
            cy = y0 + row_h * (i + 0.5)
            self.create_text(x0 - 8, cy, text=label, anchor="e", font=self.font, fill=TEXT)
            bh = min(24, row_h * 0.7)
            self.create_rectangle(px(start), cy - bh / 2, px(end), cy + bh / 2, fill=color, outline="")
            if px(end) - px(start) > 60:
                self.create_text((px(start) + px(end)) / 2, cy, text=text, font=self.font, fill="white")


# -----------------------------------------------------------------------------
# Exp 7 logo: the same canvas shapes as my Exp 7 (oval sun, line stem and
# leaves, polygon water drop, text, rectangle panel)
# -----------------------------------------------------------------------------
def draw_exp7_logo(canvas, full=True, scale=1.0, tag="logo"):
    """Draw my Exp 7 logo. full=False draws only the icon part (for the header)."""
    c = canvas
    # Sun - OVAL
    c.create_oval(50, 30, 100, 80, fill="yellow", outline="orange", width=2, tags=tag)
    # Sugarcane stem - LINE
    c.create_line(75, 80, 75, 170, fill="green", width=6, tags=tag)
    # Sugarcane leaves - LINE
    for x0, y0, x1, y1 in ((75, 105, 35, 85), (75, 120, 115, 95), (75, 140, 35, 125), (75, 150, 115, 135)):
        c.create_line(x0, y0, x1, y1, fill="green", width=4, tags=tag)
    # Water drop - POLYGON
    c.create_polygon(150, 80, 130, 120, 150, 150, 170, 120, fill="blue", outline="darkblue", tags=tag)
    if full:
        c.create_text(300, 75, text="AI IRRIGATION", font=("Arial", 28, "bold"), fill="green", tags=tag)
        c.create_text(300, 115, text="ADVISORY SYSTEM", font=("Arial", 20, "bold"), fill="darkblue", tags=tag)
        c.create_text(300, 150, text="Smart Water Management for Sugarcane", font=("Arial", 13), fill="black", tags=tag)
        # RECTANGLE - monitoring section
        c.create_rectangle(510, 30, 780, 180, outline="green", width=3, tags=tag)
        c.create_text(645, 55, text="SENSOR MONITORING", font=("Arial", 14, "bold"), fill="green", tags=tag)
        for y, label in ((90, "Soil Moisture"), (115, "Temperature"), (140, "Humidity")):
            c.create_text(645, y, text=label, font=("Arial", 12), tags=tag)
        c.create_text(645, 165, text="AI Recommendation", font=("Arial", 12, "bold"), fill="darkblue", tags=tag)
    if scale != 1.0:
        c.scale(tag, 0, 0, scale, scale)
