"""
pages.py
--------
Exp 7 : GUI-Based Dashboard - one page (tab) for each of the 12 scenarios.

Every page inherits from the abstract class BasePage and must implement
refresh(). The main window calls page.refresh() without knowing which page
it is (Exp 4 polymorphism again).
"""
import contextlib
import io
import threading
import tkinter as tk
from abc import ABC, abstractmethod
from datetime import date, datetime
from tkinter import messagebox, ttk

import analytics as an
from advisors import LEVEL_RANK, FertigationAdvisor, StressDetector
from charts import PALETTE, BarChart, GanttChart, LineChart
from database import EXP8_QUERIES
from exceptions import (DatabaseError, DuplicatePlotError, InvalidPlotDataError, IrrigationError,
                        parse_float_in_range, parse_positive_float)
from lab.exp1_classes import IrrigationSystem
from lab.exp2_records import IrrigationRecord, build_records, find_day, get_advice
from lab.exp3_inheritance import CropHealthAnalyzer, SmartFarm
from lab.exp4_abstract import AIAdvisory, SensorAdvisory
from lab.exp5_threads import monitor_all
from lab_logic import (classify_moisture, clean_number, format_advisory_report, format_collections, parse_readings,
                       sugarcane_advisory)
from models import GROWTH_STAGES, PLOT_TYPES, SOIL_PROPERTIES, VARIETY_POTENTIAL, create_plot
from services import CHANNELS, LANGUAGES, advice_to_message, compose_message

GREEN = "#1b5e20"
LEVEL_BG = {"NORMAL": "#e8f5e9", "MILD": "#fff8e1", "SEVERE": "#fff3e0", "CRITICAL": "#ffebee", "INFO": "#eef2f7"}
PRIORITY_TAG = {1: "urgent", 2: "soon", 3: "plan", 4: "ok", 5: "rain"}


# =============================================================================
# Small reusable widgets / helpers
# =============================================================================
def capture_output(fn, *args):
    """Run a function that uses print() and return what it printed (for my lab programs)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def make_tree(parent, columns, height=8):
    """columns = [(key, heading, width, anchor), ...] -> (frame, treeview)"""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height)
    for key, heading, width, anchor in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor=anchor, stretch=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    for tag, bg in [("urgent", "#ffebee"), ("soon", "#fff3e0"), ("plan", "#fff8e1"),
                    ("ok", "#f1f8f1"), ("rain", "#e3f2fd")] + list(LEVEL_BG.items()):
        tree.tag_configure(tag, background=bg)
    return frame, tree


def fill_tree(tree, rows, tags=None):
    """rows = [(iid, values_tuple), ...]; keeps the user's selection."""
    selected = tree.selection()
    tree.delete(*tree.get_children())
    for i, (iid, values) in enumerate(rows):
        tree.insert("", "end", iid=str(iid), values=values,
                    tags=(tags[i],) if tags and tags[i] else ())
    keep = [s for s in selected if tree.exists(s)]
    if keep:
        tree.selection_set(keep)


class KpiCard(ttk.Frame):
    def __init__(self, master, caption, color=GREEN):
        super().__init__(master, style="Card.TFrame", padding=(14, 8))
        self.value = ttk.Label(self, text="-", style="KpiValue.TLabel", foreground=color)
        self.value.pack(anchor="w")
        ttk.Label(self, text=caption, style="KpiCaption.TLabel").pack(anchor="w")

    def set(self, text):
        self.value.configure(text=str(text))


class KpiRow(ttk.Frame):
    def __init__(self, master, captions):
        super().__init__(master)
        self.cards = {}
        for i, cap in enumerate(captions):
            card = KpiCard(self, cap)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            self.columnconfigure(i, weight=1)
            self.cards[cap] = card

    def update_values(self, mapping):
        for key, value in mapping.items():
            if key in self.cards:
                self.cards[key].set(value)


class MoistureTile(tk.Canvas):
    """Shows one plot's moisture as a bar between wilting point and field capacity."""

    def __init__(self, master, font, **kw):
        super().__init__(master, width=230, height=112, bg="white", highlightthickness=1,
                         highlightbackground="#dfe3dc", **kw)
        self.font = font
        self.data = None
        self.bind("<Configure>", lambda e: self.redraw())

    def show(self, plot, level, trend, avg, pumping=False):
        self.data = (plot, level, trend, avg, pumping)
        self.redraw()

    def redraw(self):
        self.delete("all")
        if not self.data:
            return
        plot, level, trend, avg, pumping = self.data
        w = self.winfo_width()
        color = StressDetector.COLORS[level]
        self.configure(bg=LEVEL_BG[level])
        self.create_text(10, 10, anchor="nw", text=plot.name, font=(self.font, 11, "bold"))
        self.create_text(w - 10, 10, anchor="ne", text=level, font=(self.font, 9, "bold"), fill=color)
        arrow = {"falling": "▼", "rising": "▲", "steady": "▶"}[trend]
        self.create_text(10, 32, anchor="nw", text=f"{plot.current_moisture:.1f}%",
                         font=(self.font, 20, "bold"), fill=color)
        self.create_text(w - 10, 40, anchor="ne", text=f"{arrow} {trend}\navg {avg}%",
                         font=(self.font, 9), fill="#4b5563", justify="right")
        x0, x1, y = 10, w - 10, 82
        lo, hi = plot.wilting_point - 3, plot.field_capacity + 2

        def px(v):
            return x0 + (x1 - x0) * (min(max(v, lo), hi) - lo) / (hi - lo)

        self.create_rectangle(x0, y, x1, y + 10, fill="#e5e7eb", outline="")
        self.create_rectangle(x0, y, px(plot.current_moisture), y + 10, fill=color, outline="")
        for value, label in ((plot.wilting_point, "PWP"), (plot.threshold, "Safe"), (plot.field_capacity, "FC")):
            self.create_line(px(value), y - 3, px(value), y + 13, fill="#111827")
            self.create_text(px(value), y + 20, text=label, font=(self.font, 7), fill="#4b5563")
        if pumping:
            self.create_text(10, 63, anchor="nw", text="\u25cf PUMP ON", font=(self.font, 9), fill="#1565c0")


