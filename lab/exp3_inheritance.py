"""Exp 3 - Process Information Using String Handling and Inheritance (my lab code)."""


class Farm:
    def __init__(self, farm_id, location):
        self.farm_id = farm_id
        self.location = location

    def display(self):
        print("Farm ID:", self.farm_id, "Location:", self.location)


class CropMonitoring(Farm):                       # 1. Single inheritance
    def __init__(self, farm_id, location, crop):
        super().__init__(farm_id, location)
        self.crop = crop.upper()

    def monitor(self, moisture):
        self.moisture = moisture
        print("Crop:", self.crop, "Moisture:", self.moisture, "%")


class Sensor:
    def sensor_data(self):
        self.sensor_id = "SNS101"


class SoilSensor(Sensor):
    def soil_data(self):
        self.moisture = 38


class CropHealthAnalyzer(SoilSensor):             # 2. Multilevel inheritance
    def analyze(self):
        print("Crop Health:",
              "Water Stress" if self.moisture < 40 else "Healthy")

    # ---- added for the dashboard: same rule, returns the text
    def health(self):
        return "Water Stress" if self.moisture < 40 else "Healthy"


class WheatFarm(Farm):                            # 3. Hierarchical inheritance
    def irrigation(self):
        print("Wheat: Irrigate when moisture is low.")


class RiceFarm(Farm):
    def irrigation(self):
        print("Rice: Maintain adequate water.")


class WeatherData:
    def weather(self):
        self.rainfall = 5
        print("Rainfall:", self.rainfall, "mm")


class SoilData:
    def soil(self):
        self.moisture = 38
        print("Soil Moisture:", self.moisture, "%")


class SmartFarm(WeatherData, SoilData):          # 4. Multiple inheritance
    def advice(self):
        print("Advice:", "Irrigate Today"
              if self.moisture < 40 and self.rainfall < 10
              else "No Irrigation")

    # ---- added for the dashboard: same rule, returns the text
    def advice_text(self):
        return "Irrigate Today" if self.moisture < 40 and self.rainfall < 10 else "No Irrigation"


class SugarcaneFarm(Farm):                        # 5. Method overriding
    def irrigation(self):
        print("Sugarcane: Irrigate based on moisture and weather.")


class CottonFarm(Farm):
    def irrigation(self):
        print("Cotton: Irrigate when soil moisture is low.")


def string_report(farm_id="FRM1001", crop="sugarcane"):
    """The 10 string-handling operations from Exp 3, as (label, result) pairs."""
    obj = CropMonitoring(farm_id, "Karnataka", crop)
    fertilizers = "Urea,DAP,Potash,Micronutrients"
    status = "Dry"
    report = "Pest detected. Pest activity. Pest control required."
    soil = "   Soil moisture is 38 percent.   "
    crops = ["Sugarcane", "Wheat", "Rice"]
    code = "SC2026"
    weather = "Heavy rainfall is expected tomorrow morning"
    recommendation = "Irrigate the sugarcane crop tomorrow"
    return [
        ("1. Uppercase", "crop.upper()", obj.crop),
        ("2. Fertilizers", 'fertilizers.split(",")', fertilizers.split(",")),
        ("3. Status", 'status.replace("Dry", "Needs Irrigation")', status.replace("Dry", "Needs Irrigation")),
        ("4. Pest Count", 'report.count("Pest")', report.count("Pest")),
        ("5. Valid Farm ID", 'farm_id.startswith("FRM")', obj.farm_id.startswith("FRM")),
        ("6. Soil Report", "soil.strip()", soil.strip()),
        ("7. Seasonal Report", '", ".join(crops)', ", ".join(crops)),
        ("8. Alphanumeric", "code.isalnum()", code.isalnum()),
        ("9. Weather Words", "len(weather.split())", len(weather.split())),
        ("10. Crop Position", 'recommendation.lower().find("sugarcane")', recommendation.lower().find("sugarcane")),
    ]


def run_demo():
    """My Exp 3 main program."""
    print("A. STRING HANDLING")
    obj = CropMonitoring("FRM1001", "Karnataka", "sugarcane")
    obj.display()
    obj.monitor(38)
    for label, _expr, result in string_report():
        print(f"{label}:", result)

    print("\nB. INHERITANCE")
    print("1. Farm -> CropMonitoring")
    obj.display()
    obj.monitor(38)

    print("\n2. Multilevel Inheritance")
    a = CropHealthAnalyzer()
    a.sensor_data()
    a.soil_data()
    a.analyze()

    print("\n3. Hierarchical Inheritance")
    WheatFarm("FRM2001", "Maharashtra").irrigation()
    RiceFarm("FRM2002", "Karnataka").irrigation()

    print("\n4. Multiple Inheritance")
    s = SmartFarm()
    s.weather()
    s.soil()
    s.advice()

    print("\n5. Method Overriding")
    SugarcaneFarm("FRM3001", "Karnataka").irrigation()
    CottonFarm("FRM3002", "Maharashtra").irrigation()
