"""Validate shared settings for setup, options and stored entry data."""
import math
from .const import DEFAULTS
from .scheduling import migrate_config


def validate(config):
    config = {**DEFAULTS, **migrate_config(config)}
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
        for key in ("target",):
            if not math.isfinite(float(room[key])) or not 5 <= room[key] < config["max_temperature"]:
                raise ValueError("Room targets must be below the safety limit")
    schedule_ids=set()
    for binding in config["schedules"]:
        if binding["id"] in schedule_ids or not binding["name"].strip():
            raise ValueError("Invalid schedule name or ID")
        schedule_ids.add(binding["id"])
        if not binding.get("weekly") and not str(binding.get("entity_id","")).startswith("schedule."):
            raise ValueError("Select a native Schedule helper")
        if binding["source"] not in {"Auto","Average",*ids}:
            raise ValueError("Schedule refers to a missing room")
        if not math.isfinite(float(binding["target"])) or not 5<=binding["target"]<config["max_temperature"]:
            raise ValueError("Invalid schedule target")
        if binding["data_temperature_unit"] not in ("°C","°F") or not 0<=binding["priority"]<=100:
            raise ValueError("Invalid schedule settings")
    if config["sleep_room"] and config["sleep_room"] not in ids:
        raise ValueError("Sleep room no longer exists")
    if max(config[k] for k in ("away_temperature", "boost_temperature", "sleep_temperature")) >= config["max_temperature"]:
        raise ValueError("Preset targets must be below safety limit")
    return config
