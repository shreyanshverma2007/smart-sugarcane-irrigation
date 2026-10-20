"""Exp 4 - Design Abstract Classes and Polymorphism (my lab code)."""
from abc import ABC, abstractmethod


# Abstract Base Class
class IrrigationAdvisory(ABC):

    def __init__(self, crop, soil_moisture, temperature):
        self.crop = crop
        self.soil_moisture = soil_moisture
        self.temperature = temperature

    @abstractmethod
    def get_advisory(self):
        pass


# AI-based Irrigation Advisory
class AIAdvisory(IrrigationAdvisory):

    def get_advisory(self):
        if self.soil_moisture < 40:
            return "AI Advisory: Irrigation required."
        else:
            return "AI Advisory: No irrigation required."


# Sensor-based Irrigation Advisory
class SensorAdvisory(IrrigationAdvisory):

    def get_advisory(self):
        if self.soil_moisture < 35:
            return "Sensor Advisory: Start irrigation."
        else:
            return "Sensor Advisory: Soil moisture is sufficient."


def sample_advisories():
    """Sample data stored in a list + the list operations from Exp 4."""
    advisories = [
        AIAdvisory("Sugarcane", 32, 36),
        SensorAdvisory("Sugarcane", 45, 34),
        AIAdvisory("Sugarcane", 38, 35),
        SensorAdvisory("Sugarcane", 28, 37)
    ]
    # List operations
    advisories.append(AIAdvisory("Sugarcane", 42, 33))
    advisories.remove(advisories[1])
    return advisories


def run_demo():
    """My Exp 4 main program."""
    advisories = sample_advisories()

    print("IRRIGATION ADVISORY SYSTEM")

    # Polymorphic behaviour
    for advisory in advisories:
        print("Crop:", advisory.crop)
        print("Soil Moisture:", advisory.soil_moisture, "%")
        print("Temperature:", advisory.temperature, "°C")
        print(advisory.get_advisory())

    # List length
    print("Total advisory records:", len(advisories))