# =============================================================================
# Abstract page
# =============================================================================
class BasePage(ttk.Frame, ABC):
    title = "Page"
    subtitle = ""
    concepts = ""

    def __init__(self, master, app):
        super().__init__(master, padding=(18, 12))
        self.app = app
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=self.title, style="H1.TLabel").pack(anchor="w")
        ttk.Label(head, text=self.subtitle, style="Muted.TLabel", wraplength=1000,
                  justify="left").pack(anchor="w")
        if self.concepts:
            ttk.Label(head, text="Python concepts: " + self.concepts, style="Concept.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Separator(self).pack(fill="x", pady=8)
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        self.build(self.body)

    @abstractmethod
    def build(self, body):
        """Create the widgets of the page."""

    @abstractmethod
    def refresh(self):
        """Re-read data and redraw the page."""

    # shortcuts
    @property
    def farm(self):
        return self.app.farm

    @property
    def weather(self):
        return self.app.weather

    def selected_plot(self, tree):
        sel = tree.selection()
        return self.farm.get_plot(int(sel[0])) if sel else None


# =============================================================================
# 1. Sugarcane Farm & Plot Monitoring Dashboard
# =============================================================================
class FarmPage(BasePage):
    title = "1. Sugarcane Farm & Plot Monitoring"
    subtitle = "All plots of the farm with live status. Select a plot to see details, or use the form to add / edit / delete plots (saved in SQLite)."
    concepts = "classes & objects, constructors, lists of objects, inheritance (Drip/Furrow/FloodPlot), exceptions, SQLite CRUD | Exp 1: IrrigationSystem (class / instance / class / static methods)"

    COLS = [("id", "ID", 40, "center"), ("name", "Plot", 120, "w"), ("method", "Method", 70, "center"),
            ("area", "Acres", 60, "e"), ("soil", "Soil", 150, "w"), ("variety", "Variety", 80, "w"),
            ("age", "Age (d)", 60, "e"), ("stage", "Stage", 100, "w"),
            ("moist", "Moisture %", 80, "e"), ("status", "Status", 70, "center")]

    def build(self, body):
        self.kpis = KpiRow(body, ["Plots", "Total area", "Avg moisture", "Need water now", "Water today"])
        self.kpis.pack(fill="x", pady=(0, 10))
        main = ttk.Frame(body)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        frame, self.tree = make_tree(left, self.COLS, height=6)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        ttk.Label(left, text="Plot details", style="H2.TLabel").pack(anchor="w", pady=(10, 2))
        self.details = tk.Text(left, height=14, font=(self.app.mono, 10), relief="flat",
                               bg="#fbfcfa", padx=10, pady=6)
        self.details.pack(fill="both", expand=True)

        form = ttk.LabelFrame(main, text=" Add / edit plot ", padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        self.vars = {}
        fields = [("name", "Plot name", None), ("area", "Area (acres)", None),
                  ("soil", "Soil type", list(SOIL_PROPERTIES)), ("variety", "Variety", list(VARIETY_POTENTIAL)),
                  ("method", "Irrigation method", list(PLOT_TYPES)),
                  ("planted", "Planting date (YYYY-MM-DD)", None), ("pump", "Pump flow (litres/hour)", None)]
        for key, label, options in fields:
            ttk.Label(form, text=label).pack(anchor="w", pady=(6, 0))
            var = tk.StringVar()
            if options:
                ttk.Combobox(form, textvariable=var, values=options, state="readonly").pack(fill="x")
                var.set(options[0])
            else:
                ttk.Entry(form, textvariable=var).pack(fill="x")
            self.vars[key] = var
        self.vars["planted"].set(str(date.today()))
        self.vars["pump"].set("30000")
        btns = ttk.Frame(form)
        btns.pack(fill="x", pady=(14, 0))
        for i, (text, cmd, style) in enumerate([("Add", self.add, "Accent.TButton"), ("Update", self.update_plot, "TButton"),
                                                ("Delete", self.delete, "TButton"), ("Clear", self.clear, "TButton")]):
            ttk.Button(btns, text=text, command=cmd, style=style).grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        btns.columnconfigure((0, 1), weight=1)

    def refresh(self):
        plots = self.farm.plots
        recs = self.app.recommendations()
        self.kpis.update_values(an.farm_kpis(plots, recs))
        rows, tags = [], []
        for p in plots:
            status = "DRY" if p.current_moisture <= p.threshold else "OK"
            rows.append((p.plot_id, (p.plot_id, p.name, p.method, f"{p.area_acres:.1f}", p.soil_type, p.variety,
                                     p.age_days, p.stage, f"{p.current_moisture:.1f}", status)))
            tags.append("urgent" if status == "DRY" else "")
        fill_tree(self.tree, rows, tags)
        self.show_details()

    def on_select(self, _=None):
        plot = self.selected_plot(self.tree)
        if plot:
            for key, value in [("name", plot.name), ("area", plot.area_acres), ("soil", plot.soil_type),
                               ("variety", plot.variety), ("method", plot.method),
                               ("planted", plot.planting_date), ("pump", int(plot.pump_lph))]:
                self.vars[key].set(str(value))
        self.show_details()

    def show_details(self):
        plot = self.selected_plot(self.tree)
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        if plot:
            text = plot.describe()
            text += f"\n{'Last reading'.ljust(15)}: {plot.latest_reading or 'none yet'}"
            last = self.app.db.last_irrigation(plot.plot_id)
            text += f"\n{'Last irrigated'.ljust(15)}: {last or 'no record'}"
            # my Exp 1 class used on this plot's live values
            temp = plot.latest_reading.temperature if plot.latest_reading else self.weather.today().tmax
            field = IrrigationSystem(round(plot.current_moisture, 1), temp)
            text += "\n\n--- Exp 1: IrrigationSystem object for this plot ---\n"
            text += capture_output(IrrigationSystem.crop_info)                 # class method
            text += capture_output(IrrigationSystem.sensor_status)             # static method
            text += capture_output(field.irrigation_advice)                    # instance method
        else:
            text = f"{self.farm}\n\nSelect a plot in the table to see its details."
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _form_values(self, plot_id=None):
        """Validate the form by actually building a Plot object (raises on bad input)."""
        area = parse_positive_float(self.vars["area"].get(), "Area")
        pump = parse_positive_float(self.vars["pump"].get(), "Pump flow")
        plot = create_plot(self.vars["method"].get(), plot_id=plot_id, name=self.vars["name"].get(),
                           area_acres=area, soil_type=self.vars["soil"].get(), variety=self.vars["variety"].get(),
                           planting_date=self.vars["planted"].get(), pump_lph=pump, farm_id=self.farm.farm_id)
        for other in self.farm.plots:
            if other.name.lower() == plot.name.lower() and other.plot_id != plot_id:
                raise DuplicatePlotError(f"A plot named '{plot.name}' already exists.")
        return plot

    def add(self):
        try:
            p = self._form_values()
            self.app.db.add_plot(self.farm.farm_id, p.name, p.area_acres, p.soil_type, p.variety,
                                 p.method, p.planting_date, p.pump_lph)
        except IrrigationError as e:
            messagebox.showerror("Cannot add plot", str(e))
            return
        self.app.reload_farm()
        self.app.set_status(f"Plot '{p.name}' added.")

    def update_plot(self):
        current = self.selected_plot(self.tree)
        if not current:
            messagebox.showinfo("Update", "Select a plot in the table first.")
            return
        try:
            p = self._form_values(current.plot_id)
            self.app.db.update_plot(current.plot_id, p.name, p.area_acres, p.soil_type, p.variety,
                                    p.method, p.planting_date, p.pump_lph)
        except IrrigationError as e:
            messagebox.showerror("Cannot update plot", str(e))
            return
        self.app.reload_farm()
        self.app.set_status(f"Plot '{p.name}' updated.")

    def delete(self):
        plot = self.selected_plot(self.tree)
        if not plot:
            messagebox.showinfo("Delete", "Select a plot in the table first.")
            return
        if messagebox.askyesno("Delete plot", f"Delete '{plot.name}' and all its readings?"):
            try:
                self.app.db.delete_plot(plot.plot_id)
            except DatabaseError as e:
                messagebox.showerror("Database error", str(e))
                return
            self.tree.selection_remove(self.tree.selection())
            self.app.reload_farm()
            self.app.set_status(f"Plot '{plot.name}' deleted.")

    def clear(self):
        self.tree.selection_remove(self.tree.selection())
        self.vars["name"].set("")
        self.vars["area"].set("")
        self.vars["planted"].set(str(date.today()))


# =============================================================================
# 2. Multi-Plot Soil Moisture Monitoring
# =============================================================================
class MoisturePage(BasePage):
    title = "2. Multi-Plot Soil Moisture Monitoring"
    subtitle = "Live readings from the (simulated) sensors of every plot, the 50 field-sensor records stored in SQLite (my Exp 8), and my Exp 6 reading analysis."
    concepts = "threads + queue, deque | Exp 8: sqlite3 queries | Exp 6: list/tuple/dict/set + map/filter/reduce/lambda | Exp 2: list of IrrigationRecord objects"

    def build(self, body):
        nb = ttk.Notebook(body)
        nb.pack(fill="both", expand=True)
        live = ttk.Frame(nb, padding=(0, 8))
        sql_tab = ttk.Frame(nb, padding=(0, 8))
        exp6_tab = ttk.Frame(nb, padding=(0, 8))
        nb.add(live, text="  Live plot sensors  ")
        nb.add(sql_tab, text="  Sensor records - SQLite (Exp 8)  ")
        nb.add(exp6_tab, text="  Reading analysis (Exp 6)  ")
        exp2_tab = ttk.Frame(nb, padding=(0, 8))
        nb.add(exp2_tab, text="  30-day log (Exp 2)  ")
        self._build_live(live)
        self._build_sql(sql_tab)
        self._build_exp6(exp6_tab)
        self._build_exp2(exp2_tab)

    # ---------------------------------------------------------------- Exp 8 tab
    def _build_sql(self, tab):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        ttk.Label(left, text="Choose a query", style="H2.TLabel").pack(anchor="w")
        self.query_list = tk.Listbox(left, height=15, width=40, activestyle="none", exportselection=False,
                                     font=(self.app.font, 9), relief="flat", highlightthickness=1,
                                     highlightbackground="#dfe3dc", selectbackground="#2a78d6")
        self.query_list.pack(fill="x", pady=(4, 0))
        for title, _ in EXP8_QUERIES:
            self.query_list.insert("end", title)
        self.query_list.bind("<<ListboxSelect>>", self._pick_query)
        ttk.Label(left, text="Queries 1-7 are the ones from my Exp 8.", style="Muted.TLabel").pack(anchor="w")

        form = ttk.LabelFrame(left, text=" Add a sensor record ", padding=8)
        form.pack(fill="x", pady=(12, 0))
        self.rec_vars = {}
        for i, (key, label) in enumerate([("m", "Moisture (%)"), ("t", "Temperature (°C)"), ("h", "Humidity (%)")]):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=10).grid(row=i, column=1, pady=2, padx=(6, 0))
            self.rec_vars[key] = var
        ttk.Button(form, text="Insert into both tables", style="Accent.TButton",
                   command=self._add_record).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.rec_result = ttk.Label(form, text="", style="Muted.TLabel", wraplength=260)
        self.rec_result.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="SQL (you can edit it - SELECT only)", style="H2.TLabel").pack(anchor="w")
        self.sql_text = tk.Text(right, height=5, font=(self.app.mono, 10), relief="flat", bg="#fbfcfa",
                                padx=8, pady=6, highlightthickness=1, highlightbackground="#dfe3dc")
        self.sql_text.pack(fill="x", pady=(4, 6))
        bar = ttk.Frame(right)
        bar.pack(fill="x")
        ttk.Button(bar, text="▶ Run query", style="Accent.TButton", command=self._run_query).pack(side="left")
        self.sql_status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.sql_status.pack(side="left", padx=10)
        self.result_frame = ttk.Frame(right)
        self.result_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.result_tree = None
        self.query_list.selection_set(0)
        self._pick_query()

    def _pick_query(self, _=None):
        sel = self.query_list.curselection()
        if not sel:
            return
        self.sql_text.delete("1.0", "end")
        self.sql_text.insert("1.0", EXP8_QUERIES[sel[0]][1])
        self._run_query()

    def _run_query(self):
        try:
            columns, rows = self.app.db.run_select(self.sql_text.get("1.0", "end"))
        except DatabaseError as e:
            self.sql_status.configure(text=str(e), foreground="#c62828")
            return
        if self.result_tree is not None:
            self.result_tree.master.destroy()
        frame, self.result_tree = make_tree(self.result_frame,
                                            [(f"c{i}", c, 110, "w") for i, c in enumerate(columns)], height=14)
        frame.pack(fill="both", expand=True)
        fill_tree(self.result_tree, [(i, tuple(r)) for i, r in enumerate(rows)])
        self.sql_status.configure(text=f"{len(rows)} row(s) returned", foreground="#5b6770")

    def _add_record(self):
        try:
            m = parse_float_in_range(self.rec_vars["m"].get(), "Moisture", 0, 100, InvalidPlotDataError)
            t = parse_float_in_range(self.rec_vars["t"].get(), "Temperature", -5, 55, InvalidPlotDataError)
            h = parse_float_in_range(self.rec_vars["h"].get(), "Humidity", 0, 100, InvalidPlotDataError)
            sid, rec = self.app.db.add_sensor_record(m, t, h)
        except IrrigationError as e:
            messagebox.showerror("Cannot add record", str(e))
            return
        self.rec_result.configure(text=f"Saved as sensor {sid}: {rec}")
        self.app.set_status(f"Sensor {sid} saved to Sensor_Data and Irrigation_Advisory ({rec}).")
        self._run_query()

    # ---------------------------------------------------------------- Exp 6 tab
    def _build_exp6(self, tab):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        form = ttk.LabelFrame(tab, text=" Sensor input ", padding=10)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.e6 = {}
        defaults = [("farm", "Farm ID", "FARM101"), ("soil", "Soil moisture readings (comma separated)", "28, 32, 25, 30, 26"),
                    ("temp", "Temperature (°C)", "36"), ("hum", "Humidity (%)", "48"), ("rain", "Rainfall (mm)", "2")]
        for key, label, value in defaults:
            ttk.Label(form, text=label).pack(anchor="w", pady=(4, 0))
            var = tk.StringVar(value=value)
            ttk.Entry(form, textvariable=var, width=34).pack(fill="x")
            self.e6[key] = var
        ttk.Button(form, text="Generate advisory", style="Accent.TButton", command=self._run_exp6).pack(fill="x", pady=(10, 4))
        ttk.Separator(form).pack(fill="x", pady=8)
        ttk.Label(form, text="Or use the last 5 live readings of a plot:").pack(anchor="w")
        self.e6_plot = tk.StringVar()
        self.e6_combo = ttk.Combobox(form, textvariable=self.e6_plot, state="readonly")
        self.e6_combo.pack(fill="x", pady=4)
        ttk.Button(form, text="Load plot readings", command=self._load_plot_readings).pack(fill="x")

        out = ttk.Frame(tab)
        out.grid(row=0, column=1, sticky="nsew")
        ttk.Label(out, text="Output (same format as my Exp 6)", style="H2.TLabel").pack(anchor="w")
        self.e6_out = tk.Text(out, height=11, font=(self.app.mono, 11), relief="flat", bg="#fbfcfa", padx=10, pady=8)
        self.e6_out.pack(fill="x", pady=(4, 10))
        ttk.Label(out, text="Collections and functions used", style="H2.TLabel").pack(anchor="w")
        self.e6_col = tk.Text(out, height=7, font=(self.app.mono, 10), relief="flat", bg="#f3effa", padx=10, pady=8)
        self.e6_col.pack(fill="both", expand=True, pady=(4, 0))
        self._run_exp6()

    def _run_exp6(self):
        try:
            readings = parse_readings(self.e6["soil"].get())
            temp = parse_float_in_range(self.e6["temp"].get(), "Temperature", -5, 55)
            hum = parse_float_in_range(self.e6["hum"].get(), "Humidity", 0, 100)
            rain = parse_float_in_range(self.e6["rain"].get(), "Rainfall", 0, 500)
            farm_id = self.e6["farm"].get().strip() or "FARM101"
        except ValueError as e:                     # bad number in the readings list
            messagebox.showerror("Invalid input", f"Readings must be numbers separated by commas.\n({e})")
            return
        except IrrigationError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        temp, hum, rain = map(clean_number, (temp, hum, rain))     # 36.0 -> 36, like int() in Exp 6
        r = sugarcane_advisory(farm_id, readings, temp, hum, rain)
        for widget, text in ((self.e6_out, format_advisory_report(r)), (self.e6_col, format_collections(r))):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")

    def _load_plot_readings(self):
        plot = next((p for p in self.farm.plots if p.name == self.e6_plot.get()), None)
        if not plot or not plot.readings:
            messagebox.showinfo("Plot readings", "Choose a plot first.")
            return
        last = plot.readings[-5:]
        self.e6["farm"].set(f"PLOT{plot.plot_id:03d}")
        self.e6["soil"].set(", ".join(f"{r.moisture:.1f}" for r in last))
        self.e6["temp"].set(f"{last[-1].temperature:.0f}")
        self.e6["hum"].set(f"{last[-1].humidity:.0f}")
        self.e6["rain"].set(f"{self.weather.today().rain_mm:g}")
        self._run_exp6()

    # ---------------------------------------------------------------- Exp 2 tab
    E2COLS = [("day", "Day", 50, "center"), ("m", "Moisture %", 90, "e"), ("t", "Temperature °C", 110, "e"),
              ("r", "Rainfall mm", 90, "e"), ("rec", "Recommendation", 160, "w")]

    def _build_exp2(self, tab):
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.records = build_records()                    # list of IrrigationRecord objects
        self.e2_info = ttk.Label(tab, text="", style="Info.TLabel", padding=6)
        self.e2_info.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        frame, self.e2_tree = make_tree(tab, self.E2COLS, height=14)
        frame.grid(row=1, column=0, sticky="nsew")
        self.e2_tree.bind("<<TreeviewSelect>>", self._e2_select)

        form = ttk.LabelFrame(tab, text=" Record ", padding=10)
        form.grid(row=1, column=1, sticky="ns", padx=(12, 0))
        self.e2v = {}
        for i, (key, label) in enumerate([("day", "Day"), ("m", "Moisture (%)"), ("t", "Temperature (°C)"),
                                          ("r", "Rainfall (mm)")]):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=9).grid(row=i, column=1, pady=2, padx=(6, 0))
            self.e2v[key] = var
        buttons = [("append()  - add new day", self._e2_add, "Accent.TButton"),
                   ("Update selected day", self._e2_update, "TButton"),
                   ("remove()  - delete selected", self._e2_delete, "TButton"),
                   ("pop()  - delete last day", self._e2_pop, "TButton"),
                   ("Search day", self._e2_search, "TButton"),
                   ("Reset to my 30-day sample", self._e2_reset, "TButton")]
        for i, (text, cmd, style) in enumerate(buttons):
            ttk.Button(form, text=text, command=cmd, style=style).grid(row=5 + i, column=0, columnspan=2,
                                                                      sticky="ew", pady=2)
        ttk.Label(form, text="Rule (Exp 2): moisture < 45 → Irrigate Today,\nrain > 15 mm → No Irrigation,\n"
                             "otherwise Monitor Soil.", style="Muted.TLabel").grid(row=12, column=0, columnspan=2,
                                                                                    sticky="w", pady=(8, 0))
        self._e2_show()

    def _e2_show(self, msg=""):
        fill_tree(self.e2_tree, [(r.day, (r.day, r.moisture, r.temperature, r.rainfall, r.recommendation))
                                 for r in self.records],
                  ["urgent" if r.recommendation == "Irrigate Today" else "rain" if r.recommendation == "No Irrigation"
                   else "" for r in self.records])
        count = sum(1 for r in self.records if r.recommendation == "Irrigate Today")
        self.e2_info.configure(text=f"{len(self.records)} IrrigationRecord objects in the list   |   "
                                    f"'Irrigate Today' on {count} days   {('|   ' + msg) if msg else ''}")

    def _e2_values(self):
        try:
            return (float(self.e2v["m"].get()), float(self.e2v["t"].get()), float(self.e2v["r"].get()))
        except ValueError:
            raise InvalidPlotDataError("Moisture, temperature and rainfall must be numbers.") from None

    def _e2_selected(self):
        sel = self.e2_tree.selection()
        return find_day(self.records, int(sel[0])) if sel else None

    def _e2_select(self, _=None):
        r = self._e2_selected()
        if r:
            for key, value in (("day", r.day), ("m", r.moisture), ("t", r.temperature), ("r", r.rainfall)):
                self.e2v[key].set(clean_number(value))

    def _e2_add(self):
        try:
            m, t, rain = self._e2_values()
        except IrrigationError as e:
            messagebox.showerror("Exp 2", str(e))
            return
        day = (self.records[-1].day + 1) if self.records else 1
        self.records.append(IrrigationRecord(day, clean_number(m), clean_number(t), clean_number(rain),
                                             get_advice(m, rain)))
        self._e2_show(f"Day {day} added")

    def _e2_update(self):
        r = self._e2_selected()
        if not r:
            messagebox.showinfo("Exp 2", "Select a day in the table first.")
            return
        try:
            m, t, rain = self._e2_values()
        except IrrigationError as e:
            messagebox.showerror("Exp 2", str(e))
            return
        r.moisture, r.temperature, r.rainfall = clean_number(m), clean_number(t), clean_number(rain)
        r.recommendation = get_advice(m, rain)            # list_name[index].attribute = new_value
        self._e2_show(f"Day {r.day} Updated Successfully")

    def _e2_delete(self):
        r = self._e2_selected()
        if not r:
            messagebox.showinfo("Exp 2", "Select a day in the table first.")
            return
        self.records.remove(r)
        self._e2_show(f"Day {r.day} Record Deleted Successfully")

    def _e2_pop(self):
        if not self.records:
            return
        r = self.records.pop()
        self._e2_show(f"Day {r.day} Record Deleted Successfully")

    def _e2_search(self):
        try:
            day = int(float(self.e2v["day"].get()))
        except ValueError:
            messagebox.showerror("Exp 2", "Enter the day number to search for.")
            return
        r = find_day(self.records, day)
        if r is None:
            self._e2_show(f"Day {day} not found")
            return
        self.e2_tree.selection_set(str(r.day))
        self.e2_tree.see(str(r.day))
        self._e2_show(f"Search Result (Day {day}): {r.moisture}% moisture, {r.recommendation}")

    def _e2_reset(self):
        self.records = build_records()
        self._e2_show("Sample data reloaded")

    # ---------------------------------------------------------------- live tab
    def _build_live(self, body):
        self.tiles_frame = ttk.Frame(body)
        self.tiles_frame.pack(fill="x")
        self.tiles = {}
        ctrl = ttk.Frame(body)
        ctrl.pack(fill="x", pady=(12, 4))
        ttk.Label(ctrl, text="Chart:", style="H2.TLabel").pack(side="left")
        self.choice = tk.StringVar(value="All plots")
        self.combo = ttk.Combobox(ctrl, textvariable=self.choice, state="readonly", width=22)
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.stats = ttk.Label(ctrl, text="", style="Muted.TLabel")
        self.stats.pack(side="left", padx=10)
        self.chart = LineChart(body, title="Soil moisture (%) - last readings", height=290,
                               font=(self.app.font, 9))
        self.chart.pack(fill="both", expand=True)

    def _rebuild_tiles(self):
        for t in self.tiles.values():
            t.destroy()
        self.tiles = {}
        for i, p in enumerate(self.farm.plots):
            tile = MoistureTile(self.tiles_frame, self.app.font)
            tile.grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
            self.tiles[p.plot_id] = tile
        for c in range(3):
            self.tiles_frame.columnconfigure(c, weight=1)

    def refresh(self):
        plots = self.farm.plots
        if set(self.tiles) != {p.plot_id for p in plots}:
            self._rebuild_tiles()
        detector = self.app.adv["stress"]
        hist = self.app.history
        running = self.app.sensor.pumps_running()
        for p in plots:
            level = detector.analyze(p, self.weather)["level"]
            self.tiles[p.plot_id].show(p, level, hist.trend(p.plot_id), hist.moving_average(p.plot_id),
                                       p.plot_id in running)
        names = ["All plots"] + [p.name for p in plots]
        self.combo.configure(values=names)
        self.e6_combo.configure(values=names[1:])
        if self.choice.get() not in names:
            self.choice.set("All plots")

        if self.choice.get() == "All plots":
            series = [(p.name, hist.get(p.plot_id)[-40:], None) for p in plots]
            self.chart.set_data(series, unit="%")
            values = [p.current_moisture for p in plots]
            s = an.stats(values)
            self.stats.configure(text=f"Across plots now - min {s['min']}%, max {s['max']}%, mean {s['mean']}%")
        else:
            p = next(p for p in plots if p.name == self.choice.get())
            values = hist.get(p.plot_id)[-40:]
            times = [r.timestamp.strftime("%H:%M") for r in p.readings[-40:]]
            self.chart.set_data([(p.name, values, PALETTE[0])], x_labels=times, unit="%",
                                refs=[("Field capacity", p.field_capacity, "#19a979"),
                                      ("Irrigate below", p.threshold, "#e8743b"),
                                      ("Wilting point", p.wilting_point, "#c62828")],
                                y_range=(p.wilting_point - 4, p.field_capacity + 3))
            s = an.stats(values)
            changes = an.pairwise_changes(values[-6:])
            self.stats.configure(text=f"min {s['min']}%  max {s['max']}%  mean {s['mean']}%  |  last changes {changes}")


