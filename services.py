"""
services.py
-----------
Exp 5 : Multithreading
    SensorSimulator      - background thread that "reads" soil-moisture sensors
    NotificationService  - background thread that sends farmer notifications

Threads never touch Tkinter widgets directly (Tkinter is not thread-safe).
They put messages into a queue.Queue, and the GUI picks them up with
root.after(). Shared state is protected with threading.Lock, and
threading.Event is used to stop the threads cleanly.

Scenario 10 : Farmer-Friendly AI Advisory & Notification System
    Messages are generated in English, Hindi or Marathi.
"""
import queue
import random
import threading
import time
from datetime import datetime

from exceptions import DatabaseError, SensorError
from models import SensorReading

# --------------------------------------------------------------------------
# Message templates (string formatting)
# --------------------------------------------------------------------------
TEMPLATES = {
    "English": {
        "greet": "Namaskar {first}ji",
        "irrigate": "{greet}, soil moisture in '{plot}' is {moisture}%. Please irrigate for {hours} hours today ({litres} litres).",
        "stress": "ALERT {greet}! '{plot}' has {level} water stress. Moisture is {moisture}%. Irrigate as soon as possible.",
        "rain": "{greet}, about {rain} mm rain is expected in the next 48 hours. You can postpone irrigation of '{plot}'.",
        "ok": "{greet}, '{plot}' has enough water. Next irrigation around {date}.",
        "fertigation": "{greet}, for '{plot}' this week give Urea {urea} kg, 12:61:00 {map} kg and MOP {mop} kg.",
    },
    "Hindi": {
        "greet": "नमस्ते {first}जी",
        "irrigate": "{greet}, '{plot}' में मिट्टी की नमी {moisture}% है। आज {hours} घंटे सिंचाई करें ({litres} लीटर)।",
        "stress": "सावधान {greet}! '{plot}' में पानी की कमी ({level})। नमी {moisture}% है। जल्दी सिंचाई करें।",
        "rain": "{greet}, अगले 48 घंटों में लगभग {rain} मिमी बारिश की संभावना है। '{plot}' की सिंचाई टाल सकते हैं।",
        "ok": "{greet}, '{plot}' में पर्याप्त पानी है। अगली सिंचाई लगभग {date} को।",
        "fertigation": "{greet}, इस हफ्ते '{plot}' में यूरिया {urea} किलो, 12:61:00 {map} किलो और MOP {mop} किलो दें।",
    },
    "Marathi": {
        "greet": "नमस्कार {first}जी",
        "irrigate": "{greet}, '{plot}' मध्ये मातीतील ओलावा {moisture}% आहे. आज {hours} तास पाणी द्या ({litres} लिटर).",
        "stress": "सावधान {greet}! '{plot}' मध्ये पाण्याचा ताण ({level}). ओलावा {moisture}% आहे. लवकर पाणी द्या.",
        "rain": "{greet}, पुढील 48 तासांत सुमारे {rain} मिमी पाऊस अपेक्षित आहे. '{plot}' चे पाणी पुढे ढकलू शकता.",
        "ok": "{greet}, '{plot}' मध्ये पुरेसे पाणी आहे. पुढील पाणी सुमारे {date} रोजी.",
        "fertigation": "{greet}, या आठवड्यात '{plot}' साठी युरिया {urea} किलो, 12:61:00 {map} किलो आणि MOP {mop} किलो द्या.",
    },
}
LANGUAGES = list(TEMPLATES)
CHANNELS = ["SMS", "WhatsApp", "App"]


def compose_message(kind, language, farmer_name, **values):
    """Fill a template. Falls back to English if a language/kind is missing."""
    texts = TEMPLATES.get(language, TEMPLATES["English"])
    first = farmer_name.split()[0] if farmer_name.strip() else "Farmer"
    greet = texts["greet"].format(first=first)
    template = texts.get(kind) or TEMPLATES["English"][kind]
    try:
        return template.format(greet=greet, **values)
    except KeyError as missing:
        return f"{greet}, update for '{values.get('plot', 'your plot')}' (missing value {missing})."


def advice_to_message(rec, language, farmer_name):
    """Convert an advisor recommendation dict into the right template."""
    plot = rec["plot_name"]
    if rec["action"].startswith("POSTPONE"):
        return compose_message("rain", language, farmer_name, plot=plot, rain=rec.get("rain_48h", 0))
    if rec["priority"] <= 2:
        return compose_message("irrigate", language, farmer_name, plot=plot,
                               moisture=round(rec["moisture"], 1),
                               hours=round(rec["duration_h"], 1), litres=f"{rec['volume_l']:,}")
    return compose_message("ok", language, farmer_name, plot=plot,
                           date=rec["next_date"].strftime("%d %b"))


