"""
analytics.py
------------
Exp 6 : Python Collections and Functional Programming

Collections used : namedtuple, deque, defaultdict, Counter, OrderedDict
Functional tools : map, filter, reduce, lambda, sorted(key=...), zip,
                   list / dict comprehensions, generator expressions,
                   higher-order functions (a function that returns a function)
"""
from collections import Counter, OrderedDict, defaultdict, deque, namedtuple
from functools import reduce

PlotSnapshot = namedtuple("PlotSnapshot", "plot_id name method moisture threshold status")


class MoistureHistory:
    """Keeps the last N moisture values of every plot in a deque (fast append/pop)."""

    def __init__(self, maxlen=60):
        self._data = defaultdict(lambda: deque(maxlen=maxlen))

    def push(self, plot_id, value):
        self._data[plot_id].append(value)

    def get(self, plot_id):
        return list(self._data[plot_id])

    def moving_average(self, plot_id, window=5):
        values = list(self._data[plot_id])[-window:]
        return round(sum(values) / len(values), 2) if values else None

    def trend(self, plot_id):
        values = self.get(plot_id)
        if len(values) < 2:
            return "steady"
        change = values[-1] - values[max(0, len(values) - 6)]
        return "falling" if change < -0.5 else "rising" if change > 0.5 else "steady"


def snapshot(plots):
    """Turn Plot objects into lightweight immutable named tuples (map + lambda)."""
    return list(map(
        lambda p: PlotSnapshot(
            p.plot_id, p.name, p.method_name, p.current_moisture, p.threshold,
            "DRY" if p.current_moisture <= p.threshold else "OK"),
        plots))


def dry_plots(plots):
    return list(filter(lambda p: p.current_moisture <= p.threshold, plots))


def total_area(plots):
    return reduce(lambda acc, p: acc + p.area_acres, plots, 0.0)


def average_moisture(plots):
    values = [p.current_moisture for p in plots]
    return round(sum(values) / len(values), 1) if values else 0.0


def method_counts(plots):
    return Counter(p.method_name for p in plots)


def area_by_soil(plots):
    groups = defaultdict(float)
    for p in plots:
        groups[p.soil_type] += p.area_acres
    return dict(groups)


def plots_by_stage(plots):
    groups = defaultdict(list)
    for p in plots:
        groups[p.stage].append(p.name)
    return groups


def rank_by_urgency(recommendations):
    return sorted(recommendations, key=lambda r: (r["priority"], r["moisture"] - r["threshold"]))


def make_alert_filter(min_level):
    """Higher-order function: returns a function that keeps alerts >= min_level."""
    order = ["INFO", "MILD", "SEVERE", "CRITICAL"]
    cut = order.index(min_level)
    return lambda alert: order.index(alert["level"]) >= cut


def farm_kpis(plots, recommendations):
    """Ordered dictionary of headline numbers for the main dashboard."""
    water = reduce(lambda a, r: a + r["volume_l"], filter(lambda r: r["priority"] <= 2, recommendations), 0)
    return OrderedDict([
        ("Plots", len(plots)),
        ("Total area", f"{total_area(plots):.1f} ac"),
        ("Avg moisture", f"{average_moisture(plots)} %"),
        ("Need water now", len(dry_plots(plots))),
        ("Water today", f"{water / 1000:,.0f} m3"),
    ])


def stats(values):
    """min / max / mean of a list using zip + comprehension style helpers."""
    if not values:
        return {"min": 0, "max": 0, "mean": 0}
    return {"min": min(values), "max": max(values), "mean": round(sum(values) / len(values), 2)}


def pairwise_changes(values):
    """Differences between consecutive readings using zip."""
    return [round(b - a, 2) for a, b in zip(values, values[1:])]