# =============================================================================
# 3. Crop Water Requirement Dashboard
# =============================================================================
class WaterRequirementPage(BasePage):
    title = "3. Crop Water Requirement"
    subtitle = "Daily water need of each plot:  ETc = ET0 x Kc  (FAO-56).  ET0 comes from today's temperature (Hargreaves); Kc depends on the crop stage."
    concepts = "abstract class Advisor -> WaterRequirementAdvisor, dictionaries, list comprehension, reduce"

    COLS = [("plot", "Plot", 110, "w"), ("stage", "Stage", 95, "w"), ("kc", "Kc", 45, "e"),
            ("et0", "ET0 mm", 60, "e"), ("etc", "ETc mm/day", 80, "e"), ("method", "Method", 65, "center"),
            ("net", "Net L/day", 90, "e"), ("gross", "Pumped L/day", 100, "e"), ("week", "m³ / week", 80, "e")]

    def build(self, body):
        self.info = ttk.Label(body, text="", style="Info.TLabel", padding=8)
        self.info.pack(fill="x", pady=(0, 8))
        frame, self.tree = make_tree(body, self.COLS, height=7)
        frame.pack(fill="x")
        charts = ttk.Frame(body)
        charts.pack(fill="both", expand=True, pady=(10, 0))
        charts.columnconfigure((0, 1), weight=1)
        charts.rowconfigure(0, weight=1)
        self.bar = BarChart(charts, title="Water to pump today (litres)", font=(self.app.font, 9))
        self.bar.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.kc_chart = LineChart(charts, title="Sugarcane crop coefficient (Kc) through the season",
                                  font=(self.app.font, 9))
        self.kc_chart.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def refresh(self):
        adv = self.app.adv["water"]
        results = [(p, adv.analyze(p, self.weather)) for p in self.farm.plots]
        today = self.weather.today()
        total = sum(r["gross_litres"] for _, r in results)
        self.info.configure(text=f"Today {today.day:%d %b}:  Tmax {today.tmax} °C, Tmin {today.tmin} °C  ->  "
                                 f"ET0 = {self.weather.et0(today)} mm/day.     Farm total = {total:,} litres "
                                 f"({total / 1000:,.0f} m³) today")
        fill_tree(self.tree, [(p.plot_id, (p.name, r["stage"], r["kc"], r["et0"], r["etc_mm"], p.method,
                                           f"{r['net_litres']:,}", f"{r['gross_litres']:,}", r["weekly_m3"]))
                              for p, r in results])
        self.bar.set_data([p.name for p, _ in results], [("Pumped", [r["gross_litres"] for _, r in results], None)])
        days = list(range(0, 391, 15))
        kc = [next((s[3] for s in GROWTH_STAGES if s[1] <= d < s[2]), GROWTH_STAGES[-1][3]) for d in days]
        self.kc_chart.set_data([("Kc", kc, PALETTE[2])], x_labels=[f"{d // 30}m" for d in days],
                               y_range=(0, 1.5))