# --------------------------------------------------------------------------
# Thread 1 : sensor simulator
# --------------------------------------------------------------------------
class SensorSimulator(threading.Thread):
    SIM_HOURS_PER_TICK = 1

    def __init__(self, farm, weather, db, out_queue, interval=2.0, speed=3):
        super().__init__(daemon=True, name="SensorThread")
        self.farm = farm
        self.weather = weather
        self.db = db
        self.out = out_queue
        self.interval = interval
        self.speed = speed
        self.failure_rate = 0.01
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._lock = threading.Lock()
        self._pumps = {}            # plot_id -> remaining simulated hours

    # ---- control methods called from the GUI thread
    def stop(self):
        self._stop_event.set()

    def pause(self, paused=True):
        if paused:
            self._pause_event.set()
        else:
            self._pause_event.clear()

    @property
    def paused(self):
        return self._pause_event.is_set()

    def start_pump(self, plot_id, hours):
        with self._lock:
            self._pumps[plot_id] = self._pumps.get(plot_id, 0) + hours

    def pumps_running(self):
        with self._lock:
            return dict(self._pumps)

    # ---- one sensor reading
    def _read(self, plot, today):
        if random.random() < self.failure_rate:
            raise SensorError(plot.plot_id, f"No response from sensor in '{plot.name}'")
        hrs = self.SIM_HOURS_PER_TICK * self.speed
        etc = self.weather.et0(today) * plot.kc * hrs / 24
        moisture = plot.current_moisture - etc / plot.root_depth_mm * 100

        with self._lock:
            pump_left = self._pumps.get(plot.plot_id, 0)
            if pump_left > 0:
                run = min(hrs, pump_left)
                mm = plot.pump_lph * run * plot.efficiency / (plot.area_m2 * plot.wetted_fraction)
                moisture += mm / plot.root_depth_mm * 100
                self._pumps[plot.plot_id] = pump_left - run
                if self._pumps[plot.plot_id] <= 0:
                    del self._pumps[plot.plot_id]
                    self.out.put(("pump_off", plot.plot_id))

        moisture = min(plot.field_capacity + 2, max(plot.wilting_point - 3,
                                                     moisture + random.uniform(-0.15, 0.15)))
        hour = datetime.now().hour
        temp = today.tmin + (today.tmax - today.tmin) * max(0.0, 1 - abs(hour - 14) / 9)
        return SensorReading(plot.plot_id, moisture, temp + random.uniform(-0.8, 0.8),
                             today.humidity + random.uniform(-4, 4))

    def run(self):
        while not self._stop_event.is_set():
            if not self._pause_event.is_set():
                today = self.weather.today()
                batch = []
                for plot in list(self.farm.plots):          # copy: GUI may edit list
                    try:
                        reading = self._read(plot, today)
                        self.db.add_reading(reading)
                        batch.append(reading)
                    except SensorError as e:
                        self.out.put(("sensor_error", e.plot_id, str(e)))
                    except DatabaseError as e:
                        self.out.put(("db_error", None, str(e)))
                if batch:
                    self.out.put(("readings", batch))
            self._stop_event.wait(self.interval)            # sleeps but wakes on stop()


# --------------------------------------------------------------------------
# Thread 2 : notification sender
# --------------------------------------------------------------------------
class NotificationService(threading.Thread):
    """Producer-consumer: GUI produces jobs, this thread consumes and 'sends' them."""

    def __init__(self, db, out_queue, send_delay=0.4):
        super().__init__(daemon=True, name="NotificationThread")
        self.db = db
        self.out = out_queue
        self.jobs = queue.Queue()
        self.send_delay = send_delay
        self._stop_event = threading.Event()
        self.sent_count = 0

    def send(self, farmer_id, channel, language, message):
        self.jobs.put((farmer_id, channel, language, message))

    def stop(self):
        self._stop_event.set()
        self.jobs.put(None)                     # wake the thread up

    def run(self):
        while not self._stop_event.is_set():
            job = self.jobs.get()
            if job is None:
                break
            farmer_id, channel, language, message = job
            time.sleep(self.send_delay)        # pretend we are calling an SMS gateway
            try:
                self.db.add_notification(farmer_id, channel, language, message)
                self.sent_count += 1
                self.out.put(("notification_sent", channel, message))
            except DatabaseError as e:
                self.out.put(("db_error", None, str(e)))
