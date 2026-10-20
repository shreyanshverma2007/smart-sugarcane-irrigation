"""
models.py
---------
Exp 1 : Classes and Objects        -> Person, Farmer, Plot, Farm, SensorReading
Exp 2 : Constructors and Lists     -> __init__ of every class, Plot.readings list,
                                      Farm.plots list (add / remove / search)
Exp 3 : String Handling            -> name cleaning, title(), masking phone numbers,
                                      initials, formatted reports (ljust / f-strings)
        Inheritance                -> Person -> Farmer,
                                      Plot -> DripPlot / FurrowPlot / FloodPlot
"""
from __future__ import annotations

from datetime import date, datetime

from exceptions import DuplicatePlotError, InvalidPlotDataError

# ----------------------------------------------------------------------------
# Agronomy constants (sugarcane, Maharashtra / Karnataka conditions)
# ----------------------------------------------------------------------------
ACRE_TO_M2 = 4046.86
ACRE_TO_HA = 0.404686

# Volumetric soil moisture (%) : (field capacity, permanent wilting point)
SOIL_PROPERTIES = {
    "Black Cotton (Vertisol)": (45.0, 25.0),
    "Clay Loam": (38.0, 20.0),
    "Red Laterite": (30.0, 15.0),
    "Sandy Loam": (22.0, 10.0),
}

# Potential cane yield in tonnes per hectare under good management
VARIETY_POTENTIAL = {
    "Co 86032": 120.0,
    "CoM 0265": 130.0,
    "Co 0238": 115.0,
    "MS 10001": 110.0,
}

# (stage name, start day, end day, crop coefficient Kc, effective root depth in metres)
# Kc values follow FAO-56 for sugarcane (ini 0.40, mid 1.25, end 0.75)
GROWTH_STAGES = [
    ("Germination", 0, 45, 0.45, 0.25),
    ("Tillering", 45, 120, 0.80, 0.45),
    ("Grand Growth", 120, 270, 1.25, 0.60),
    ("Maturity", 270, 400, 0.75, 0.60),
]

MAX_READINGS = 240          # readings kept in memory per plot


def parse_date(value):
    """Accept a date object or 'YYYY-MM-DD' text and return a date."""
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        raise InvalidPlotDataError(
            f"Date '{value}' must be in YYYY-MM-DD format, e.g. 2026-03-15."
        ) from None


# ----------------------------------------------------------------------------
# People  (Exp 1 + Exp 3 inheritance + string handling)
# ----------------------------------------------------------------------------
class Person:
    """A generic person. Cleans the name and phone number on creation."""

    def __init__(self, name: str, phone: str = ""):
        # "  ramesh   PATIL " -> "Ramesh Patil"
        self.name = " ".join(name.split()).title()
        # keep digits only: "+91 98220-12345" -> "919822012345"
        self.phone = "".join(ch for ch in phone if ch.isdigit())

    @property
    def masked_phone(self) -> str:
        """Show only the last 4 digits: XXXXXX2345."""
        if len(self.phone) < 4:
            return "N/A"
        return "X" * (len(self.phone) - 4) + self.phone[-4:]

    @property
    def initials(self) -> str:
        return "".join(part[0] for part in self.name.split()).upper()

    def __str__(self):
        return f"{self.name} ({self.masked_phone})"


class Farmer(Person):
    """A farmer IS-A person, with a village and a preferred greeting."""

    def __init__(self, name, phone="", village=""):
        super().__init__(name, phone)          # call the parent constructor
        self.village = village.strip().title()

    def greeting(self) -> str:
        first_name = self.name.split()[0] if self.name else "Farmer"
        return f"Namaskar {first_name}ji"

    def __str__(self):                         # method overriding
        return f"{super().__str__()} - {self.village}"


# ----------------------------------------------------------------------------
# Sensor reading
# ----------------------------------------------------------------------------
class SensorReading:
    """One reading from the soil-moisture / weather sensor of a plot."""

    def __init__(self, plot_id, moisture, temperature, humidity, timestamp=None):
        self.plot_id = plot_id
        self.moisture = round(float(moisture), 2)
        self.temperature = round(float(temperature), 1)
        self.humidity = round(float(humidity), 1)
        self.timestamp = timestamp or datetime.now()

    def __str__(self):
        return (f"Plot {self.plot_id} @ {self.timestamp:%d-%b %H:%M} | "
                f"Moisture {self.moisture:5.1f}% | Temp {self.temperature:4.1f} C | "
                f"RH {self.humidity:4.1f}%")