# =============================================================================
# 4. Next Irrigation Date Prediction
# =============================================================================
class NextIrrigationPage(BasePage):
    title = "4. Next Irrigation Date Prediction"
    subtitle = "Simulates the soil water day by day (ETc out, effective rain in) until moisture reaches the safe level of each plot."
    concepts = "loops & simulation inside a class method, sorted() with lambda key, date arithmetic"

    COLS = [("plot", "Plot", 110, "w"), ("moist", "Moisture %", 80, "e"), ("safe", "Safe level %", 85, "e"),
            ("rate", "Loss %/day", 75, "e"), ("days", "Days left", 70, "e"), ("date", "Next irrigation", 110, "center"),
            ("last", "Last irrigated", 130, "center")]

    def build(self, body):
        frame, self.tree = make_tree(body, self.COLS, height=7)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.draw_projection())
        charts = ttk.Frame(body)
        charts.pack(fill="both", expand=True, pady=(10, 0))
        charts.columnconfigure((0, 1), weight=1)
        charts.rowconfigure(0, weight=1)
        self.bar = BarChart(charts, horizontal=True, title="Days until next irrigation", font=(self.app.font, 9))
        self.bar.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.proj = LineChart(charts, title="10-day moisture projection (select a plot)", font=(self.app.font, 9))
        self.proj.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def refresh(self):
        adv = self.app.adv["next"]
        results = sorted(((p, adv.analyze(p, self.weather)) for p in self.farm.plots),
                         key=lambda pr: pr[1]["days_left"])
        rows, tags = [], []
        for p, r in results:
            last = self.app.db.last_irrigation(p.plot_id)
            rows.append((p.plot_id, (p.name, f"{r['moisture']:.1f}", r["threshold"], r["depletion_per_day"],
                                     r["days_left"], "TODAY" if r["days_left"] == 0 else f"{r['next_date']:%a %d %b}",
                                     last[:16] if last else "-")))
            tags.append("urgent" if r["days_left"] == 0 else "plan" if r["days_left"] <= 3 else "ok")
        fill_tree(self.tree, rows, tags)
        colors = ["#c62828" if r["days_left"] == 0 else "#e8a33b" if r["days_left"] <= 3 else "#19a979"
                  for _, r in results]
        self.bar.set_data([p.name for p, _ in results], [("Days", [r["days_left"] for _, r in results], None)],
                          unit=" d", bar_colors=colors)
        if not self.tree.selection() and results:
            self.tree.selection_set(str(results[0][0].plot_id))
        self.draw_projection()

    def draw_projection(self):
        plot = self.selected_plot(self.tree)
        if not plot:
            return
        values = self.app.adv["next"].project(plot, self.weather, 10)
        labels = ["Today"] + [self.weather.day(i).day.strftime("%d %b") for i in range(1, 11)]
        self.proj.title = f"10-day moisture projection - {plot.name} (no irrigation)"
        self.proj.set_data([(plot.name, values, PALETTE[0])], x_labels=labels, unit="%",
                           refs=[("Irrigate below", plot.threshold, "#e8743b"),
                                 ("Wilting point", plot.wilting_point, "#c62828")],
                           y_range=(plot.wilting_point - 4, plot.field_capacity + 2))


# =============================================================================
# 5. Smart Irrigation Recommendation System
# =============================================================================
class RecommendationPage(BasePage):
    title = "5. Smart Irrigation Recommendation"
    subtitle = "Soil-moisture based advice: how much water each plot needs (refill root zone to field capacity) and how long to run the pump."
    concepts = "IrrigationAdvisor (inherits Advisor), composition, sorting | Exp 5: sensor.py + recommendation.py in 3 threads | Exp 7: Entry/grid/Button form"

    COLS = [("prio", "#", 30, "center"), ("plot", "Plot", 110, "w"), ("action", "Recommendation", 170, "w"),
            ("moist", "Moisture %", 75, "e"), ("safe", "Safe %", 55, "e"), ("net", "Net mm", 60, "e"),
            ("vol", "Water (L)", 95, "e"), ("hrs", "Pump hrs", 65, "e"), ("reason", "Why", 260, "w")]

    def build(self, body):
        frame, self.tree = make_tree(body, self.COLS, height=8)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.explain())
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="▶ Start irrigation for selected plot", style="Accent.TButton",
                   command=self.irrigate_selected).pack(side="left")
        ttk.Button(bar, text="Irrigate all urgent plots", command=self.irrigate_urgent).pack(side="left", padx=8)
        lower = ttk.Frame(body)
        lower.pack(fill="both", expand=True)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)
        ttk.Label(lower, text="How the amount is calculated", style="H2.TLabel").grid(row=0, column=0, sticky="w", pady=(6, 2))
        self.text = tk.Text(lower, height=9, font=(self.app.mono, 10), relief="flat", bg="#fbfcfa", padx=10, pady=6)
        self.text.grid(row=1, column=0, sticky="nsew")
        self._build_quick_check(lower)

    # ---- my Exp 7 form: enter sensor values -> recommendation
    def _build_quick_check(self, parent):
        box = ttk.LabelFrame(parent, text=" Quick check from sensor values (my Exp 7 form) ", padding=10)
        box.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(12, 0), pady=(6, 0))
        self.q_entries = {}
        for i, label in enumerate(["Soil Moisture (%):", "Temperature (°C):", "Humidity (%):"]):
            tk.Label(box, text=label, font=(self.app.font, 10), bg="#f4f6f2").grid(row=i, column=0, sticky="w", padx=4, pady=2)
            entry = tk.Entry(box, width=10, font=(self.app.font, 10))
            entry.grid(row=i, column=1, padx=4, pady=2)
            self.q_entries[i] = entry
        self.q_save = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Also save to Sensor_Data (Exp 8)", variable=self.q_save).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tk.Button(box, text="Generate Irrigation Recommendation", font=(self.app.font, 10, "bold"), bg="green",
                  fg="white", activebackground="#1b5e20", activeforeground="white", padx=12, pady=6,
                  relief="flat", command=self.generate_recommendation).grid(row=4, column=0, columnspan=2, pady=6)
        self.q_label = tk.Label(box, text="Enter sensor values and click the button", font=(self.app.font, 10, "bold"),
                                fg="darkblue", bg="#f4f6f2", wraplength=300, justify="left")
        self.q_label.grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Button(box, text="Read selected plot with 3 threads (Exp 5)",
                   command=self.read_with_threads).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(box, text="Rule: below 40% → Irrigation Required, below 60% → Recommended Soon, otherwise not required.",
                  style="Muted.TLabel", wraplength=300).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def read_with_threads(self):
        """My Exp 5: one thread per sensor (sensor.py), then recommend() (recommendation.py)."""
        plot = self.selected_plot(self.tree)
        if not plot:
            messagebox.showinfo("Exp 5", "Select a plot in the table first.")
            return
        reading = plot.latest_reading
        values = {"soil moisture": round(plot.current_moisture, 1),
                  "temperature": round(reading.temperature if reading else self.weather.today().tmax, 1),
                  "humidity": round(reading.humidity if reading else self.weather.today().humidity, 1)}
        self._exp5_result = None
        self.q_label.config(text=f"Reading 3 sensors of '{plot.name}' in 3 threads...", fg="#5b6770")

        def worker():                                     # runs outside the GUI thread
            self._exp5_result = monitor_all(values, delay=1, log=lambda *a: None)

        threading.Thread(target=worker, daemon=True).start()
        self.after(200, lambda: self._wait_exp5(plot.name))

    def _wait_exp5(self, name):
        if self._exp5_result is None:                     # threads still running -> check again
            self.after(200, lambda: self._wait_exp5(name))
            return
        data, result = self._exp5_result
        for i, key in enumerate(("soil moisture", "temperature", "humidity")):
            self.q_entries[i].delete(0, "end")
            self.q_entries[i].insert(0, clean_number(data[key]))
        self.q_label.config(text=f"{name} - recommend(): {result}", fg="darkblue")

    def generate_recommendation(self):
        try:
            moisture = float(self.q_entries[0].get())
            temperature = float(self.q_entries[1].get())
            humidity = float(self.q_entries[2].get())
        except ValueError:
            self.q_label.config(text="Please enter valid numeric values.", fg="#c62828")
            return
        result = classify_moisture(moisture)
        text = "Irrigation Recommendation: " + result
        if self.q_save.get():
            try:
                sid, _ = self.app.db.add_sensor_record(moisture, temperature, humidity)
                text += f"\n(saved as sensor {sid})"
            except DatabaseError as e:
                text += f"\n(not saved: {e})"
        self.q_label.config(text=text, fg="darkblue")

    def results(self):
        adv = self.app.adv["basic"]
        return an.rank_by_urgency([adv.analyze(p, self.weather) for p in self.farm.plots])

    def refresh(self):
        recs = self.results()
        running = self.app.sensor.pumps_running()          # plot_id -> pump hours left
        rows, tags = [], []
        for r in recs:
            if r["plot_id"] in running:                     # already being watered
                rows.append((r["plot_id"], ("-", r["plot_name"], "PUMP ON - WATERING", f"{r['moisture']:.1f}",
                                            r["threshold"], r["net_mm"], "-", f"{running[r['plot_id']]:.1f} left",
                                            "Moisture is rising; it will stop by itself")))
                tags.append("rain")
                continue
            rows.append((r["plot_id"], (r["priority"], r["plot_name"], r["action"], f"{r['moisture']:.1f}",
                                        r["threshold"], r["net_mm"],
                                        f"{r['volume_l']:,}" if r["priority"] <= 3 else "-",
                                        r["duration_h"] if r["priority"] <= 3 else "-", r["reason"])))
            tags.append(PRIORITY_TAG[r["priority"]])
        fill_tree(self.tree, rows, tags)
        if not self.tree.selection() and recs:
            self.tree.selection_set(str(recs[0]["plot_id"]))
        self.explain()

    def explain(self):
        plot = self.selected_plot(self.tree)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if not plot:
            self.text.insert("1.0", "Select a plot to see the step-by-step calculation.")
        else:
            r = self.app.adv["basic"].analyze(plot, self.weather)
            deficit = max(0, plot.field_capacity - plot.current_moisture)
            lines = [
                f"Plot {plot.name} ({plot.method}, {plot.area_acres} acres = {plot.area_m2:,.0f} m²)",
                f"1. Field capacity {plot.field_capacity}% - current {plot.current_moisture:.1f}% = deficit {deficit:.1f}%",
                f"2. Root zone at {plot.stage} stage = {plot.root_depth_mm:.0f} mm",
                f"3. Net depth = {deficit:.1f}% x {plot.root_depth_mm:.0f} mm = {r['net_mm']} mm",
                f"4. Gross depth = net / efficiency {plot.efficiency:.0%} = {r['gross_mm']} mm",
                f"5. Volume = {r['gross_mm']} mm x {plot.area_m2:,.0f} m² x wetted {plot.wetted_fraction:.0%} = {r['volume_l']:,} L",
                f"6. Pump time = {r['volume_l']:,} L / {plot.pump_lph:,.0f} L/h = {r['duration_h']} h",
                "",
                f"Decision: {r['action']}  -  {r['reason']}",
            ]
            left = self.app.sensor.pumps_running().get(plot.plot_id)
            if left:
                lines += ["", f"PUMP IS ON: {left:.1f} pump hours left. The numbers above are what is still",
                          "missing right now - they shrink as the soil fills up."]
            self.text.insert("1.0", "\n".join(lines))
        self.text.configure(state="disabled")

    def irrigate_selected(self):
        plot = self.selected_plot(self.tree)
        if not plot:
            messagebox.showinfo("Irrigate", "Select a plot first.")
            return
        if plot.plot_id in self.app.sensor.pumps_running():
            messagebox.showinfo("Irrigate", f"The pump for '{plot.name}' is already ON.")
            return
        r = self.app.adv["basic"].analyze(plot, self.weather)
        if r["volume_l"] <= 0:
            messagebox.showinfo("Irrigate", f"'{plot.name}' is already at field capacity.")
            return
        self.app.start_irrigation(plot, r["duration_h"], r["volume_l"], "Recommendation")

    def irrigate_urgent(self):
        running = self.app.sensor.pumps_running()
        recs = [r for r in self.results() if r["priority"] == 1 and r["plot_id"] not in running]
        if not recs:
            messagebox.showinfo("Irrigate", "No dry plot is waiting - pumps are already on or plots are fine.")
        for r in recs:
            self.app.start_irrigation(self.farm.get_plot(r["plot_id"]), r["duration_h"], r["volume_l"], "Recommendation")


