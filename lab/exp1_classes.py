"""Exp 1 - Develop Python Classes and Objects (my lab code)."""


class IrrigationSystem:
    crop_name = "Sugarcane"  # Class Variable

    # Constructor
    def __init__(self, soil_moisture, temperature):
        self.soil_moisture = soil_moisture
        self.temperature = temperature

    # Instance Method
    def irrigation_advice(self):
        if self.soil_moisture < 40:
            print("Advice: Irrigation Required")
        else:
            print("Advice: No Irrigation Needed")

    # Class Method
    @classmethod
    def crop_info(cls):
        print("Crop:", cls.crop_name)

    # Static Method
    @staticmethod
    def sensor_status():
        print("Sensors are working properly")

    # ---- added for the dashboard: same rule, but returns the text
    def advice_text(self):
        return "Irrigation Required" if self.soil_moisture < 40 else "No Irrigation Needed"


def run_demo():
    """My Exp 1 main program."""
    # Creating Object
    field1 = IrrigationSystem(35, 30)

    # Calling Methods
    IrrigationSystem.crop_info()        # Class Method
    IrrigationSystem.sensor_status()    # Static Method

    print("Soil Moisture:", field1.soil_moisture, "%")
    print("Temperature:", field1.temperature, "°C")

    field1.irrigation_advice()          # Instance Method
