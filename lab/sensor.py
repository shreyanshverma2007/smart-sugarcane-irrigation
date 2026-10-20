"""Exp 5 - Module 1: sensor.py (my lab code)."""
import time

# The fixed values my Exp 5 returned. The dashboard can pass a plot's live
# values instead (the 'values' argument is the only thing I added).
DEFAULT_VALUES = {"soil moisture": 35, "temperature": 32, "humidity": 50}


def read_sensor(name, values=None, delay=1):
    time.sleep(delay)
    values = values or DEFAULT_VALUES

    if name == "soil moisture":
        return values["soil moisture"]
    elif name == "temperature":
        return values["temperature"]
    elif name == "humidity":
        return values["humidity"]
    else:
        raise ValueError("Invalid sensor")