# =============================================================================
# 6. Weather-Aware Irrigation Advisory
# =============================================================================
class WeatherPage(BasePage):
    title = "6. Weather-Aware Irrigation Advisory"
    subtitle = "7-day forecast with evapotranspiration. Rain in the next 48 h reduces or postpones irrigation. Edit a day to try 'what if it rains tomorrow?'."
    concepts = "method overriding + super() (WeatherAwareAdvisor extends IrrigationAdvisor), namedtuple, thread Lock | Exp 3: SmartFarm(WeatherData, SoilData) multiple inheritance"

    COLS = [("plot", "Plot", 110, "w"), ("basic", "Soil-only advice", 190, "w"),
            ("smart", "Weather-aware advice", 200, "w"), ("vol", "Water (L)", 90, "e"),
            ("rain", "Rain 48h mm", 85, "e"), ("exp3", "SmartFarm (Exp 3)", 125, "w"),
            ("note", "Weather note", 300, "w")]

    def build(self, body):
        self.cards = ttk.Frame(body)
        self.cards.pack(fill="x")
        mid = ttk.Frame(body)
        mid.pack(fill="x", pady=10)
        mid.columnconfigure(0, weight=1)
        self.chart = BarChart(mid, title="Rain vs crop water use (mm/day)", height=200, font=(self.app.font, 9))
        self.chart.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        form = ttk.LabelFrame(mid, text=" Edit forecast day ", padding=8)
        form.grid(row=0, column=1, sticky="ns")
        self.day_var = tk.StringVar()
        self.day_combo = ttk.Combobox(form, textvariable=self.day_var, state="readonly", width=14)
        self.day_combo.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.day_combo.bind("<<ComboboxSelected>>", lambda e: self.load_day())
        self.fields = {}
        for i, (key, label) in enumerate([("tmax", "Max °C"), ("tmin", "Min °C"),
                                          ("hum", "Humidity %"), ("rain", "Rain mm")]):
            ttk.Label(form, text=label).grid(row=i + 1, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=8).grid(row=i + 1, column=1, pady=2)
            self.fields[key] = var
        ttk.Button(form, text="Update day", style="Accent.TButton", command=self.save_day).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(form, text="New random forecast", command=self.new_forecast).grid(
            row=6, column=0, columnspan=2, sticky="ew")
        frame, self.tree = make_tree(body, self.COLS, height=6)
        frame.pack(fill="both", expand=True)

    def refresh(self):
        days = self.weather.all_days()
        for w in self.cards.winfo_children():
            w.destroy()
        for i, d in enumerate(days):
            card = ttk.Frame(self.cards, style="Card.TFrame", padding=8)
            card.grid(row=0, column=i, sticky="nsew", padx=3)
            self.cards.columnconfigure(i, weight=1)
            icon = "\U0001F327" if d.rain_mm >= 5 else "\U0001F326" if d.rain_mm > 0 else "☀"
            ttk.Label(card, text=("Today" if i == 0 else d.day.strftime("%a")) + d.day.strftime(" %d %b"),
                      style="CardBold.TLabel").pack(anchor="w")
            ttk.Label(card, text=f"{icon}  {d.tmax:.0f}° / {d.tmin:.0f}°", style="CardBig.TLabel").pack(anchor="w")
            ttk.Label(card, text=f"Rain {d.rain_mm} mm\nRH {d.humidity:.0f}%\nET0 {self.weather.et0(d)} mm",
                      style="Card.TLabel").pack(anchor="w")
        labels = [d.day.strftime("%d %b") for d in days]
        self.day_combo.configure(values=labels)
        if not self.day_var.get():
            self.day_var.set(labels[0])
            self.load_day()
        avg_kc = sum(p.kc for p in self.farm.plots) / max(1, len(self.farm.plots))
        self.chart.set_data(labels, [("Rain", [d.rain_mm for d in days], "#2a78d6"),
                                     ("Crop use (ETc, avg Kc)", [round(self.weather.et0(d) * avg_kc, 1) for d in days], "#e8743b")])
        basic, smart = self.app.adv["basic"], self.app.adv["weather"]
        rows, tags = [], []
        for p in self.farm.plots:
            b, s = basic.analyze(p, self.weather), smart.analyze(p, self.weather)
            farm = SmartFarm()                            # my Exp 3 class (WeatherData + SoilData)
            farm.moisture = round(p.current_moisture, 1)
            farm.rainfall = self.weather.today().rain_mm
            water = f"{s['volume_l']:,}" if s["priority"] <= 3 else "-"
            rows.append((p.plot_id, (p.name, b["action"], s["action"], water, s["rain_48h"],
                                     farm.advice_text(), s["weather_note"] or "-")))
            tags.append(PRIORITY_TAG[s["priority"]])
        fill_tree(self.tree, rows, tags)

    def _index(self):
        labels = list(self.day_combo.cget("values"))
        return labels.index(self.day_var.get()) if self.day_var.get() in labels else 0

    def load_day(self):
        d = self.weather.day(self._index())
        for key, value in zip(("tmax", "tmin", "hum", "rain"), (d.tmax, d.tmin, d.humidity, d.rain_mm)):
            self.fields[key].set(str(value))

    def save_day(self):
        try:
            self.weather.update_day(self._index(), self.fields["tmax"].get(), self.fields["tmin"].get(),
                                    self.fields["hum"].get(), self.fields["rain"].get())
        except IrrigationError as e:
            messagebox.showerror("Invalid weather", str(e))
            return
        self.app.set_status(f"Forecast for {self.day_var.get()} updated.")
        self.app.refresh_all()

    def new_forecast(self):
        self.weather.regenerate(seed=datetime.now().microsecond)
        self.load_day()
        self.app.refresh_all()


# =============================================================================
# 7. Water Stress Detection & Alert Dashboard
# =============================================================================
class StressPage(BasePage):
    title = "7. Water Stress Detection & Alerts"
    subtitle = "Every new sensor batch is checked. When a plot's stress level gets worse, an alert is stored in SQLite and (optionally) sent to the farmer."
    concepts = "StressDetector (Advisor subclass), custom SensorError, higher-order make_alert_filter(), SQL JOIN | Exp 3: CropHealthAnalyzer multilevel inheritance"

    COLS = [("ts", "Time", 140, "w"), ("plot", "Plot", 110, "w"), ("level", "Level", 75, "center"),
            ("msg", "Message", 520, "w"), ("ack", "Seen", 50, "center")]

    def build(self, body):
        self.tile_frame = ttk.Frame(body)
        self.tile_frame.pack(fill="x")
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(12, 4))
        ttk.Label(bar, text="Alert log", style="H2.TLabel").pack(side="left")
        ttk.Label(bar, text="   show:").pack(side="left")
        self.filter = tk.StringVar(value="INFO")
        for text, value in [("All", "INFO"), ("Mild +", "MILD"), ("Severe +", "SEVERE"), ("Critical", "CRITICAL")]:
            ttk.Radiobutton(bar, text=text, value=value, variable=self.filter,
                            command=self.refresh).pack(side="left", padx=3)
        ttk.Button(bar, text="Mark all as seen", command=self.ack).pack(side="right")
        ttk.Button(bar, text="Run check now", command=lambda: (self.app.check_stress(), self.refresh())).pack(side="right", padx=6)
        frame, self.tree = make_tree(body, self.COLS, height=10)
        frame.pack(fill="both", expand=True)

    def refresh(self):
        for w in self.tile_frame.winfo_children():
            w.destroy()
        det = self.app.adv["stress"]
        for i, p in enumerate(self.farm.plots):
            r = det.analyze(p, self.weather)
            tile = tk.Frame(self.tile_frame, bg=r["color"], padx=10, pady=6)
            tile.grid(row=0, column=i, sticky="nsew", padx=3)
            self.tile_frame.columnconfigure(i, weight=1)
            tk.Label(tile, text=p.name, bg=r["color"], fg="white", font=(self.app.font, 10, "bold")).pack(anchor="w")
            tk.Label(tile, text=r["level"], bg=r["color"], fg="white", font=(self.app.font, 15, "bold")).pack(anchor="w")
            tk.Label(tile, text=f"{r['moisture']:.1f}% | {r['temperature']:.0f}°C", bg=r["color"], fg="white",
                     font=(self.app.font, 9)).pack(anchor="w")
            analyzer = CropHealthAnalyzer()             # my Exp 3 class (Sensor -> SoilSensor -> Analyzer)
            analyzer.sensor_data()
            analyzer.moisture = r["moisture"]
            tk.Label(tile, text=f"Exp 3: {analyzer.health()}", bg=r["color"], fg="white",
                     font=(self.app.font, 8, "italic")).pack(anchor="w")
        keep = an.make_alert_filter(self.filter.get())
        alerts = list(filter(keep, self.app.db.recent_alerts(200)))
        fill_tree(self.tree, [(a["alert_id"], (a["ts"], a["plot"] or "-", a["level"], a["message"],
                                               "✓" if a["acknowledged"] else ""))
                              for a in alerts], [a["level"] for a in alerts])

    def ack(self):
        self.app.db.acknowledge_all()
        self.app.refresh_all()


