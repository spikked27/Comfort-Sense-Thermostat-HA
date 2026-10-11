"""Validate shared settings for setup, options and stored entry data."""
import math
from .const import DEFAULTS


def validate(config):
    config = {**DEFAULTS, **config}
    if not str(config.get("heater", "")).startswith("switch."):
        raise ValueError("A switch heater is required")
    for key, low, high in [
        ("away_temperature", 5, 27), ("boost_temperature", 5, 27),
        ("sleep_temperature", 5, 27), ("boost_minutes", 1, 240),
        ("occupancy_rise_minutes", 1, 60), ("occupancy_decay_minutes", 1, 180),
        ("away_delay_minutes", 0, 180), ("sensor_timeout_minutes", 5, 1440),
        ("min_on_seconds", 30, 3600), ("min_off_seconds", 30, 3600),
        ("pwm_seconds", 120, 7200), ("max_temperature", 10, 35),
        ("max_preheat_minutes", 15, 480), ("fallback_heat_rate", 0.1, 5),
        ("average_kp", 0, 2), ("average_ki", 0, 0.001), ("average_kd", 0, 3600),
    ]:
        v = float(config[key])
        if not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"Invalid {key}")
        config[key] = v
    if config["pwm_seconds"] < config["min_on_seconds"] + config["min_off_seconds"]:
        raise ValueError("PWM must cover minimum on and off periods")
    rooms = config.get("rooms", [])
    if config["average_tuning_mode"] not in ("manual", "auto"):
        raise ValueError("Choose manual or automatic average tuning")
    if not rooms or len(rooms) > 20:
        raise ValueError("Configure 1 to 20 rooms")
    ids, names = set(), set()
    for room in rooms:
        room.setdefault("tuning_mode", "manual")
        for key, default, high in [("kp", 0.2, 2), ("ki", 0.000035, 0.001), ("kd", 0.0, 3600)]:
            room.setdefault(key, default)
            if not math.isfinite(float(room[key])) or not 0 <= room[key] <= high:
                raise ValueError(f"Invalid room {key}")
        if room["tuning_mode"] not in ("manual", "auto"):
            raise ValueError("Choose manual or automatic room tuning")
        if room["id"] in ids or room["name"] in names or room["name"] in ("Auto", "Average"):
            raise ValueError("Room names must be unique")
        ids.add(room["id"])
        names.add(room["name"])
        if not room.get("temperature_sensors"):
            raise ValueError("Every room needs a temperature sensor")
        for key in ("target", "morning_target"):
            if not math.isfinite(float(room[key])) or not 5 <= room[key] < config["max_temperature"]:
                raise ValueError("Room targets must be below the safety limit")
        if not 1 <= room["morning_duration"] <= 240:
            raise ValueError("Invalid morning duration")
        hour, minute = map(int, room["morning_time"].split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid morning time")
        if any(day not in range(7) for day in room["morning_days"]):
            raise ValueError("Invalid weekday")
    if config["sleep_room"] and config["sleep_room"] not in ids:
        raise ValueError("Sleep room no longer exists")
    if max(config[k] for k in ("away_temperature", "boost_temperature", "sleep_temperature")) >= config["max_temperature"]:
        raise ValueError("Preset targets must be below safety limit")
    return config
