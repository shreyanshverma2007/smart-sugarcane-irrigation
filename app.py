"""
app.py
------
Main window of the Smart Sugarcane Irrigation system (Exp 7 : GUI).

Layout:  header (farm, clock, simulation controls)
         left sidebar with the 12 scenarios | page area
         status bar

Threads (Exp 5) send events through self.events (queue.Queue); poll_events()
runs every 400 ms on the Tk main loop and applies them safely.
"""
import queue
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import messagebox, ttk

from advisors import (LEVEL_RANK, FertigationAdvisor, IrrigationAdvisor, NextIrrigationAdvisor,
                      PumpScheduler, StressDetector, WaterRequirementAdvisor, WeatherAwareAdvisor,
                      YieldPredictor)
from analytics import MoistureHistory
from charts import draw_exp7_logo
from database import Database
from exceptions import IrrigationError
from pages import PAGES
from services import NotificationService, SensorSimulator, compose_message
from weather import WeatherService

BG = "#f4f6f2"
SIDEBAR = "#1b3a1f"
SIDEBAR_ACTIVE = "#2e7d32"
ACCENT = "#2e7d32"

NAV_LABELS = ["Farm & Plot Monitoring", "Soil Moisture Monitoring", "Crop Water Requirement",
              "Next Irrigation Date", "Smart Recommendation", "Weather-Aware Advisory",
              "Water Stress Alerts", "Pump Scheduling", "Fertigation", "Farmer Advisory & SMS",
              "Yield Prediction", "Integrated Dashboard", "My Lab Programs 1-8"]


def pick_font(root, choices):
    available = set(tkfont.families(root))
    return next((f for f in choices if f in available), "TkDefaultFont")