# =============================================================================
# 8. Irrigation Duration & Pump Scheduling
# =============================================================================
class PumpPage(BasePage):
    title = "8. Irrigation Duration & Pump Scheduling"
    subtitle = "Builds a pump timetable: the most urgent plot is irrigated first on whichever pump becomes free first (greedy scheduling)."
    concepts = "PumpScheduler class, sorted() with tuple keys, timedelta, SQLite INSERT + GROUP BY reports"

    SCOLS = [("pump", "Pump", 50, "center"), ("plot", "Plot", 110, "w"), ("start", "Start", 90, "center"),
             ("end", "End", 90, "center"), ("hrs", "Hours", 60, "e"), ("vol", "Water (L)", 100, "e"), ("act", "Advice", 200, "w")]
    HCOLS = [("plot", "Plot", 110, "w"), ("start", "Started", 135, "w"), ("hrs", "Hours", 55, "e"),
             ("vol", "Litres", 90, "e"), ("src", "Source", 100, "w")]

    def build(self, body):
        ctrl = ttk.Frame(body)
        ctrl.pack(fill="x")
        self.start = tk.StringVar(value="06:00")
        self.pumps = tk.IntVar(value=2)
        self.gap = tk.IntVar(value=10)
        self.planned = tk.BooleanVar(value=True)
        ttk.Label(ctrl, text="Start time").pack(side="left")
        ttk.Entry(ctrl, textvariable=self.start, width=7).pack(side="left", padx=(4, 14))
        ttk.Label(ctrl, text="Pumps").pack(side="left")
        ttk.Spinbox(ctrl, from_=1, to=4, textvariable=self.pumps, width=4, command=self.refresh).pack(side="left", padx=(4, 14))
        ttk.Label(ctrl, text="Gap (min)").pack(side="left")
        ttk.Spinbox(ctrl, from_=0, to=60, increment=5, textvariable=self.gap, width=4, command=self.refresh).pack(side="left", padx=(4, 14))
        ttk.Checkbutton(ctrl, text="Include plots due in 3 days", variable=self.planned, command=self.refresh).pack(side="left")
        ttk.Button(ctrl, text="Build schedule", command=self.refresh).pack(side="left", padx=10)
        ttk.Button(ctrl, text="▶ Start pumps now", style="Accent.TButton", command=self.run_now).pack(side="left")
        self.gantt = GanttChart(body, title="Pump timetable", height=190, font=(self.app.font, 9))
        self.gantt.pack(fill="x", pady=8)
        frame, self.tree = make_tree(body, self.SCOLS, height=5)
        frame.pack(fill="x")
        bottom = ttk.Frame(body)
        bottom.pack(fill="both", expand=True, pady=(10, 0))
        bottom.columnconfigure((0, 1), weight=1)
        bottom.rowconfigure(1, weight=1)
        ttk.Label(bottom, text="Irrigation history (from database)", style="H2.TLabel").grid(row=0, column=0, sticky="w")
        hframe, self.history = make_tree(bottom, self.HCOLS, height=6)
        hframe.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.used = BarChart(bottom, title="Water used in last 30 days (m³)", height=170, font=(self.app.font, 9))
        self.used.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

    def schedule(self):
        try:
            hh, mm = (int(x) for x in self.start.get().split(":"))
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError
        except ValueError:
            self.start.set("06:00")
            messagebox.showerror("Invalid time", "Start time must look like 06:00")
        try:
            pumps = max(1, int(self.pumps.get()))
            gap = max(0, int(self.gap.get()))
        except (tk.TclError, ValueError):
            pumps, gap = 1, 10
        running = self.app.sensor.pumps_running()          # skip plots that are already being watered
        recs = [self.app.adv["weather"].analyze(p, self.weather) for p in self.farm.plots if p.plot_id not in running]
        return self.app.scheduler.build(recs, self.start.get(), pumps, gap, self.planned.get())

    def refresh(self):
        sched = self.schedule()
        self._last = sched
        self.gantt.set_data([(f"P{s['pump']} · {s['plot_name']}", s["start"], s["end"],
                              PALETTE[(s["pump"] - 1) % len(PALETTE)], f"{s['duration_h']:.1f} h") for s in sched])
        fill_tree(self.tree, [(i, (s["pump"], s["plot_name"], s["start"].strftime("%H:%M"),
                                   s["end"].strftime("%H:%M") + (" (+1)" if s["end"].date() > s["start"].date() else ""),
                                   s["duration_h"], f"{s['volume_l']:,}", s["action"])) for i, s in enumerate(sched)],
                  [PRIORITY_TAG[s["priority"]] for s in sched])
        fill_tree(self.history, [(h["event_id"], (h["plot"], h["start_ts"][:16], h["duration_h"], f"{h['volume_l']:,.0f}", h["source"]))
                                 for h in self.app.db.irrigation_history(100)])
        used = self.app.db.water_used_by_plot(30)
        self.used.set_data([u["plot"] for u in used], [("m3", [u["m3"] for u in used], "#2a78d6")])

    def run_now(self):
        sched = self.schedule()
        if not sched:
            messagebox.showinfo("Pumps", "Nothing to irrigate right now.")
            return
        for s in sched:
            self.app.start_irrigation(self.farm.get_plot(s["plot_id"]), s["duration_h"], s["volume_l"], f"Schedule P{s['pump']}")
        self.refresh()


# =============================================================================
# 9. Fertigation Recommendation
# =============================================================================
class FertigationPage(BasePage):
    title = "9. Fertigation Recommendation"
    subtitle = "Weekly fertiliser dose per plot from the recommended 250:115:115 kg N:P₂O₅:K₂O per hectare, split by growth stage."
    concepts = "FertigationAdvisor, generator expressions + zip, class attributes (dict of tuples)"

    COLS = [("plot", "Plot", 110, "w"), ("method", "Method", 60, "center"), ("stage", "Stage", 95, "w"),
            ("n", "N kg", 55, "e"), ("p", "P kg", 55, "e"), ("k", "K kg", 55, "e"),
            ("urea", "Urea kg", 65, "e"), ("map", "12:61:00 kg", 80, "e"), ("mop", "MOP kg", 65, "e"),
            ("note", "Note", 330, "w")]

    def build(self, body):
        frame, self.tree = make_tree(body, self.COLS, height=7)
        frame.pack(fill="x")
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Send this week's plan to farmer", style="Accent.TButton",
                   command=self.send).pack(side="left")
        lower = ttk.Frame(body)
        lower.pack(fill="both", expand=True)
        lower.columnconfigure(0, weight=2)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)
        self.chart = BarChart(lower, title="Nutrients this week (kg)", font=(self.app.font, 9))
        self.chart.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        split = ttk.LabelFrame(lower, text=" Season split (share of total dose) ", padding=8)
        split.grid(row=0, column=1, sticky="nsew")
        _, t = make_tree(split, [("stage", "Stage", 100, "w"), ("n", "N", 50, "e"), ("p", "P", 50, "e"), ("k", "K", 50, "e")], 4)
        _.pack(fill="both", expand=True)
        fill_tree(t, [(s, (s, f"{n:.0%}", f"{p:.0%}", f"{k:.0%}")) for s, (n, p, k) in FertigationAdvisor.STAGE_SPLIT.items()])
        ttk.Label(split, text="Urea = 46% N, 12:61:00 = 12% N + 61% P₂O₅,\nMOP = 60% K₂O.  Apply in 2 split doses.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    def results(self):
        adv = self.app.adv["fert"]
        return [(p, adv.analyze(p, self.weather)) for p in self.farm.plots]

    def refresh(self):
        res = self.results()
        fill_tree(self.tree, [(p.plot_id, (p.name, p.method, r["stage"], r["n_kg"], r["p_kg"], r["k_kg"], r["urea_kg"],
                                           r["map_kg"], r["mop_kg"], r["note"])) for p, r in res])
        self.chart.set_data([p.name for p, _ in res], [("N", [r["n_kg"] for _, r in res], "#19a979"),
                                                        ("P", [r["p_kg"] for _, r in res], "#e8743b"),
                                                        ("K", [r["k_kg"] for _, r in res], "#945ecf")])

    def send(self):
        f = self.farm.farmer
        for p, r in self.results():
            self.app.notify(compose_message("fertigation", f.language, f.name, plot=p.name,
                                            urea=r["urea_kg"], map=r["map_kg"], mop=r["mop_kg"]))
        self.app.set_status("Fertigation plan queued for sending.")


# =============================================================================
# 10. Farmer-Friendly AI Advisory & Notification System
# =============================================================================
class AdvisoryPage(BasePage):
    title = "10. Farmer-Friendly Advisory & Notifications"
    subtitle = "Turns the technical advice into short messages in English, Hindi or Marathi. Messages are sent by a background thread and logged in SQLite. Ask 'Krishi Mitra' a question in plain words."
    concepts = "string templates & format(), Producer-Consumer thread with queue, keyword matching with string methods"

    NCOLS = [("ts", "Time", 130, "w"), ("ch", "Channel", 70, "center"), ("lang", "Language", 70, "center"), ("msg", "Message", 700, "w")]

    def build(self, body):
        top = ttk.Frame(body)
        top.pack(fill="both", expand=True)
        top.columnconfigure(1, weight=1)
        top.rowconfigure(0, weight=1)

        prof = ttk.LabelFrame(top, text=" Farmer profile ", padding=10)
        prof.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.pv = {k: tk.StringVar() for k in ("name", "phone", "village", "language", "channel")}
        for key, label in [("name", "Name"), ("phone", "Mobile"), ("village", "Village")]:
            ttk.Label(prof, text=label).pack(anchor="w")
            ttk.Entry(prof, textvariable=self.pv[key], width=24).pack(fill="x", pady=(0, 6))
        ttk.Label(prof, text="Language").pack(anchor="w")
        ttk.Combobox(prof, textvariable=self.pv["language"], values=LANGUAGES, state="readonly").pack(fill="x", pady=(0, 6))
        ttk.Label(prof, text="Send by").pack(anchor="w")
        ttk.Combobox(prof, textvariable=self.pv["channel"], values=CHANNELS, state="readonly").pack(fill="x", pady=(0, 6))
        self.pv["channel"].set("SMS")
        ttk.Button(prof, text="Save profile", command=self.save_profile).pack(fill="x", pady=(4, 0))
        self.id_label = ttk.Label(prof, text="", style="Muted.TLabel", justify="left")
        self.id_label.pack(anchor="w", pady=(10, 0))

        mid = ttk.Frame(top)
        mid.grid(row=0, column=1, sticky="nsew")
        head = ttk.Frame(mid)
        head.pack(fill="x")
        ttk.Label(head, text="Today's advisory (preview)", style="H2.TLabel").pack(side="left")
        ttk.Button(head, text="✉ Send all to farmer", style="Accent.TButton", command=self.send_all).pack(side="right")
        self.preview = tk.Text(mid, height=9, wrap="word", font=(self.app.font, 10), relief="flat",
                               bg="#fbfcfa", padx=10, pady=6)
        self.preview.pack(fill="both", expand=True, pady=(4, 8))
        ask = ttk.LabelFrame(mid, text=" Ask Krishi Mitra (e.g. 'Should I water North Block?', 'how much urea?', 'will it rain?') ", padding=8)
        ask.pack(fill="x")
        self.question = tk.StringVar()
        entry = ttk.Entry(ask, textvariable=self.question)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self.answer())
        ttk.Button(ask, text="Ask", command=self.answer).pack(side="left", padx=(6, 0))
        self.reply = ttk.Label(mid, text="", style="Info.TLabel", wraplength=760, justify="left", padding=8)
        self.reply.pack(fill="x", pady=(6, 0))

        ttk.Label(body, text="Sent notifications", style="H2.TLabel").pack(anchor="w", pady=(10, 2))
        frame, self.log = make_tree(body, self.NCOLS, height=6)
        frame.pack(fill="both", expand=True)
        self.load_profile()

    def load_profile(self):
        f = self.farm.farmer
        self.pv["name"].set(f.name)
        self.pv["phone"].set(f.phone)
        self.pv["village"].set(f.village)
        self.pv["language"].set(f.language)

    def save_profile(self):
        name = self.pv["name"].get().strip()
        if len(name) < 2 or not all(ch.isalpha() or ch.isspace() for ch in name):
            messagebox.showerror("Profile", "Name must contain letters only.")
            return
        digits = "".join(c for c in self.pv["phone"].get() if c.isdigit())
        if len(digits) < 10:
            messagebox.showerror("Profile", "Mobile number needs at least 10 digits.")
            return
        self.app.db.update_farmer(self.farm.farmer.farmer_id, name, self.pv["phone"].get(),
                                  self.pv["village"].get(), self.pv["language"].get())
        self.app.reload_farm()
        self.load_profile()
        self.app.set_status("Farmer profile saved.")

    def messages(self):
        f = self.farm.farmer
        lang = self.pv["language"].get() or f.language
        recs = an.rank_by_urgency(self.app.recommendations())
        return [advice_to_message(r, lang, f.name) for r in recs]

    def refresh(self):
        f = self.farm.farmer
        self.id_label.configure(text=f"Display: {f}\nInitials: {f.initials}\nGreeting: {f.greeting()}")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n\n".join(f"• {m}" for m in self.messages()))
        self.preview.configure(state="disabled")
        fill_tree(self.log, [(n["notif_id"], (n["ts"], n["channel"], n["language"], n["message"]))
                             for n in self.app.db.recent_notifications(100)])

    def send_all(self):
        for m in self.messages():
            self.app.notify(m, self.pv["channel"].get())
        self.app.set_status("Advisory queued - the notification thread is sending it...")

    # ---- simple rule-based question answering (string handling)
    INTENTS = {
        "fert": ("fert", "urea", "khat", "npk", "potash", "dap", "nutrient", "खत", "खाद"),
        "rain": ("rain", "paus", "baarish", "barish", "weather", "पाऊस", "बारिश", "मौसम"),
        "yield": ("yield", "tonne", "ton", "production", "utpadan", "उत्पादन", "income"),
        "stress": ("stress", "wilt", "dry", "yellow", "roll", "सूख"),
        "water": ("water", "irrigat", "pani", "paani", "pump", "पाणी", "पानी", "सिंचाई"),
    }

    def answer(self):
        q = " ".join(self.question.get().lower().split())
        if not q:
            return
        plots = [p for p in self.farm.plots if p.name.lower() in q
                 or any(word in q for word in p.name.lower().split() if len(word) > 4)] or self.farm.plots
        intent = next((name for name, words in self.INTENTS.items() if any(w in q for w in words)), None)
        w = self.weather
        if intent == "water":
            recs = [self.app.adv["weather"].analyze(p, w) for p in plots]
            text = "\n".join(advice_to_message(r, self.pv["language"].get(), self.farm.farmer.name) for r in recs)
        elif intent == "fert":
            text = "\n".join(f"{p.name}: {self.app.adv['fert'].headline(self.app.adv['fert'].analyze(p, w))}" for p in plots)
        elif intent == "rain":
            days = [d for d in w.all_days() if d.rain_mm > 0]
            text = ("Rain expected on: " + ", ".join(f"{d.day:%a %d %b} ({d.rain_mm} mm)" for d in days)) if days \
                else "No rain expected in the next 7 days - keep irrigating as advised."
        elif intent == "yield":
            yp = self.app.adv["yield"]
            text = "\n".join(f"{p.name}: {yp.headline(yp.analyze(p, w))}" for p in plots)
        elif intent == "stress":
            sd = self.app.adv["stress"]
            text = "\n".join(f"{p.name}: {sd.headline(sd.analyze(p, w))}" for p in plots)
        else:
            text = "I can answer about watering / irrigation, fertiliser (urea, khat), rain, water stress and yield. Mention a plot name for a specific answer."
        self.reply.configure(text=text)


