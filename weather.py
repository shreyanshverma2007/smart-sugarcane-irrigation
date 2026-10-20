"""
weather.py
----------
Simulated 7-day weather forecast + reference evapotranspiration (ET0).

Exp 5 : Modules / thread-safety -> a Lock protects the forecast because the
        sensor thread and the GUI thread both read it.
Exp 6 : Collections             -> namedtuple DayWeather
"""
from __future__ import annotations

import math
import random
import threading
from collections import namedtuple
from datetime import date, timedelta

from exceptions import parse_float_in_range, WeatherDataError

DayWeather = namedtuple("DayWeather", "day tmax tmin humidity rain_mm")

# Extraterrestrial radiation for ~16-19 deg N in October, as mm/day of water
RA_MM_PER_DAY = 13.5


def hargreaves_et0(tmax, tmin, ra=RA_MM_PER_DAY):
    """Hargreaves equation: ET0 = 0.0023 * Ra * (Tmean + 17.8) * sqrt(Tmax - Tmin)."""
    tmean = (tmax + tmin) / 2
    return round(0.0023 * ra * (tmean + 17.8) * math.sqrt(max(tmax - tmin, 0)), 2)


def effective_rain(rain_mm):
    """Only part of rainfall is useful to the crop; light showers (<5 mm) are ignored."""
    return round(0.8 * rain_mm, 1) if rain_mm >= 5 else 0.0


class WeatherService:
    def __init__(self, days=7, seed=None):
        self.days = days
        self._lock = threading.Lock()
        self.forecast: list[DayWeather] = []
        self.regenerate(seed)

    def regenerate(self, seed=None):
        rng = random.Random(seed if seed is not None else date.today().toordinal())
        start = date.today()
        new = []
        for i in range(self.days):
            tmax = round(rng.uniform(30, 35), 1)
            tmin = round(rng.uniform(19, 23), 1)
            rain = round(rng.uniform(4, 28), 1) if rng.random() < 0.3 else 0.0
            humidity = round(rng.uniform(55, 70) + (12 if rain else 0), 0)
            new.append(DayWeather(start + timedelta(days=i), tmax, tmin, humidity, rain))
        with self._lock:
            self.forecast = new

    def today(self) -> DayWeather:
        return self.day(0)

    def day(self, index) -> DayWeather:
        """Forecast for day `index`; beyond the forecast, repeat the last day."""
        with self._lock:
            if index < len(self.forecast):
                return self.forecast[index]
            last = self.forecast[-1]
        return last._replace(day=date.today() + timedelta(days=index), rain_mm=0.0)

    def all_days(self):
        with self._lock:
            return list(self.forecast)

    @staticmethod
    def et0(day: DayWeather) -> float:
        return hargreaves_et0(day.tmax, day.tmin)

    @staticmethod
    def effective_rain(rain_mm) -> float:
        return effective_rain(rain_mm)

    def rain_next_days(self, n=2) -> float:
        """Total effective rain expected in the next n days (mm)."""
        return round(sum(effective_rain(self.day(i).rain_mm) for i in range(n)), 1)

    def update_day(self, index, tmax, tmin, humidity, rain):
        tmax = parse_float_in_range(tmax, "Max temperature", 10, 50)
        tmin = parse_float_in_range(tmin, "Min temperature", 0, 40)
        humidity = parse_float_in_range(humidity, "Humidity", 5, 100)
        rain = parse_float_in_range(rain, "Rainfall", 0, 400)
        if tmin >= tmax:
            raise WeatherDataError("Min temperature must be lower than max temperature.")
        with self._lock:
            old = self.forecast[index]
            self.forecast[index] = DayWeather(old.day, tmax, tmin, humidity, rain)
