"""Exp 2 - Implement Constructors and Lists (my lab code)."""


class IrrigationRecord:

    def __init__(self, day, moisture, temperature, rainfall, recommendation):
        self.day = day
        self.moisture = moisture
        self.temperature = temperature
        self.rainfall = rainfall
        self.recommendation = recommendation

    def display(self):
        print(f"{self.day:2}     {self.moisture:2}%        {self.temperature}°C        "
              f"{self.rainfall} mm        {self.recommendation}")


# Sample data for 30 days
moisture = [42, 45, 48, 50, 46, 43, 40, 38, 41, 44,
            47, 49, 51, 53, 55, 52, 50, 48, 46, 44,
            43, 42, 45, 47, 49, 51, 54, 56, 53, 50]

temperature = [31, 32, 33, 34, 35, 34, 33, 32, 31, 30,
               31, 32, 33, 34, 35, 36, 35, 34, 33, 32,
               31, 30, 31, 32, 33, 34, 35, 36, 35, 34]

rainfall = [0, 0, 5, 10, 0, 0, 15, 20, 5, 0,
            0, 10, 0, 5, 0, 0, 25, 10, 0, 0,
            5, 0, 0, 15, 20, 5, 0, 0, 10, 0]


def get_advice(moisture_value, rainfall_value):
    """The rule from my Exp 2 loop."""
    if moisture_value < 45:
        return "Irrigate Today"
    elif rainfall_value > 15:
        return "No Irrigation"
    else:
        return "Monitor Soil"


def build_records():
    """Add 30 records into a list (same loop as Exp 2)."""
    records = []
    for i in range(30):
        advice = get_advice(moisture[i], rainfall[i])
        records.append(
            IrrigationRecord(
                i + 1,
                moisture[i],
                temperature[i],
                rainfall[i],
                advice
            )
        )
    return records


def find_day(records, day):
    """Search a record by day number (returns None if it is not in the list)."""
    for record in records:
        if record.day == day:
            return record
    return None


def run_demo():
    """My Exp 2 main program."""
    records = build_records()

    # Display all records
    print("\n--------------- 30 DAYS IRRIGATION DATA ---------------")
    print("Day   Moisture   Temperature   Rainfall   Recommendation")
    print("-------------------------------------------------------")
    for record in records:
        record.display()

    # Update Day 10 moisture
    records[9].moisture = 60
    records[9].recommendation = "No Irrigation"
    print("\nDay 10 Updated Successfully")

    # Delete Day 30 record
    records.pop()
    print("Day 30 Record Deleted Successfully")

    # Search Day 15
    print("\nSearch Result (Day 15)")
    print("Day   Moisture   Temperature   Rainfall   Recommendation")
    records[14].display()
