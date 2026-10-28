"""Shared integration constants."""
DOMAIN = "comfort_sense"
AVERAGE = "_average"
PLATFORMS = ["climate", "sensor", "number", "select"]
DEFAULTS = {
    "name": "ComfortSense", "shadow": True, "outdoor_sensor": "",
    "home_sensor": "", "away_temperature": 18.0, "boost_temperature": 22.0,
    "comfort_temperature": 21.0, "reaction_time": "medium",
    "occupancy_margin": 30.0,
    "boost_minutes": 60, "sleep_temperature": 18.0, "sleep_room": "",
    "occupancy_rise_minutes": 5, "occupancy_decay_minutes": 30,
    "away_delay_minutes": 20, "sensor_timeout_minutes": 180,
    "min_on_seconds": 300, "min_off_seconds": 300, "pwm_seconds": 1200,
    "max_temperature": 28.0, "max_preheat_minutes": 240,
    "fallback_heat_rate": 0.5,
    "room_buffer": 2.0,
    "morning_enabled": False, "alarm_sensors": [], "alarm_owners": {},
    "morning_target": 20.0, "morning_source": "Average", "morning_duration": 60,
    "alarm_window_start": "03:00", "alarm_window_end": "12:00",
    "average_tuning_mode": "auto", "average_kp": 0.2,
    "average_ki": 0.000035, "average_kd": 0.0,
    "schedules": [],
}
