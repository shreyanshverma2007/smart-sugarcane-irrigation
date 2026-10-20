"""Exp 5 - Main program: 3 sensor threads + exception handling (my lab code)."""
import threading

from lab.recommendation import recommend
from lab.sensor import read_sensor

SENSORS = ("soil moisture", "temperature", "humidity")


def monitor_all(values=None, delay=1, sensors=SENSORS, log=print):
    """Read every sensor in its own thread, wait for all of them, then recommend.

    Same steps as my Exp 5: create threads -> start -> join -> recommend().
    Returns (data dict, recommendation text).
    """
    data = {name: None for name in SENSORS}

    def monitor(sensor_name):
        try:
            data[sensor_name] = read_sensor(sensor_name, values, delay)
            log(sensor_name, ":", data[sensor_name])
        except ValueError as e:
            log("Error:", e)

    # Create threads
    threads = [threading.Thread(target=monitor, args=(name,)) for name in sensors]

    # Start threads
    for t in threads:
        t.start()

    # Wait for threads
    for t in threads:
        t.join()

    result = recommend(data["soil moisture"], data["temperature"], data["humidity"])
    return data, result


def run_demo():
    """My Exp 5 main program (plus one wrong sensor name to show the exception)."""
    data, result = monitor_all()
    print("\nAI Irrigation Advisory")
    print(result)

    print("\nException handling test - asking for a sensor that does not exist:")
    monitor_all(delay=0, sensors=("rainfall",))
