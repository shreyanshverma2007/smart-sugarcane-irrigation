"""
advisors.py
-----------
Exp 4 : Abstract Classes and Polymorphism

`Advisor` is an abstract base class (ABC). Every scenario-specific advisor
inherits from it and MUST implement analyze() and headline(). The GUI keeps
a list of different advisors and calls advisor.summary(plot, weather) on each
one without caring which class it is -> runtime polymorphism.

Scenario mapping
    3  Crop Water Requirement      -> WaterRequirementAdvisor
    4  Next Irrigation Date        -> NextIrrigationAdvisor
    5  Smart Irrigation Rec.       -> IrrigationAdvisor
    6  Weather-Aware Advisory      -> WeatherAwareAdvisor (overrides analyze)
    7  Water Stress Detection      -> StressDetector
    8  Pump Scheduling             -> PumpScheduler
    9  Fertigation                 -> FertigationAdvisor
    11 Yield Prediction            -> YieldPredictor
"""
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

from models import GROWTH_STAGES, VARIETY_POTENTIAL

LEVEL_RANK = {"NORMAL": 0, "MILD": 1, "SEVERE": 2, "CRITICAL": 3}


class Advisor(ABC):
    name = "Advisor"

    @abstractmethod
    def analyze(self, plot, weather) -> dict:
        """Return a dictionary with the advisor's results for one plot."""

    @abstractmethod
    def headline(self, result: dict) -> str:
        """One-line human readable summary of analyze()'s result."""

    def summary(self, plot, weather) -> str:          # concrete method
        return f"{self.name:<20} {self.headline(self.analyze(plot, weather))}"


# ---------------------------------------------------------------- Scenario 3
class WaterRequirementAdvisor(Advisor):
    name = "Water requirement"

    def analyze(self, plot, weather):
        today = weather.today()
        et0 = weather.et0(today)
        etc = round(et0 * plot.kc, 2)                 # crop evapotranspiration
        net_litres = etc * plot.area_m2 * plot.wetted_fraction   # 1 mm on 1 m2 = 1 L
        gross_litres = net_litres / plot.efficiency
        return {
            "plot_id": plot.plot_id, "stage": plot.stage, "kc": plot.kc,
            "et0": et0, "etc_mm": etc,
            "net_litres": round(net_litres), "gross_litres": round(gross_litres),
            "weekly_m3": round(gross_litres * 7 / 1000, 1),
        }

    def headline(self, r):
        return f"ETc {r['etc_mm']} mm/day -> {r['gross_litres']:,} L/day"


# ---------------------------------------------------------------- Scenario 4
class NextIrrigationAdvisor(Advisor):
    name = "Next irrigation"

    def analyze(self, plot, weather):
        moisture = plot.current_moisture
        root = plot.root_depth_mm
        days = 0
        for i in range(30):                         # simulate day by day
            if moisture <= plot.threshold:
                break
            day = weather.day(i)
            etc = weather.et0(day) * plot.kc
            gain = weather.effective_rain(day.rain_mm)
            moisture = min(plot.field_capacity, moisture + (gain - etc) / root * 100)
            days += 1
        rate = weather.et0(weather.today()) * plot.kc / root * 100
        return {
            "plot_id": plot.plot_id, "moisture": plot.current_moisture,
            "threshold": plot.threshold, "depletion_per_day": round(rate, 2),
            "days_left": days, "next_date": date.today() + timedelta(days=days),
        }

    def project(self, plot, weather, days=10):
        """Expected moisture for today + the next `days` days if we do NOT irrigate."""
        moisture, values = plot.current_moisture, [plot.current_moisture]
        for i in range(days):
            day = weather.day(i)
            etc = weather.et0(day) * plot.kc
            moisture += (weather.effective_rain(day.rain_mm) - etc) / plot.root_depth_mm * 100
            moisture = max(plot.wilting_point - 2, min(plot.field_capacity, moisture))
            values.append(round(moisture, 2))
        return values

    def headline(self, r):
        if r["days_left"] == 0:
            return "Irrigate TODAY"
        return f"in {r['days_left']} day(s) on {r['next_date']:%d %b}"