class App(tk.Tk):
    def __init__(self, db_path="sugarcane.db"):
        super().__init__()
        self.title("Smart Sugarcane Irrigation Advisory System")
        self.geometry("1366x800")
        self.minsize(1100, 680)
        self.configure(bg=BG)
        self.font = pick_font(self, ["Segoe UI", "Noto Sans", "Helvetica Neue", "DejaVu Sans", "Arial"])
        self.mono = pick_font(self, ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"])
        self._style()

        # ---- data layer
        self.db = Database(db_path)
        self.db.seed_demo_data()
        self.db.seed_exp8_data()                       # 50 records from my Exp 8
        self.farm = self.db.load_farm()
        self.weather = WeatherService()
        self.history = MoistureHistory(maxlen=120)
        for plot in self.farm.plots:
            for r in plot.readings:
                self.history.push(plot.plot_id, r.moisture)

        # ---- advisors (one object per scenario)
        self.adv = {
            "water": WaterRequirementAdvisor(), "next": NextIrrigationAdvisor(),
            "basic": IrrigationAdvisor(), "weather": WeatherAwareAdvisor(),
            "stress": StressDetector(), "fert": FertigationAdvisor(), "yield": YieldPredictor(),
        }
        # a LIST of different Advisor objects -> used polymorphically
        self.advisor_list = [self.adv[k] for k in ("stress", "water", "next", "weather", "fert", "yield")]
        self.scheduler = PumpScheduler()
        self.last_level = {p.plot_id: self.adv["stress"].analyze(p, self.weather)["level"] for p in self.farm.plots}

        # ---- threads
        self.events = queue.Queue()
        self.sensor = SensorSimulator(self.farm, self.weather, self.db, self.events, interval=2.0, speed=1)
        self.notifier = NotificationService(self.db, self.events)

        self._build_layout()
        self.show_splash()
        self.sensor.start()
        self.notifier.start()
        self.show_page(0)
        self.after(400, self.poll_events)
        self.after(1000, self.tick_clock)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ styling
    def _style(self):
        s = ttk.Style(self)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        f = self.font
        s.configure(".", background=BG, font=(f, 10))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground="#1f2933")
        s.configure("H1.TLabel", font=(f, 17, "bold"), foreground="#1b3a1f")
        s.configure("H2.TLabel", font=(f, 11, "bold"))
        s.configure("Muted.TLabel", foreground="#5b6770", font=(f, 9))
        s.configure("Concept.TLabel", foreground="#6a3fb5", font=(f, 9, "italic"))
        s.configure("Info.TLabel", background="#e8f1e6", foreground="#1b3a1f")
        s.configure("Card.TFrame", background="white", relief="solid", borderwidth=1)
        s.configure("Card.TLabel", background="white", font=(f, 9), foreground="#4b5563")
        s.configure("CardBold.TLabel", background="white", font=(f, 9, "bold"))
        s.configure("CardBig.TLabel", background="white", font=(f, 13, "bold"))
        s.configure("KpiValue.TLabel", background="white", font=(f, 18, "bold"))
        s.configure("KpiCaption.TLabel", background="white", foreground="#5b6770", font=(f, 9))
        s.configure("TLabelframe", background=BG)
        s.configure("TLabelframe.Label", background=BG, font=(f, 10, "bold"), foreground="#1b3a1f")
        s.configure("Treeview", rowheight=24, font=(f, 9), fieldbackground="white")
        s.configure("Treeview.Heading", font=(f, 9, "bold"), background="#e3e9df")
        s.map("Treeview", background=[("selected", "#2a78d6")], foreground=[("selected", "white")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white", font=(f, 10, "bold"))
        s.map("Accent.TButton", background=[("active", "#1b5e20")])
        s.configure("TCheckbutton", background=BG)
        s.configure("TRadiobutton", background=BG)

    # ------------------------------------------------------------------ layout
    def _build_layout(self):
        header = tk.Frame(self, bg="white", height=56, highlightthickness=1, highlightbackground="#dfe3dc")
        header.pack(fill="x")
        logo = tk.Canvas(header, width=46, height=46, bg="white", highlightthickness=0)
        logo.pack(side="left", padx=(12, 0), pady=4)
        draw_exp7_logo(logo, full=False, scale=0.3)          # my Exp 7 logo, made smaller
        logo.move("logo", -8, -6)
        tk.Label(header, text="Smart Sugarcane Irrigation", bg="white", fg="#1b3a1f",
                 font=(self.font, 15, "bold")).pack(side="left", padx=(6, 16), pady=10)
        self.farm_label = tk.Label(header, text="", bg="white", fg="#5b6770", font=(self.font, 10))
        self.farm_label.pack(side="left", padx=8)
        self.clock = tk.Label(header, text="", bg="white", fg="#1f2933", font=(self.font, 10, "bold"))
        self.clock.pack(side="right", padx=16)
        self.pause_btn = ttk.Button(header, text="Pause sensors", command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=4)
        ttk.Button(header, text="\u21ba Reset demo", command=self.reset_demo).pack(side="right", padx=4)
        self.speed = tk.IntVar(value=self.sensor.speed)
        tk.Scale(header, from_=1, to=24, orient="horizontal", variable=self.speed, length=100, showvalue=True,
                 bg="white", highlightthickness=0, label="Sim hours/tick", font=(self.font, 8),
                 command=lambda v: setattr(self.sensor, "speed", int(v))).pack(side="right", padx=6)
        self.auto_notify = tk.BooleanVar(value=True)
        tk.Checkbutton(header, text="Auto-SMS", variable=self.auto_notify, bg="white",
                       font=(self.font, 9)).pack(side="right", padx=6)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=SIDEBAR, width=230)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Label(nav, text="SCENARIOS", bg=SIDEBAR, fg="#9fbf9f", font=(self.font, 8, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        self.nav_buttons = []
        for i, label in enumerate(NAV_LABELS):
            b = tk.Button(nav, text=f"{i + 1:>2}.  {label}", anchor="w", relief="flat", bd=0, padx=14, pady=7,
                          bg=SIDEBAR, fg="#e8f5e9", activebackground=SIDEBAR_ACTIVE, activeforeground="white",
                          font=(self.font, 10), cursor="hand2", command=lambda i=i: self.show_page(i))
            b.pack(fill="x")
            self.nav_buttons.append(b)
        self.alert_badge = tk.Label(nav, text="", bg=SIDEBAR, fg="#ffcdd2", font=(self.font, 9), justify="left")
        self.alert_badge.pack(side="bottom", anchor="w", padx=16, pady=(4, 12))
        self.sensor_state = tk.Label(nav, text="\u25cf Sensors live", bg=SIDEBAR, fg="#a5d6a7", font=(self.font, 9, "bold"))
        self.sensor_state.pack(side="bottom", anchor="w", padx=16)

        self.container = ttk.Frame(body)
        self.container.pack(side="left", fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        self.pages = []
        for PageClass in PAGES:
            page = PageClass(self.container, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages.append(page)

        self.status = tk.Label(self, text="Ready", anchor="w", bg="#e3e9df", fg="#1f2933", font=(self.font, 9), padx=10)
        self.status.pack(fill="x", side="bottom")
        self.update_header()

    def show_splash(self, ms=2500):
        """Start-up screen with the full logo from my Exp 7 (Tkinter Canvas shapes)."""
        self.update_idletasks()
        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.configure(bg="white", highlightthickness=2, highlightbackground="#2e7d32")
        c = tk.Canvas(splash, width=820, height=230, bg="white", highlightthickness=0)
        c.pack(padx=10, pady=(10, 0))
        draw_exp7_logo(c, full=True)
        tk.Label(splash, text="Loading sensors, weather and database...", bg="white", fg="#5b6770",
                 font=(self.font, 10)).pack(pady=(0, 10))
        splash.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - splash.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - splash.winfo_height()) // 2
        splash.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        splash.lift()
        splash.bind("<Button-1>", lambda e: splash.destroy())
        self.after(ms, splash.destroy)

    # ------------------------------------------------------------------ navigation
    def show_page(self, index):
        self.current = index
        for i, b in enumerate(self.nav_buttons):
            b.configure(bg=SIDEBAR_ACTIVE if i == index else SIDEBAR,
                        font=(self.font, 10, "bold" if i == index else "normal"))
        page = self.pages[index]
        page.tkraise()
        self.safe_refresh(page)

    def safe_refresh(self, page):
        try:
            page.refresh()
        except IrrigationError as e:
            self.set_status(f"Error: {e}")

    def refresh_all(self):
        self.update_header()
        self.safe_refresh(self.pages[self.current])

    def update_header(self):
        f = self.farm
        self.farm_label.configure(text=f"{f.name}  \u00b7  {len(f)} plots")
        unseen = self.db.recent_alerts(500, unack_only=True)
        self.alert_badge.configure(text=f"⚠ {len(unseen)} unseen alert(s)" if unseen else "✓ No unseen alerts",
                                   fg="#ffcdd2" if unseen else "#a5d6a7")

    def tick_clock(self):
        self.clock.configure(text=datetime.now().strftime("%a %d %b %Y  %H:%M:%S"))
        self.after(1000, self.tick_clock)

    def set_status(self, text):
        self.status.configure(text=f"{datetime.now():%H:%M:%S}  {text}")

    # ------------------------------------------------------------------ shared actions
    def recommendations(self):
        return [self.adv["weather"].analyze(p, self.weather) for p in self.farm.plots]

    def reload_farm(self):
        """Re-read plots from SQLite. The list is changed IN PLACE so the sensor thread sees it."""
        fresh = self.db.load_farm(self.farm.farm_id)
        self.farm.name = fresh.name
        self.farm.farmer = fresh.farmer
        self.farm.plots[:] = fresh.plots
        for p in self.farm.plots:
            if not self.history.get(p.plot_id):
                for r in p.readings:
                    self.history.push(p.plot_id, r.moisture)
            self.last_level.setdefault(p.plot_id, "NORMAL")
        self.refresh_all()

    def start_irrigation(self, plot, hours, volume, source="Manual"):
        if plot is None or hours <= 0:
            return
        self.sensor.start_pump(plot.plot_id, hours)
        self.db.log_irrigation(plot.plot_id, round(hours, 2), round(volume), source)
        self.set_status(f"Pump started for '{plot.name}' - {hours:.1f} h, {volume:,.0f} litres ({source}).")
        self.refresh_all()

    def notify(self, message, channel=None):
        farmer = self.farm.farmer
        channel = channel or self.pages[9].pv["channel"].get() or "SMS"
        self.notifier.send(farmer.farmer_id, channel, farmer.language, message)

    def check_stress(self):
        """Create an alert whenever a plot's stress level becomes WORSE."""
        det = self.adv["stress"]
        for p in self.farm.plots:
            r = det.analyze(p, self.weather)
            old = self.last_level.get(p.plot_id, "NORMAL")
            if LEVEL_RANK[r["level"]] > LEVEL_RANK[old]:
                self.db.add_alert(p.plot_id, r["level"], r["message"])
                self.set_status(f"ALERT: {p.name} is now {r['level']}")
                if self.auto_notify.get():
                    f = self.farm.farmer
                    self.notify(compose_message("stress", f.language, f.name, plot=p.name,
                                                level=r["level"], moisture=round(r["moisture"], 1)))
            self.last_level[p.plot_id] = r["level"]

    # ------------------------------------------------------------------ thread events
    def poll_events(self):
        got_readings = False
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "readings":
                    for reading in event[1]:
                        plot = self.farm.get_plot(reading.plot_id)
                        if plot:
                            plot.add_reading(reading)
                            self.history.push(plot.plot_id, reading.moisture)
                    got_readings = True
                elif kind == "sensor_error":
                    plot = self.farm.get_plot(event[1])
                    self.db.add_alert(event[1], "INFO", event[2] + " - reading skipped")
                    self.set_status(f"Sensor warning: {event[2]}")
                elif kind == "pump_off":
                    plot = self.farm.get_plot(event[1])
                    self.set_status(f"Irrigation finished for '{plot.name if plot else event[1]}'.")
                elif kind == "notification_sent":
                    self.set_status(f"{event[1]} sent: {event[2][:90]}...")
                    if self.current == 9:
                        self.safe_refresh(self.pages[9])
                elif kind == "db_error":
                    self.set_status(f"Database error: {event[2]}")
        except queue.Empty:
            pass
        if got_readings:
            self.check_stress()
            self.refresh_all()
        self.after(400, self.poll_events)

    def toggle_pause(self):
        paused = not self.sensor.paused
        self.sensor.pause(paused)
        self.pause_btn.configure(text="Resume sensors" if paused else "Pause sensors")
        self.sensor_state.configure(text="● Sensors paused" if paused else "● Sensors live",
                                    fg="#ffe082" if paused else "#a5d6a7")

    def reset_demo(self):
        """Put every plot back to a different moisture level, clear alerts/SMS/pumps and the forecast."""
        if not messagebox.askyesno("Reset demo", "Give every plot fresh, different moisture levels?\n"
                                   "(Clears alerts, SMS log, irrigation history and running pumps.)"):
            return
        was_paused = self.sensor.paused
        self.sensor.pause(True)
        with self.sensor._lock:
            self.sensor._pumps.clear()
        while not self.events.empty():           # drop readings made before the reset
            self.events.get_nowait()
        self.db.reset_demo_readings()
        self.weather.regenerate()
        self.history = MoistureHistory(maxlen=120)
        fresh = self.db.load_farm(self.farm.farm_id)
        self.farm.plots[:] = fresh.plots
        for p in self.farm.plots:
            for r in p.readings:
                self.history.push(p.plot_id, r.moisture)
        self.last_level = {p.plot_id: self.adv["stress"].analyze(p, self.weather)["level"] for p in self.farm.plots}
        self.sensor.pause(was_paused)
        self.set_status("Demo reset - every plot now has a different moisture level.")
        self.refresh_all()

    def on_close(self):
        self.sensor.stop()
        self.notifier.stop()
        self.sensor.join(timeout=2)
        self.notifier.join(timeout=2)
        self.db.close()
        self.destroy()


def main():
    try:
        app = App()
    except IrrigationError as e:
        messagebox.showerror("Startup error", str(e))
        return
    app.mainloop()


if __name__ == "__main__":
    main()
