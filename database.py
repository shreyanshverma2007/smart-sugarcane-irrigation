"""
database.py
-----------
Exp 8 : Database-Driven System using SQLite

Tables
    farmers, farms, plots, sensor_readings, irrigation_events, alerts, notifications
    Sensor_Data, Irrigation_Advisory   (the two tables of my Exp 8, with its 50 records)

* Uses the built-in sqlite3 module (no server needed - one .db file)
* Parameterised queries (?) everywhere -> safe from SQL injection
* One connection shared between threads, protected by a threading.Lock
* sqlite3 errors are wrapped in our own DatabaseError (Exp 5)
"""
import random
import sqlite3
import threading
from datetime import date, datetime, timedelta

from exceptions import DatabaseError
from lab_logic import classify_moisture, water_required
from models import Farm, Farmer, SensorReading, create_plot

SCHEMA = """
CREATE TABLE IF NOT EXISTS farmers (
    farmer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    phone       TEXT,
    village     TEXT,
    language    TEXT DEFAULT 'English'
);
CREATE TABLE IF NOT EXISTS farms (
    farm_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id   INTEGER NOT NULL REFERENCES farmers(farmer_id),
    name        TEXT NOT NULL,
    location    TEXT
);
CREATE TABLE IF NOT EXISTS plots (
    plot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id       INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    area_acres    REAL NOT NULL CHECK (area_acres > 0),
    soil_type     TEXT NOT NULL,
    variety       TEXT NOT NULL,
    method        TEXT NOT NULL CHECK (method IN ('Drip','Furrow','Flood')),
    planting_date TEXT NOT NULL,
    pump_lph      REAL NOT NULL DEFAULT 25000,
    UNIQUE (farm_id, name)
);
CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id     INTEGER NOT NULL REFERENCES plots(plot_id) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    moisture    REAL NOT NULL,
    temperature REAL,
    humidity    REAL
);
CREATE INDEX IF NOT EXISTS idx_readings_plot_ts ON sensor_readings(plot_id, ts);
CREATE TABLE IF NOT EXISTS irrigation_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id     INTEGER NOT NULL REFERENCES plots(plot_id) ON DELETE CASCADE,
    start_ts    TEXT NOT NULL,
    duration_h  REAL NOT NULL,
    volume_l    REAL NOT NULL,
    source      TEXT DEFAULT 'Manual'
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id     INTEGER REFERENCES plots(plot_id) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notifications (
    notif_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id   INTEGER REFERENCES farmers(farmer_id),
    ts          TEXT NOT NULL,
    channel     TEXT NOT NULL,
    language    TEXT NOT NULL,
    message     TEXT NOT NULL
);

-- ---- Exp 8 tables (same names and columns as my Exp 8) ----
CREATE TABLE IF NOT EXISTS Sensor_Data (
    sensor_id   INTEGER PRIMARY KEY,
    moisture    REAL,
    temperature REAL,
    humidity    REAL
);
CREATE TABLE IF NOT EXISTS Irrigation_Advisory (
    advisory_id    INTEGER PRIMARY KEY,
    sensor_id      INTEGER,
    recommendation TEXT,
    water_required REAL
);
"""