# =============================================================================
# 11. Sugarcane Yield Prediction
# =============================================================================
class YieldPage(BasePage):
    title = "11. Sugarcane Yield Prediction"
    subtitle = "FAO-33 water-production function: 1 - Ya/Ym = Ky (1 - water index), Ky = 1.2 for sugarcane. Water index comes from the plot's moisture history."
    concepts = "YieldPredictor (map + lambda over readings), aggregation with sum(), formatted currency strings"

    COLS = [("plot", "Plot", 110, "w"), ("var", "Variety", 75, "w"), ("method", "Method", 60, "center"),
            ("ha", "Area ha", 60, "e"), ("pot", "Potential t/ha", 95, "e"), ("wi", "Water index", 80, "e"),
            ("pred", "Predicted t/ha", 95, "e"), ("loss", "Loss %", 60, "e"), ("cane", "Cane t", 70, "e"),
            ("sugar", "Sugar t", 65, "e"), ("rev", "Revenue ₹", 110, "e")]

    def build(self, body):
        ctrl = ttk.Frame(body)
        ctrl.pack(fill="x", pady=(0, 8))
        ttk.Label(ctrl, text="Cane price (₹ per tonne)").pack(side="left")
        self.price = tk.StringVar(value="3550")
        e = ttk.Entry(ctrl, textvariable=self.price, width=8)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda ev: self.refresh())
        ttk.Button(ctrl, text="Recalculate", command=self.refresh).pack(side="left")
        ttk.Label(ctrl, text="  (FRP 2025-26 is ₹355 per quintal = ₹3,550 per tonne; change it if your factory pays more)",
                  style="Muted.TLabel").pack(side="left")
        self.kpis = KpiRow(body, ["Expected cane", "Expected sugar", "Average yield", "Estimated revenue"])
        self.kpis.pack(fill="x", pady=(0, 8))
        frame, self.tree = make_tree(body, self.COLS, height=7)
        frame.pack(fill="x")
        self.chart = BarChart(body, title="Yield per hectare: potential vs predicted (t/ha)", font=(self.app.font, 9))
        self.chart.pack(fill="both", expand=True, pady=(10, 0))

    def refresh(self):
        try:
            price = parse_positive_float(self.price.get(), "Cane price")
        except IrrigationError as e:
            messagebox.showerror("Price", str(e))
            self.price.set("3550")
            price = 3550.0
        yp = self.app.adv["yield"]
        res = [(p, yp.analyze(p, self.weather)) for p in self.farm.plots]
        fill_tree(self.tree, [(p.plot_id, (p.name, p.variety, p.method, f"{p.area_ha:.2f}", r["potential_t_ha"],
                                           r["water_index"], r["predicted_t_ha"], r["loss_pct"], r["total_t"], r["sugar_t"],
                                           f"{r['total_t'] * price:,.0f}")) for p, r in res],
                  ["ok" if r["loss_pct"] < 10 else "plan" if r["loss_pct"] < 30 else "urgent" for _, r in res])
        cane = sum(r["total_t"] for _, r in res)
        area = sum(p.area_ha for p, _ in res) or 1
        self.kpis.update_values({"Expected cane": f"{cane:,.0f} t", "Expected sugar": f"{sum(r['sugar_t'] for _, r in res):,.1f} t",
                                 "Average yield": f"{cane / area:.0f} t/ha", "Estimated revenue": f"₹{cane * price / 1e5:,.1f} lakh"})
        self.chart.set_data([p.name for p, _ in res], [("Potential", [r["potential_t_ha"] for _, r in res], "#b8c4b0"),
                                                        ("Predicted", [r["predicted_t_ha"] for _, r in res], "#19a979")])