# ---------------------------------------------------------------- Scenario 5
class IrrigationAdvisor(Advisor):
    name = "Recommendation"

    def __init__(self):
        self.next_advisor = NextIrrigationAdvisor()   # composition

    def analyze(self, plot, weather):
        moisture = plot.current_moisture
        deficit = max(0.0, plot.field_capacity - moisture)       # % volume
        net_mm = deficit / 100 * plot.root_depth_mm
        gross_mm = net_mm / plot.efficiency
        volume = gross_mm * plot.area_m2 * plot.wetted_fraction
        hours = volume / plot.pump_lph
        nxt = self.next_advisor.analyze(plot, weather)

        if moisture <= plot.threshold:
            action, priority = "IRRIGATE NOW", 1
            reason = f"Moisture {moisture:.1f}% is below the safe level {plot.threshold}%"
        elif nxt["days_left"] <= 1:
            action, priority = "IRRIGATE TOMORROW", 2
            reason = "Soil will reach the safe level within a day"
        elif nxt["days_left"] <= 3:
            action, priority = f"PLAN IN {nxt['days_left']} DAYS", 3
            reason = f"Moisture is dropping {nxt['depletion_per_day']}%/day"
        else:
            action, priority = "NO IRRIGATION NEEDED", 4
            reason = f"Enough water for {nxt['days_left']} more days"

        return {
            "plot_id": plot.plot_id, "plot_name": plot.name, "action": action,
            "priority": priority, "reason": reason, "moisture": moisture,
            "threshold": plot.threshold, "net_mm": round(net_mm, 1),
            "gross_mm": round(gross_mm, 1), "volume_l": round(volume),
            "duration_h": round(hours, 2), "next_date": nxt["next_date"],
            "days_left": nxt["days_left"], "weather_note": "",
        }

    def headline(self, r):
        text = r["action"]
        if r["priority"] <= 3:
            text += f" ({r['volume_l']:,} L, {r['duration_h']:.1f} h pump)"
        return text


# ---------------------------------------------------------------- Scenario 6
class WeatherAwareAdvisor(IrrigationAdvisor):
    """Inherits the basic recommendation and OVERRIDES analyze() to add weather."""
    name = "Weather-aware advice"

    def analyze(self, plot, weather):
        result = super().analyze(plot, weather)       # reuse parent logic
        rain48 = weather.rain_next_days(2)
        today = weather.today()
        notes = []
        span = plot.field_capacity - plot.wilting_point
        critical = plot.current_moisture <= plot.wilting_point + 0.25 * span

        if result["priority"] <= 2 and rain48 > 0:
            if rain48 >= 0.5 * result["net_mm"] and not critical:
                result["action"], result["priority"] = "POSTPONE - RAIN EXPECTED", 5
                result["reason"] = f"{rain48} mm useful rain expected in 48 h"
                result["volume_l"], result["duration_h"] = 0, 0.0
            else:
                factor = max(0.0, 1 - rain48 / max(result["net_mm"], 1))
                result["volume_l"] = round(result["volume_l"] * factor)
                result["duration_h"] = round(result["duration_h"] * factor, 2)
                result["action"] = "IRRIGATE LIGHTLY"
                notes.append(f"Rain of {rain48} mm expected, so water is reduced")
        if today.tmax >= 34:
            notes.append("Hot day - irrigate early morning or after 5 PM")
        if today.humidity >= 80:
            notes.append("High humidity - watch for fungal disease")
        result["rain_48h"] = rain48
        result["weather_note"] = "; ".join(notes)
        return result

    def headline(self, r):
        text = super().headline(r)
        return text + (f" | {r['weather_note']}" if r["weather_note"] else "")


# ---------------------------------------------------------------- Scenario 7
class StressDetector(Advisor):
    name = "Water stress"
    COLORS = {"NORMAL": "#2e7d32", "MILD": "#c79100", "SEVERE": "#e65100", "CRITICAL": "#c62828"}

    def analyze(self, plot, weather):
        m = plot.current_moisture
        span = plot.field_capacity - plot.wilting_point
        if m <= plot.wilting_point + 0.05 * span:
            level, msg = "CRITICAL", "Crop is near wilting point - irrigate immediately"
        elif m <= plot.wilting_point + 0.25 * span:
            level, msg = "SEVERE", "Leaves may roll; growth is slowing down"
        elif m <= plot.threshold:
            level, msg = "MILD", "Moisture below safe level - irrigate soon"
        else:
            level, msg = "NORMAL", "Crop has enough water"

        reading = plot.latest_reading
        temp = reading.temperature if reading else weather.today().tmax
        heat = temp >= 38
        if heat:
            msg += "; HEAT stress risk"
        if level != "NORMAL" and plot.stage in ("Tillering", "Grand Growth"):
            msg += f" ({plot.stage} is a sensitive stage)"
        return {"plot_id": plot.plot_id, "plot_name": plot.name, "level": level,
                "message": msg, "moisture": m, "temperature": temp,
                "heat_stress": heat, "color": self.COLORS[level]}

    def headline(self, r):
        return f"{r['level']} - {r['message']}"


