"""UI temperature conversion; stored settings and control remain Celsius."""
import math


def display_temperature(value, unit):
    return float(value)*1.8+32 if unit == "°F" else float(value)


def native_temperature(value, unit):
    value=float(value)
    if not math.isfinite(value):
        raise ValueError("Invalid temperature")
    return (value-32)/1.8 if unit == "°F" else value


def display_rate(value, unit):
    return float(value)*1.8 if unit == "°F" else float(value)


def native_rate(value, unit):
    return float(value)/1.8 if unit == "°F" else float(value)