# =============================================================================
# 12. Integrated Smart Sugarcane Irrigation Dashboard
# =============================================================================
class IntegratedPage(BasePage):
    title = "12. Integrated Smart Sugarcane Irrigation Dashboard"
    subtitle = "Everything in one place. The plot report below loops over a LIST of different advisor objects and calls the same summary() on each - polymorphism in action."
    concepts = "all experiments together: OOP + ABC polymorphism + collections + threads + GUI + SQLite + file export | Exp 4: AIAdvisory / SensorAdvisory"

    COLS = [("plot", "Plot", 90, "w"), ("moist", "Moist.", 58, "e"), ("stress", "Stress", 68, "center"),
            ("etc", "ETc", 46, "e"), ("next", "Next irr.", 64, "center"), ("advice", "Advice", 150, "w"),
            ("yield", "t/ha", 48, "e")]

    def build(self, body):
        self.kpis = KpiRow(body, ["Plots", "Avg moisture", "Plots in stress", "Water needed today",
                                  "Unseen alerts", "Expected cane"])
        self.kpis.pack(fill="x", pady=(0, 8))
        grid = ttk.Frame(body)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=3)
        grid.columnconfigure(1, weight=2)
        grid.rowconfigure(1, weight=1)
        frame, self.tree = make_tree(grid, self.COLS, height=7)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.report())
        self.mix = BarChart(grid, title="Water needed today by plot (m³)", height=180, font=(self.app.font, 9))
        self.mix.grid(row=0, column=1, sticky="nsew")
        self.trend = LineChart(grid, title="Farm average soil moisture (%)", height=200, font=(self.app.font, 9))
        self.trend.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        rep = ttk.Frame(grid)
        rep.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        head = ttk.Frame(rep)
        head.pack(fill="x")
        ttk.Label(head, text="Plot report", style="H2.TLabel").pack(side="left")
        ttk.Button(head, text="Export farm report (.txt)", command=self.export).pack(side="right")
        self.text = tk.Text(rep, height=10, wrap="word", font=(self.app.mono, 9), relief="flat", bg="#fbfcfa", padx=8, pady=6)
        self.text.pack(fill="both", expand=True)

    def refresh(self):
        w, plots = self.weather, self.farm.plots
        adv = self.app.adv
        recs = self.app.recommendations()
        stress = {p.plot_id: adv["stress"].analyze(p, w) for p in plots}
        yields = {p.plot_id: adv["yield"].analyze(p, w) for p in plots}
        water = {r["plot_id"]: r["volume_l"] for r in recs if r["priority"] <= 2}
        rows, tags = [], []
        for p, r in zip(plots, recs):
            nxt = adv["next"].analyze(p, w)
            rows.append((p.plot_id, (p.name, f"{p.current_moisture:.1f}%", stress[p.plot_id]["level"],
                                     adv["water"].analyze(p, w)["etc_mm"],
                                     "TODAY" if nxt["days_left"] == 0 else f"{nxt['next_date']:%d %b}",
                                     r["action"], yields[p.plot_id]["predicted_t_ha"])))
            tags.append(stress[p.plot_id]["level"])
        fill_tree(self.tree, rows, tags)
        in_stress = sum(1 for s in stress.values() if s["level"] != "NORMAL")
        self.kpis.update_values({
            "Plots": len(plots), "Avg moisture": f"{an.average_moisture(plots)}%",
            "Plots in stress": in_stress, "Water needed today": f"{sum(water.values()) / 1000:,.0f} m³",
            "Unseen alerts": len(self.app.db.recent_alerts(500, unack_only=True)),
            "Expected cane": f"{sum(y['total_t'] for y in yields.values()):,.0f} t"})
        self.kpis.cards["Plots in stress"].value.configure(foreground="#c62828" if in_stress else GREEN)
        self.mix.set_data([p.name for p in plots], [("m3", [round(water.get(p.plot_id, 0) / 1000, 1) for p in plots], None)],
                          bar_colors=[StressDetector.COLORS[stress[p.plot_id]["level"]] for p in plots])
        series = [self.app.history.get(p.plot_id)[-40:] for p in plots]
        n = min((len(s) for s in series), default=0)
        avg = [round(sum(s[-n:][i] for s in series) / len(series), 2) for i in range(n)] if n else []
        self.trend.set_data([("Farm average", avg, "#2a78d6")], unit="%")
        if not self.tree.selection() and plots:
            self.tree.selection_set(str(plots[0].plot_id))
        self.report()

    def plot_report(self, plot):
        lines = [f"{plot.name} - {plot.method}, {plot.stage}, {plot.current_moisture:.1f}% moisture"]
        for advisor in self.app.advisor_list:          # <-- polymorphism
            lines.append("  " + advisor.summary(plot, self.weather))
        # my Exp 4 classes: same get_advisory() call, different class -> different answer
        temp = plot.latest_reading.temperature if plot.latest_reading else self.weather.today().tmax
        m = round(plot.current_moisture, 1)
        my_advisories = [AIAdvisory("Sugarcane", m, temp), SensorAdvisory("Sugarcane", m, temp)]
        lines.append("  Exp 4 (IrrigationAdvisory ABC):")
        for advisory in my_advisories:
            lines.append("    " + advisory.get_advisory())
        return "\n".join(lines)

    def report(self):
        plot = self.selected_plot(self.tree)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.plot_report(plot) if plot else "Select a plot to see every advisor's view of it.")
        self.text.configure(state="disabled")

    def export(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"farm_report_{date.today()}.txt",
                                            filetypes=[("Text file", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"SMART SUGARCANE IRRIGATION REPORT - {datetime.now():%d %b %Y %H:%M}\n")
                fh.write(f"{self.farm}\n{'=' * 78}\n\n")
                for p in self.farm.plots:
                    fh.write(self.plot_report(p) + "\n\n")
        except OSError as e:
            messagebox.showerror("Export failed", str(e))
            return
        self.app.set_status(f"Report saved to {path}")


# =============================================================================
# 13. My lab programs (Exp 1 - 8)
# =============================================================================
class LabProgramsPage(BasePage):
    title = "My Lab Programs (Exp 1 - 8)"
    subtitle = ("Runs each of my OOP-PY lab programs exactly as submitted and shows its output. "
                "The right side says where the same code is used inside the 12 scenarios.")
    concepts = "every experiment: classes, constructors + lists, strings + inheritance, ABC + polymorphism, "\
               "exceptions + modules + threads, collections + functional, Tkinter Canvas, SQLite"

    LABS = [
        ("Exp 1", "Develop Python Classes and Objects", "lab/exp1_classes.py",
         "Page 1 (Farm & Plot Monitoring): select a plot - an IrrigationSystem object is made from its live "
         "moisture and temperature, and crop_info() (class method), sensor_status() (static method) and "
         "irrigation_advice() (instance method) are shown in Plot details."),
        ("Exp 2", "Implement Constructors and Lists", "lab/exp2_records.py",
         "Page 2 → '30-day log (Exp 2)' tab: the list of 30 IrrigationRecord objects with append(), update "
         "(list[index].attribute = value), remove(), pop() and search buttons."),
        ("Exp 3", "String Handling and Inheritance", "lab/exp3_inheritance.py",
         "Page 6: 'SmartFarm (Exp 3)' column uses SmartFarm(WeatherData, SoilData) - multiple inheritance - "
         "with each plot's moisture and today's rain.  Page 7: every stress tile shows CropHealthAnalyzer "
         "(Sensor → SoilSensor → CropHealthAnalyzer, multilevel) result."),
        ("Exp 4", "Abstract Classes and Polymorphism", "lab/exp4_abstract.py",
         "Page 12 (Integrated): the plot report puts AIAdvisory and SensorAdvisory objects in a list and calls "
         "get_advisory() on each - the same call gives different answers (runtime polymorphism)."),
        ("Exp 5", "Exception Handling, Modules and Multithreading", "lab/sensor.py, lab/recommendation.py, lab/exp5_threads.py",
         "Page 5: 'Read selected plot with 3 threads (Exp 5)' reads soil moisture, temperature and humidity in "
         "3 threads with read_sensor() and gives recommend()'s answer. The whole project is also split into "
         "modules, and the live sensors / SMS sender run as background threads."),
        ("Exp 6", "Python Collections and Functional Programming", "lab_logic.py",
         "Page 2 → 'Reading analysis (Exp 6)' tab: list, tuple, dict, set + map / filter / reduce / lambda "
         "with my exact output format; can also run on a plot's last 5 live readings."),
        ("Exp 7", "GUI-Based Dashboard (Tkinter Canvas)", "charts.py (draw_exp7_logo) + page 5",
         "Start-up screen and header: my canvas logo (oval, lines, polygon, text, rectangle).  Page 5: my "
         "'Generate Irrigation Recommendation' form.  The whole app is Tkinter."),
        ("Exp 8", "Database-Driven System Using SQLite", "database.py",
         "Page 2 → 'Sensor records - SQLite (Exp 8)' tab: Sensor_Data and Irrigation_Advisory with the 50 "
         "records and my 7 queries (+8 more). The rest of the app also stores plots, readings, alerts and "
         "SMS in SQLite."),
    ]

    def build(self, body):
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        self.choice = tk.IntVar(value=0)
        for i, (num, title, _f, _w) in enumerate(self.LABS):
            ttk.Radiobutton(left, text=f"{num}  {title}", value=i, variable=self.choice,
                            command=self.show).pack(anchor="w", pady=3)
        ttk.Button(left, text="\u25b6 Run my program", style="Accent.TButton",
                   command=self.run).pack(fill="x", pady=(14, 4))
        ttk.Button(left, text="Show my Exp 7 logo", command=lambda: self.app.show_splash(4000)).pack(fill="x")

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self.head = ttk.Label(right, text="", style="H2.TLabel")
        self.head.pack(anchor="w")
        self.file_label = ttk.Label(right, text="", style="Muted.TLabel")
        self.file_label.pack(anchor="w")
        self.where = ttk.Label(right, text="", style="Info.TLabel", wraplength=660, justify="left", padding=8)
        self.where.pack(fill="x", pady=(6, 8))
        ttk.Label(right, text="Program output", style="H2.TLabel").pack(anchor="w")
        self.console = tk.Text(right, font=(self.app.mono, 10), bg="#1e1e1e", fg="#d4d4d4",
                               insertbackground="white", relief="flat", padx=10, pady=8)
        self.console.pack(fill="both", expand=True, pady=(4, 0))
        self.show()

    def refresh(self):
        pass                                             # nothing live on this page

    def show(self):
        num, title, files, where = self.LABS[self.choice.get()]
        self.head.configure(text=f"{num}: {title}")
        self.file_label.configure(text=f"Code: {files}")
        self.where.configure(text="Used in the dashboard:  " + where)
        self._write("Click 'Run my program' to run it.")

    def _write(self, text):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.insert("1.0", text)
        self.console.configure(state="disabled")

    def run(self):
        from lab import exp1_classes, exp2_records, exp3_inheritance, exp4_abstract
        i = self.choice.get()
        try:
            if i == 0:
                self._write(capture_output(exp1_classes.run_demo))
            elif i == 1:
                self._write(capture_output(exp2_records.run_demo))
            elif i == 2:
                self._write(capture_output(exp3_inheritance.run_demo))
            elif i == 3:
                self._write(capture_output(exp4_abstract.run_demo))
            elif i == 4:
                self._run_exp5()
            elif i == 5:
                r = sugarcane_advisory("FARM101", [28, 32, 25, 30, 26], 36, 48, 2)
                self._write("Input: Farm ID FARM101, readings 28,32,25,30,26, 36 °C, 48 %, 2 mm\n\n"
                            + format_advisory_report(r) + "\n\n" + format_collections(r))
            elif i == 6:
                self._write("My Exp 7 logo is drawn on a Canvas with create_oval (sun), create_line (stem, "
                            "leaves), create_polygon (water drop), create_text and create_rectangle.\n\n"
                            "The logo window is opening now. The Exp 7 recommendation form is on page 5.")
                self.app.show_splash(4000)
            else:
                self._write(self._exp8_output())
        except Exception as e:                       # show any error in the console instead of crashing
            self._write(f"Error while running: {type(e).__name__}: {e}")

    def _run_exp5(self):
        lines = []
        self._write("Starting 3 sensor threads (each one sleeps 1 second, like my sensor.py)...")

        def log(*parts):
            lines.append(" ".join(str(x) for x in parts))

        def worker():
            data, result = monitor_all(log=log)
            lines.extend(["", "AI Irrigation Advisory", result, "",
                          "Exception handling test - asking for a sensor that does not exist:"])
            monitor_all(delay=0, sensors=("rainfall",), log=log)
            lines.append("<done>")

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, lambda: self._wait(lines))

    def _wait(self, lines):
        if not lines or lines[-1] != "<done>":
            self.after(150, lambda: self._wait(lines))
            return
        self._write("\n".join(lines[:-1]))

    def _exp8_output(self):
        db = self.app.db
        out = ["Database and tables created successfully.", "50 records inserted into both tables.", ""]
        for title, sql in EXP8_QUERIES[:7]:
            _cols, rows = db.run_select(sql)
            shown = rows if len(rows) <= 15 else rows[:15] + [f"... ({len(rows)} rows)"]
            out += [title + ":", str(shown), ""]
        return "\n".join(out)


PAGES = [FarmPage, MoisturePage, WaterRequirementPage, NextIrrigationPage, RecommendationPage, WeatherPage,
         StressPage, PumpPage, FertigationPage, AdvisoryPage, YieldPage, IntegratedPage, LabProgramsPage]
