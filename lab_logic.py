"""
lab_logic.py
------------
The logic from my own lab experiments, reused inside the dashboard.

Exp 6 : sugarcane_advisory()  - same collections + map/filter/reduce/lambda
                                 program as my Exp 6 (same thresholds and the
                                 same output format)
Exp 7 : classify_moisture()   - same rule as the "Generate Irrigation
                                 Recommendation" button in my Exp 7 GUI
Exp 8 : water_required()      - water amounts used in my Exp 8
                                 Irrigation_Advisory table
"""
from functools import reduce

# ---------------------------------------------------------------- Exp 6
# Set -> unique irrigation advisory levels
ADVISORY_LEVELS = {
    "Irrigation Not Required",
    "Irrigation Recommended",
    "Immediate Irrigation Required",
}
LOW_MOISTURE_LIMIT = 32          # readings below this are "low"


def parse_readings(text):
    """'28, 32,25 ,30,26' -> [28.0, 32.0, 25.0, 30.0, 26.0]  (raises ValueError)."""
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    if not parts:
        raise ValueError("Enter at least one soil moisture reading.")
    return list(map(float, parts))


def sugarcane_advisory(farm_id, soil_moisture, temperature, humidity, rainfall):
    """My Exp 6 program, written as a function so the GUI can call it."""
    farm_info = (farm_id, "Sugarcane", "Field-A")            # Tuple

    sensor_data = {                                          # Dictionary
        "Temperature": temperature,
        "Humidity": humidity,
        "Rainfall": rainfall,
    }

    processed_readings = list(map(lambda x: round(x, 2), soil_moisture))              # map
    low_moisture = list(filter(lambda x: x < LOW_MOISTURE_LIMIT, processed_readings))  # filter
    total_moisture = reduce(lambda x, y: x + y, processed_readings)                    # reduce
    average_moisture = total_moisture / len(processed_readings)

    if average_moisture < 25:
        advisory = "IMMEDIATE IRRIGATION REQUIRED"
    elif average_moisture < 35:
        advisory = "IRRIGATION RECOMMENDED"
    else:
        advisory = "IRRIGATION NOT REQUIRED"

    return {
        "farm_info": farm_info,
        "sensor_data": sensor_data,
        "readings": processed_readings,
        "low_moisture": low_moisture,
        "total": total_moisture,
        "average": average_moisture,
        "advisory": advisory,
        "levels": ADVISORY_LEVELS,
    }


def clean_number(x):
    """Print 36.0 as 36 (like the int input in Exp 6) but keep 36.5."""
    return int(x) if float(x).is_integer() else x


def format_advisory_report(r):
    """Same printout as my Exp 6 output."""
    lines = [
        "----- Sugarcane Irrigation Advisory -----",
        f"Farm ID             : {r['farm_info'][0]}",
        f"Average Soil Moisture: {format(r['average'], '.2f')} %",
        f"Temperature         : {clean_number(r['sensor_data']['Temperature'])} °C",
        f"Humidity            : {clean_number(r['sensor_data']['Humidity'])} %",
        f"Rainfall            : {clean_number(r['sensor_data']['Rainfall'])} mm",
        "",
        f"Low Moisture Readings: {[clean_number(v) for v in r['low_moisture']]}",
        f"AI Advisory          : {r['advisory']}",
    ]
    return "\n".join(lines)


def format_collections(r):
    """Shows each collection used, for the viva."""
    return "\n".join([
        f"List  (readings)     : {[clean_number(v) for v in r['readings']]}",
        f"Tuple (farm_info)    : {r['farm_info']}",
        f"Dict  (sensor_data)  : {r['sensor_data']}",
        f"Set   (advisory lvls): {sorted(r['levels'])}",
        f"map()    -> rounded readings, filter() -> readings < {LOW_MOISTURE_LIMIT}",
        f"reduce() -> total = {round(r['total'], 2)}",
    ])


# ---------------------------------------------------------------- Exp 7 / Exp 8
EXP7_RESULTS = ("Irrigation Required", "Irrigation Recommended Soon", "No Irrigation Required")


def classify_moisture(moisture):
    """Exp 7 rule: below 40 % -> required, below 60 % -> soon, else not required."""
    if moisture < 40:
        return "Irrigation Required"
    elif moisture < 60:
        return "Irrigation Recommended Soon"
    return "No Irrigation Required"


def water_required(moisture):
    """Water amount for the Exp 8 Irrigation_Advisory table (same values as my table)."""
    result = classify_moisture(moisture)
    if result == "Irrigation Required":
        return 30.0 if moisture < 35 else 25.0
    if result == "Irrigation Recommended Soon":
        return 20.0 if moisture < 50 else 15.0
    return 0.0
