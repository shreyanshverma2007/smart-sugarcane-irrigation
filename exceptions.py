"""
exceptions.py
-------------
Exp 5 : Exception Handling
    * A hierarchy of user-defined exceptions (all inherit from IrrigationError)
    * Helper functions that convert bad user input into meaningful errors
      (try / except / raise ... from ...)
"""


class IrrigationError(Exception):
    """Base class for every custom error in this project."""


class InvalidPlotDataError(IrrigationError):
    """Raised when plot details entered by the user are not valid."""


class DuplicatePlotError(InvalidPlotDataError):
    """Raised when a plot with the same name already exists on the farm."""


class WeatherDataError(IrrigationError):
    """Raised when weather values are outside a realistic range."""


class DatabaseError(IrrigationError):
    """Wraps sqlite3 errors so the GUI only has to catch one type."""


class SensorError(IrrigationError):
    """Raised by the (simulated) soil-moisture sensor when a reading fails."""

    def __init__(self, plot_id, message):
        super().__init__(message)
        self.plot_id = plot_id


def parse_positive_float(text, field):
    """Convert text from an Entry box into a float > 0, or raise an error."""
    try:
        value = float(str(text).strip())
    except ValueError:
        raise InvalidPlotDataError(
            f"{field} must be a number (you entered '{text}')."
        ) from None
    if value <= 0:
        raise InvalidPlotDataError(f"{field} must be greater than zero.")
    return value


def parse_float_in_range(text, field, low, high, error_cls=WeatherDataError):
    """Convert text into a float that must lie between low and high."""
    try:
        value = float(str(text).strip())
    except ValueError:
        raise error_cls(f"{field} must be a number (you entered '{text}').") from None
    if not low <= value <= high:
        raise error_cls(f"{field} must be between {low} and {high}.")
    return value
