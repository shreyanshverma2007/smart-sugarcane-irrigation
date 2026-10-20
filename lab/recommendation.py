"""Exp 5 - Module 2: recommendation.py (my lab code)."""


def recommend(soil, temperature, humidity):

    if soil is None or temperature is None or humidity is None:
        return "Missing sensor data"

    if soil < 40 and temperature > 30:
        return "Irrigation Required"

    return "Irrigation Not Required"