# The 50 sensor records from my Exp 8 (sensor_id, moisture, temperature, humidity)
EXP8_SENSOR_DATA = [
    (1, 35.5, 30.0, 65.0), (2, 42.0, 29.5, 68.0), (3, 55.0, 28.0, 70.0), (4, 62.5, 27.5, 72.0),
    (5, 38.0, 31.0, 64.0), (6, 47.5, 30.5, 66.0), (7, 58.0, 29.0, 69.0), (8, 65.0, 27.0, 74.0),
    (9, 32.5, 32.0, 62.0), (10, 44.0, 30.0, 67.0), (11, 52.5, 29.0, 71.0), (12, 68.0, 26.5, 75.0),
    (13, 36.0, 31.5, 63.0), (14, 49.0, 30.0, 68.0), (15, 57.5, 28.5, 70.0), (16, 72.0, 26.0, 77.0),
    (17, 34.5, 32.0, 61.0), (18, 45.5, 30.5, 66.0), (19, 54.0, 29.5, 69.0), (20, 63.5, 27.5, 73.0),
    (21, 39.0, 31.0, 65.0), (22, 48.5, 30.0, 67.0), (23, 59.0, 28.0, 71.0), (24, 67.5, 27.0, 74.0),
    (25, 31.0, 32.5, 60.0), (26, 43.5, 30.5, 65.0), (27, 51.0, 29.5, 68.0), (28, 61.0, 28.0, 72.0),
    (29, 37.5, 31.0, 63.0), (30, 46.0, 30.0, 66.0), (31, 56.5, 29.0, 70.0), (32, 69.0, 26.5, 76.0),
    (33, 33.0, 32.0, 61.0), (34, 41.5, 31.0, 64.0), (35, 53.5, 29.5, 69.0), (36, 64.5, 27.5, 73.0),
    (37, 35.0, 31.5, 62.0), (38, 47.0, 30.5, 67.0), (39, 58.5, 28.5, 71.0), (40, 66.0, 27.0, 75.0),
    (41, 30.5, 33.0, 59.0), (42, 44.5, 30.5, 65.0), (43, 52.0, 29.0, 68.0), (44, 60.5, 28.0, 72.0),
    (45, 38.5, 31.0, 63.0), (46, 49.5, 30.0, 67.0), (47, 55.5, 29.0, 70.0), (48, 70.0, 26.0, 76.0),
    (49, 36.5, 32.0, 62.0), (50, 45.0, 30.5, 66.0),
]

# Queries for the "Sensor Records (Exp 8)" tab. The first 7 are the ones in my Exp 8.
EXP8_QUERIES = [
    ("1. Display all sensor data", "SELECT * FROM Sensor_Data"),
    ("2. Sensors with moisture below 40", "SELECT * FROM Sensor_Data\nWHERE moisture < 40"),
    ("3. Sensors with temperature above 30", "SELECT * FROM Sensor_Data\nWHERE temperature > 30"),
    ("4. Sensor data sorted by moisture", "SELECT * FROM Sensor_Data\nORDER BY moisture ASC"),
    ("5. Count total sensor records", "SELECT COUNT(*) FROM Sensor_Data"),
    ("6. Average soil moisture", "SELECT AVG(moisture) FROM Sensor_Data"),
    ("7. Irrigation recommendations (Required)",
     "SELECT * FROM Irrigation_Advisory\nWHERE recommendation = 'Irrigation Required'"),
    ("8. Count of each recommendation (GROUP BY)",
     "SELECT recommendation, COUNT(*) AS sensors, SUM(water_required) AS total_water\n"
     "FROM Irrigation_Advisory\nGROUP BY recommendation"),
    ("9. Min / max / avg temperature",
     "SELECT MIN(temperature), MAX(temperature), ROUND(AVG(temperature), 2)\nFROM Sensor_Data"),
    ("10. Moisture BETWEEN 40 AND 60", "SELECT * FROM Sensor_Data\nWHERE moisture BETWEEN 40 AND 60"),
    ("11. Driest 5 sensors (ORDER BY + LIMIT)",
     "SELECT * FROM Sensor_Data\nORDER BY moisture ASC\nLIMIT 5"),
    ("12. Distinct recommendations", "SELECT DISTINCT recommendation FROM Irrigation_Advisory"),
    ("13. Recommendations LIKE '%Soon%'",
     "SELECT * FROM Irrigation_Advisory\nWHERE recommendation LIKE '%Soon%'"),
    ("14. Groups having more than 15 sensors (HAVING)",
     "SELECT recommendation, COUNT(*)\nFROM Irrigation_Advisory\nGROUP BY recommendation\nHAVING COUNT(*) > 15"),
    ("15. Sensor + advisory together (JOIN)",
     "SELECT s.sensor_id, s.moisture, s.temperature, a.recommendation, a.water_required\n"
     "FROM Sensor_Data s JOIN Irrigation_Advisory a ON a.sensor_id = s.sensor_id\n"
     "ORDER BY s.moisture"),
]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# Where each demo plot's moisture starts, relative to its own safe level:
#   plan in a few days, irrigate now, well watered, very dry, irrigate soon, well watered
DEMO_OFFSETS = [0.06, -0.10, 0.25, -0.32, 0.02, 0.35]