# ----------------------------------------------------------------------------
# Plots  (base class + 3 child classes)
# ----------------------------------------------------------------------------
class Plot:
    """A sugarcane plot. Child classes decide the irrigation method."""

    method_name = "Generic"
    efficiency = 0.70             # fraction of pumped water that reaches roots
    mad = 0.50                    # management allowed depletion
    wetted_fraction = 1.0         # part of the field actually wetted
    supports_fertigation = False

    def __init__(self, plot_id, name, area_acres, soil_type, variety,
                 planting_date, pump_lph=25000.0, farm_id=1):
        name = name.strip()
        if not name:
            raise InvalidPlotDataError("Plot name cannot be empty.")
        if area_acres <= 0:
            raise InvalidPlotDataError("Area must be greater than 0 acres.")
        if soil_type not in SOIL_PROPERTIES:
            raise InvalidPlotDataError(f"Unknown soil type '{soil_type}'.")
        if variety not in VARIETY_POTENTIAL:
            raise InvalidPlotDataError(f"Unknown variety '{variety}'.")
        planting_date = parse_date(planting_date)
        if planting_date > date.today():
            raise InvalidPlotDataError("Planting date cannot be in the future.")
        if pump_lph <= 0:
            raise InvalidPlotDataError("Pump flow must be greater than zero.")

        self.plot_id = plot_id
        self.farm_id = farm_id
        self.name = name
        self.area_acres = float(area_acres)
        self.soil_type = soil_type
        self.variety = variety
        self.planting_date = planting_date
        self.pump_lph = float(pump_lph)
        self.readings: list[SensorReading] = []   # Exp 2 : list inside object

    # ---- list handling ------------------------------------------------------
    def add_reading(self, reading: SensorReading):
        self.readings.append(reading)
        if len(self.readings) > MAX_READINGS:
            del self.readings[0]                  # keep the list bounded

    @property
    def latest_reading(self):
        return self.readings[-1] if self.readings else None

    @property
    def current_moisture(self) -> float:
        if self.readings:
            return self.readings[-1].moisture
        return self.field_capacity * 0.9

    # ---- crop stage ---------------------------------------------------------
    @property
    def age_days(self) -> int:
        return (date.today() - self.planting_date).days

    @property
    def stage_info(self):
        age = self.age_days
        for stage in GROWTH_STAGES:
            if stage[1] <= age < stage[2]:
                return stage
        return GROWTH_STAGES[-1]

    @property
    def stage(self) -> str:
        return self.stage_info[0]

    @property
    def kc(self) -> float:
        return self.stage_info[3]

    @property
    def root_depth_mm(self) -> float:
        return self.stage_info[4] * 1000

    # ---- soil ---------------------------------------------------------------
    @property
    def field_capacity(self) -> float:
        return SOIL_PROPERTIES[self.soil_type][0]

    @property
    def wilting_point(self) -> float:
        return SOIL_PROPERTIES[self.soil_type][1]

    @property
    def threshold(self) -> float:
        """Moisture level at which irrigation should start."""
        span = self.field_capacity - self.wilting_point
        return round(self.wilting_point + (1 - self.mad) * span, 1)

    # ---- area ---------------------------------------------------------------
    @property
    def area_m2(self) -> float:
        return self.area_acres * ACRE_TO_M2

    @property
    def area_ha(self) -> float:
        return self.area_acres * ACRE_TO_HA

    @property
    def method(self) -> str:
        return self.method_name

    def describe(self) -> str:
        """Multi-line formatted description (string handling)."""
        rows = [
            ("Plot", f"{self.name} (ID {self.plot_id})"),
            ("Area", f"{self.area_acres:.2f} acres = {self.area_ha:.2f} ha"),
            ("Soil", f"{self.soil_type}  [FC {self.field_capacity}% | PWP {self.wilting_point}%]"),
            ("Variety", self.variety),
            ("Irrigation", f"{self.method_name} (efficiency {self.efficiency:.0%})"),
            ("Planted", f"{self.planting_date:%d %b %Y}  ({self.age_days} days)"),
            ("Stage", f"{self.stage}  (Kc {self.kc}, root zone {self.root_depth_mm:.0f} mm)"),
            ("Irrigate below", f"{self.threshold}% moisture"),
        ]
        return "\n".join(f"{label.ljust(15)}: {value}" for label, value in rows)

    def __str__(self):
        return f"{self.name} [{self.method_name}, {self.area_acres} ac]"


class DripPlot(Plot):
    method_name = "Drip"
    efficiency = 0.90
    mad = 0.30                 # drip is irrigated little and often
    wetted_fraction = 0.65     # drip wets only the root strip
    supports_fertigation = True


class FurrowPlot(Plot):
    method_name = "Furrow"
    efficiency = 0.60


class FloodPlot(Plot):
    method_name = "Flood"
    efficiency = 0.50


PLOT_TYPES = {"Drip": DripPlot, "Furrow": FurrowPlot, "Flood": FloodPlot}


def create_plot(method, **kwargs) -> Plot:
    """Factory: pick the right child class from the irrigation method."""
    plot_class = PLOT_TYPES.get(method)
    if plot_class is None:
        raise InvalidPlotDataError(f"Unknown irrigation method '{method}'.")
    return plot_class(**kwargs)


# ----------------------------------------------------------------------------
# Farm  (a list of Plot objects)
# ----------------------------------------------------------------------------
class Farm:
    def __init__(self, farm_id, name, farmer: Farmer, plots=None):
        self.farm_id = farm_id
        self.name = name.strip().title()
        self.farmer = farmer
        # never use a mutable default argument like plots=[]
        self.plots: list[Plot] = list(plots) if plots else []

    def add_plot(self, plot: Plot):
        if any(p.name.lower() == plot.name.lower() for p in self.plots):
            raise DuplicatePlotError(f"A plot named '{plot.name}' already exists.")
        self.plots.append(plot)

    def remove_plot(self, plot_id):
        self.plots = [p for p in self.plots if p.plot_id != plot_id]

    def get_plot(self, plot_id):
        for plot in self.plots:
            if plot.plot_id == plot_id:
                return plot
        return None

    @property
    def total_area(self) -> float:
        return sum(p.area_acres for p in self.plots)

    def __len__(self):
        return len(self.plots)

    def __iter__(self):
        return iter(self.plots)

    def __str__(self):
        return f"{self.name} | {self.farmer} | {len(self)} plots, {self.total_area:.1f} acres"