# ---------------------------------------------------------------- Scenario 9
class FertigationAdvisor(Advisor):
    name = "Fertigation"
    # share of the season's total N, P, K given in each stage
    STAGE_SPLIT = {
        "Germination": (0.10, 0.50, 0.25),
        "Tillering": (0.40, 0.30, 0.25),
        "Grand Growth": (0.45, 0.20, 0.40),
        "Maturity": (0.05, 0.00, 0.10),
    }

    def __init__(self, npk_per_ha=(250.0, 115.0, 115.0)):
        self.npk_per_ha = npk_per_ha        # recommended dose for sugarcane

    def analyze(self, plot, weather):
        stage = plot.stage_info
        weeks = max(1.0, (stage[2] - stage[1]) / 7)
        split = self.STAGE_SPLIT[stage[0]]
        n, p, k = (total * share / weeks * plot.area_ha
                   for total, share in zip(self.npk_per_ha, split))
        map_kg = p / 0.61                    # 12:61:00 (MAP) supplies P
        urea_kg = max(0.0, n - map_kg * 0.12) / 0.46
        mop_kg = k / 0.60                    # Muriate of potash, 60 % K2O

        notes = []
        if not plot.supports_fertigation:
            notes.append(f"{plot.method_name} plot: apply as soil dose near the root zone")
        if plot.current_moisture <= plot.threshold:
            notes.append("Irrigate first - do not fertilise dry soil")
        if stage[0] == "Maturity":
            notes.append("Stop nitrogen 2 months before harvest")
        return {"plot_id": plot.plot_id, "stage": stage[0],
                "n_kg": round(n, 1), "p_kg": round(p, 1), "k_kg": round(k, 1),
                "urea_kg": round(urea_kg, 1), "map_kg": round(map_kg, 1),
                "mop_kg": round(mop_kg, 1),
                "note": "; ".join(notes) or "Inject through drip in 2 split doses"}

    def headline(self, r):
        return (f"This week: Urea {r['urea_kg']} kg, 12:61:00 {r['map_kg']} kg, "
                f"MOP {r['mop_kg']} kg")


# --------------------------------------------------------------- Scenario 11
class YieldPredictor(Advisor):
    """FAO-33 yield response: 1 - Ya/Ym = Ky (1 - ETa/ETm), Ky = 1.2 for sugarcane."""
    name = "Yield forecast"
    KY = 1.2
    METHOD_FACTOR = {"Drip": 1.00, "Furrow": 0.90, "Flood": 0.85}
    SUGAR_RECOVERY = 0.115              # 11.5 % recovery at the factory

    def analyze(self, plot, weather):
        values = [r.moisture for r in plot.readings] or [plot.current_moisture]
        low, safe = plot.wilting_point, plot.threshold
        # 1.0 = no water stress, 0.0 = soil at wilting point
        ratios = list(map(lambda m: min(1.0, max(0.0, (m - low) / (safe - low))), values))
        water_index = sum(ratios) / len(ratios)
        potential = VARIETY_POTENTIAL[plot.variety] * self.METHOD_FACTOR.get(plot.method_name, 0.9)
        predicted = max(0.0, potential * (1 - self.KY * (1 - water_index)))
        total = predicted * plot.area_ha
        return {"plot_id": plot.plot_id, "variety": plot.variety,
                "potential_t_ha": round(potential, 1), "water_index": round(water_index, 2),
                "predicted_t_ha": round(predicted, 1), "total_t": round(total, 1),
                "sugar_t": round(total * self.SUGAR_RECOVERY, 1),
                "loss_pct": round((1 - predicted / potential) * 100, 1)}

    def headline(self, r):
        return f"{r['predicted_t_ha']} t/ha (water index {r['water_index']}) -> {r['total_t']} t cane"


# ---------------------------------------------------------------- Scenario 8
class PumpScheduler:
    """Greedy scheduler: most urgent plot first, on whichever pump is free first."""

    def build(self, recommendations, start="06:00", pumps=1, gap_minutes=10,
              include_planned=True):
        hour, minute = (int(x) for x in start.split(":"))
        begin_at = datetime.combine(date.today(), datetime.min.time()).replace(
            hour=hour, minute=minute)
        max_priority = 3 if include_planned else 2
        jobs = sorted(
            (r for r in recommendations if r["priority"] <= max_priority and r["volume_l"] > 0),
            key=lambda r: (r["priority"], r["moisture"] - r["threshold"]),
        )
        pump_free = [begin_at] * pumps
        schedule = []
        for job in jobs:
            pump = min(range(pumps), key=lambda i: pump_free[i])
            start_t = pump_free[pump]
            end_t = start_t + timedelta(hours=job["duration_h"])
            pump_free[pump] = end_t + timedelta(minutes=gap_minutes)
            schedule.append({**job, "pump": pump + 1, "start": start_t, "end": end_t})
        return schedule