class Database:
    def __init__(self, path="sugarcane.db"):
        self.path = path
        self._lock = threading.Lock()
        try:
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row          # rows behave like dicts
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Could not open database '{path}': {e}") from e

    # ------------------------------------------------------------ helpers
    def execute(self, sql, params=()):
        """INSERT / UPDATE / DELETE. Returns the new row id."""
        with self._lock:
            try:
                cur = self.conn.execute(sql, params)
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError as e:
                self.conn.rollback()
                raise DatabaseError(f"Data rule violated: {e}") from e
            except sqlite3.Error as e:
                self.conn.rollback()
                raise DatabaseError(str(e)) from e

    def query(self, sql, params=()):
        with self._lock:
            try:
                return [dict(row) for row in self.conn.execute(sql, params).fetchall()]
            except sqlite3.Error as e:
                raise DatabaseError(str(e)) from e

    def close(self):
        with self._lock:
            self.conn.close()

    # ------------------------------------------------------------ farmer / farm
    def get_farmer(self, farmer_id=1):
        rows = self.query("SELECT * FROM farmers WHERE farmer_id = ?", (farmer_id,))
        return rows[0] if rows else None

    def update_farmer(self, farmer_id, name, phone, village, language):
        self.execute("UPDATE farmers SET name=?, phone=?, village=?, language=? WHERE farmer_id=?",
                     (name, phone, village, language, farmer_id))

    def load_farm(self, farm_id=1) -> Farm:
        """Build Farm, Farmer and Plot OBJECTS from database rows."""
        rows = self.query("""SELECT f.farm_id, f.name AS farm_name, fa.*
                             FROM farms f JOIN farmers fa ON fa.farmer_id = f.farmer_id
                             WHERE f.farm_id = ?""", (farm_id,))
        if not rows:
            raise DatabaseError("Farm not found - delete sugarcane.db to recreate demo data.")
        r = rows[0]
        farmer = Farmer(r["name"], r["phone"] or "", r["village"] or "")
        farmer.farmer_id = r["farmer_id"]
        farmer.language = r["language"]
        farm = Farm(r["farm_id"], r["farm_name"], farmer)
        for row in self.query("SELECT * FROM plots WHERE farm_id = ? ORDER BY plot_id", (farm_id,)):
            farm.plots.append(self._row_to_plot(row))
        for plot in farm.plots:
            for rd in self.get_readings(plot.plot_id, limit=200):
                plot.add_reading(SensorReading(plot.plot_id, rd["moisture"], rd["temperature"],
                                               rd["humidity"], datetime.strptime(rd["ts"], TS_FMT)))
        return farm

    @staticmethod
    def _row_to_plot(row):
        return create_plot(row["method"], plot_id=row["plot_id"], name=row["name"],
                           area_acres=row["area_acres"], soil_type=row["soil_type"],
                           variety=row["variety"], planting_date=row["planting_date"],
                           pump_lph=row["pump_lph"], farm_id=row["farm_id"])

    # ------------------------------------------------------------ plots (CRUD)
    def add_plot(self, farm_id, name, area, soil, variety, method, planting_date, pump_lph):
        plot_id = self.execute(
            """INSERT INTO plots (farm_id, name, area_acres, soil_type, variety, method,
                                  planting_date, pump_lph) VALUES (?,?,?,?,?,?,?,?)""",
            (farm_id, name, area, soil, variety, method, str(planting_date), pump_lph))
        return plot_id

    def update_plot(self, plot_id, name, area, soil, variety, method, planting_date, pump_lph):
        self.execute(
            """UPDATE plots SET name=?, area_acres=?, soil_type=?, variety=?, method=?,
                                planting_date=?, pump_lph=? WHERE plot_id=?""",
            (name, area, soil, variety, method, str(planting_date), pump_lph, plot_id))

    def delete_plot(self, plot_id):
        self.execute("DELETE FROM plots WHERE plot_id = ?", (plot_id,))

    # ------------------------------------------------------------ readings
    def add_reading(self, reading: SensorReading):
        self.execute("""INSERT INTO sensor_readings (plot_id, ts, moisture, temperature, humidity)
                        VALUES (?,?,?,?,?)""",
                     (reading.plot_id, reading.timestamp.strftime(TS_FMT), reading.moisture,
                      reading.temperature, reading.humidity))

    def get_readings(self, plot_id, limit=100):
        rows = self.query("""SELECT * FROM sensor_readings WHERE plot_id = ?
                             ORDER BY ts DESC, reading_id DESC LIMIT ?""", (plot_id, limit))
        return rows[::-1]                          # oldest first

    def daily_moisture(self, plot_id, days=7):
        since = (datetime.now() - timedelta(days=days)).strftime(TS_FMT)
        return self.query("""SELECT substr(ts,1,10) AS day, ROUND(AVG(moisture),1) AS avg_m,
                                    ROUND(MIN(moisture),1) AS min_m, ROUND(MAX(moisture),1) AS max_m
                             FROM sensor_readings WHERE plot_id = ? AND ts >= ?
                             GROUP BY day ORDER BY day""", (plot_id, since))

    # ------------------------------------------------------------ irrigation log
    def log_irrigation(self, plot_id, duration_h, volume_l, source="Manual", start=None):
        start = start or datetime.now()
        return self.execute("""INSERT INTO irrigation_events (plot_id, start_ts, duration_h, volume_l, source)
                               VALUES (?,?,?,?,?)""",
                            (plot_id, start.strftime(TS_FMT), duration_h, volume_l, source))

    def irrigation_history(self, limit=50):
        return self.query("""SELECT e.event_id, p.name AS plot, e.start_ts, e.duration_h,
                                    e.volume_l, e.source
                             FROM irrigation_events e JOIN plots p ON p.plot_id = e.plot_id
                             ORDER BY e.start_ts DESC LIMIT ?""", (limit,))

    def water_used_by_plot(self, days=30):
        since = (datetime.now() - timedelta(days=days)).strftime(TS_FMT)
        return self.query("""SELECT p.name AS plot, COUNT(e.event_id) AS events,
                                    ROUND(COALESCE(SUM(e.volume_l),0)/1000.0,1) AS m3
                             FROM plots p LEFT JOIN irrigation_events e
                                  ON e.plot_id = p.plot_id AND e.start_ts >= ?
                             GROUP BY p.plot_id ORDER BY m3 DESC""", (since,))

    def last_irrigation(self, plot_id):
        rows = self.query("""SELECT start_ts FROM irrigation_events WHERE plot_id = ?
                             ORDER BY start_ts DESC LIMIT 1""", (plot_id,))
        return rows[0]["start_ts"] if rows else None

    # ------------------------------------------------------------ alerts
    def add_alert(self, plot_id, level, message):
        return self.execute("INSERT INTO alerts (plot_id, ts, level, message) VALUES (?,?,?,?)",
                            (plot_id, datetime.now().strftime(TS_FMT), level, message))

    def recent_alerts(self, limit=100, unack_only=False):
        where = "WHERE a.acknowledged = 0" if unack_only else ""
        return self.query(f"""SELECT a.alert_id, a.ts, p.name AS plot, a.level, a.message, a.acknowledged
                              FROM alerts a LEFT JOIN plots p ON p.plot_id = a.plot_id
                              {where} ORDER BY a.ts DESC, a.alert_id DESC LIMIT ?""", (limit,))

    def acknowledge_all(self):
        self.execute("UPDATE alerts SET acknowledged = 1 WHERE acknowledged = 0")

    # ------------------------------------------------------------ notifications
    def add_notification(self, farmer_id, channel, language, message):
        return self.execute("""INSERT INTO notifications (farmer_id, ts, channel, language, message)
                               VALUES (?,?,?,?,?)""",
                            (farmer_id, datetime.now().strftime(TS_FMT), channel, language, message))

    def recent_notifications(self, limit=100):
        return self.query("SELECT * FROM notifications ORDER BY notif_id DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------ Exp 8 tables
    def seed_exp8_data(self):
        """Insert the 50 records of my Exp 8 into both tables (INSERT OR REPLACE, like Exp 8)."""
        advisory = [(sid, sid, classify_moisture(m), water_required(m))
                    for sid, m, _t, _h in EXP8_SENSOR_DATA]
        with self._lock:
            cur = self.conn.cursor()
            if cur.execute("SELECT COUNT(*) FROM Sensor_Data").fetchone()[0] > 0:
                return
            cur.executemany("""INSERT OR REPLACE INTO Sensor_Data
                               (sensor_id, moisture, temperature, humidity)
                               VALUES (?, ?, ?, ?)""", EXP8_SENSOR_DATA)
            cur.executemany("""INSERT OR REPLACE INTO Irrigation_Advisory
                               (advisory_id, sensor_id, recommendation, water_required)
                               VALUES (?, ?, ?, ?)""", advisory)
            self.conn.commit()

    def add_sensor_record(self, moisture, temperature, humidity):
        """Add one reading to Sensor_Data and its advice to Irrigation_Advisory."""
        rec = classify_moisture(moisture)
        with self._lock:
            try:
                cur = self.conn.cursor()
                cur.execute("INSERT INTO Sensor_Data (moisture, temperature, humidity) VALUES (?, ?, ?)",
                            (moisture, temperature, humidity))
                sid = cur.lastrowid
                cur.execute("""INSERT INTO Irrigation_Advisory (sensor_id, recommendation, water_required)
                               VALUES (?, ?, ?)""", (sid, rec, water_required(moisture)))
                self.conn.commit()
            except sqlite3.Error as e:
                self.conn.rollback()
                raise DatabaseError(str(e)) from e
        return sid, rec

    def run_select(self, sql):
        """Run a read-only query typed in the GUI. Returns (column names, rows)."""
        text = sql.strip().rstrip(";").strip()
        if not text.lower().startswith("select"):
            raise DatabaseError("Only SELECT queries can be run from this screen.")
        if ";" in text:
            raise DatabaseError("Run one query at a time (remove the extra ';').")
        with self._lock:
            try:
                cur = self.conn.cursor()
                cur.execute(text)
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description]
            except sqlite3.Error as e:
                raise DatabaseError(f"SQL error: {e}") from e
        return columns, [tuple(r) for r in rows]

    # ------------------------------------------------------------ demo data
    def is_empty(self):
        return self.query("SELECT COUNT(*) AS n FROM farmers")[0]["n"] == 0

    def _write_history(self, conn, plot, offset, rng):
        """Write 7 days of 3-hourly readings that END at a chosen moisture.

        offset is measured from the plot's own safe level, as a share of its
        water range: +0.25 = well watered, 0 = just at the safe level,
        -0.30 = very dry. Different offsets give each plot a different status.
        """
        fc, pwp = plot.field_capacity, plot.wilting_point
        safe_share = 1 - plot.mad
        m_now = pwp + min(0.97, max(0.05, safe_share + offset)) * (fc - pwp)
        per_step = (plot.kc * 5.0 / plot.root_depth_mm * 100) / 8   # loss every 3 hours
        ts = datetime.now().replace(minute=0, second=0, microsecond=0)
        values, m = [], m_now
        for step in range(56):                                # walk BACKWARD in time
            values.append((ts - timedelta(hours=3 * step), m))
            m += per_step * rng.uniform(0.7, 1.3)
            if m >= fc:                                       # an irrigation happened here
                event_ts = ts - timedelta(hours=3 * step)
                duration = round(rng.uniform(2, 6) if plot.method == "Drip" else rng.uniform(4, 8), 1)
                conn.execute("""INSERT INTO irrigation_events (plot_id, start_ts, duration_h, volume_l, source)
                                VALUES (?,?,?,?,?)""",
                             (plot.plot_id, event_ts.strftime(TS_FMT), duration, duration * plot.pump_lph, "Manual"))
                m = pwp + rng.uniform(0.35, 0.55) * (fc - pwp)
        for t, value in reversed(values):
            temp = 23 + 9 * max(0.0, 1 - abs(t.hour - 14) / 8) + rng.uniform(-1, 1)
            hum = 75 - (temp - 23) * 2.5 + rng.uniform(-3, 3)
            conn.execute("""INSERT INTO sensor_readings (plot_id, ts, moisture, temperature, humidity)
                            VALUES (?,?,?,?,?)""",
                         (plot.plot_id, t.strftime(TS_FMT), round(value + rng.uniform(-0.3, 0.3), 2),
                          round(temp, 1), round(hum, 1)))

    def reset_demo_readings(self):
        """Give every plot fresh, DIFFERENT moisture levels (for demos). Plots themselves are kept."""
        rng = random.Random(42)
        rows = self.query("SELECT * FROM plots ORDER BY plot_id")
        with self._lock:
            conn = self.conn
            for table in ("sensor_readings", "irrigation_events", "alerts", "notifications"):
                conn.execute(f"DELETE FROM {table}")
            for i, row in enumerate(rows):
                self._write_history(conn, self._row_to_plot(row), DEMO_OFFSETS[i % len(DEMO_OFFSETS)], rng)
            conn.commit()

    def seed_demo_data(self):
        """Create one farmer, one farm, six plots and 7 days of sensor history."""
        if not self.is_empty():
            return
        rng = random.Random(42)
        fid = self.execute("INSERT INTO farmers (name, phone, village, language) VALUES (?,?,?,?)",
                           ("ramesh   patil", "+91 98220 41357", "sakarwadi", "Marathi"))
        farm_id = self.execute("INSERT INTO farms (farmer_id, name, location) VALUES (?,?,?)",
                               (fid, "patil sugarcane farm", "Sakarwadi, Ahmednagar, MH"))
        today = date.today()
        demo = [  # name, acres, soil, variety, method, days since planting, pump L/h
            ("North Block", 2.5, "Black Cotton (Vertisol)", "Co 86032", "Drip", 210, 30000),
            ("River Side", 2.0, "Clay Loam", "CoM 0265", "Furrow", 150, 75000),
            ("Well Plot", 1.5, "Black Cotton (Vertisol)", "Co 0238", "Drip", 60, 20000),
            ("South Field", 2.5, "Red Laterite", "Co 86032", "Flood", 300, 90000),
            ("Ratoon Patch", 2.0, "Sandy Loam", "MS 10001", "Drip", 95, 25000),
            ("Canal Strip", 3.0, "Clay Loam", "CoM 0265", "Furrow", 30, 80000),
        ]
        conn = self.conn
        with self._lock:
            for i, (name, acres, soil, var, method, age, pump) in enumerate(demo):
                cur = conn.execute(
                    """INSERT INTO plots (farm_id, name, area_acres, soil_type, variety, method,
                                          planting_date, pump_lph) VALUES (?,?,?,?,?,?,?,?)""",
                    (farm_id, name, acres, soil, var, method,
                     str(today - timedelta(days=age)), pump))
                plot = create_plot(method, plot_id=cur.lastrowid, name=name, area_acres=acres,
                                   soil_type=soil, variety=var,
                                   planting_date=today - timedelta(days=age), pump_lph=pump)
                self._write_history(conn, plot, DEMO_OFFSETS[i % len(DEMO_OFFSETS)], rng)
            conn.commit()
