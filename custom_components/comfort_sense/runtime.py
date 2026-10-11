"""HA boundary: reads observations, persists learning and arbitrates one heat relay."""
import asyncio
from collections import deque
from dataclasses import asdict
from datetime import timedelta
import logging
import math

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import AVERAGE, DOMAIN
from .control import Occupancy, PID, Relay, celsius, deadline_plan, presence, weights
from .learning import Sample, ThermalModel, identify
from .settings import validate

_LOGGER = logging.getLogger(__name__)


class Runtime:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = validate({**entry.data, **entry.options})
        self.rooms = self.config["rooms"]
        average = {"id": AVERAGE, "name": "Average",
                   "tuning_mode": self.config["average_tuning_mode"],
                   **{k:self.config[f"average_{k}"] for k in ("kp", "ki", "kd")}}
        self.plants = self.rooms + [average]
        self.pids = {r["id"]: PID(*(r[k] for k in ("kp", "ki", "kd"))) for r in self.plants}
        self.occupancy = {r["id"]: Occupancy() for r in self.rooms}
        self.samples = {r["id"]: deque(maxlen=40320) for r in self.plants}  # 14 days @ 30sec
        self.models, self.learning_status, self.targets = {}, {}, {}
        self.applied = {}
        self.relay = Relay(self.config["pwm_seconds"], self.config["min_on_seconds"], self.config["min_off_seconds"])
        self.mode, self.preset, self.source = "off", "comfort", "Auto"
        self.boost_until = 0.0
        self.absent_since = None
        self.last_tick = self.last_sample = self.last_fit = self.last_save = 0.0
        self.outdoor = None
        self.actual = None
        self.duty = 0.0
        self.proposed = False
        self.reason = "Starting"
        self.current_temperature = self.target_temperature = None
        self.room_data = {}
        self.listeners, self.unsubs = [], []
        self.lock = asyncio.Lock()
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.closed = False

    async def start(self):
        saved = await self.store.async_load() or {}
        # Always start off; never restore an energized output or stale occupancy.
        self.preset = saved.get("preset", "comfort")
        if self.preset not in ("comfort", "away", "sleep"):
            self.preset = "comfort"
        self.source = saved.get("source", "Auto")
        if self.source not in ["Auto", "Average", *(r["id"] for r in self.rooms)]:
            self.source = "Auto"
        self.targets = {k: float(v) for k, v in saved.get("targets", {}).items()
                        if k in self.pids and math.isfinite(float(v)) and 5 <= float(v) < self.config["max_temperature"]}
        now = dt_util.utcnow().timestamp()
        for r in self.plants:
            rid = r["id"]
            if saved.get("signatures", {}).get(rid) != self.signature(r):
                continue  # sensor/actuator changes invalidate plant history and learned gains
            try:
                model = ThermalModel(**saved["models"][rid])
                if all(math.isfinite(v) for v in asdict(model).values()) and 0.05 <= model.heat_rate <= 10 and 0.002 <= model.loss_rate <= 0.5 and 0 <= model.delay <= 10800 and now-model.fitted_at < 14*86400:
                    self.models[rid] = model
                for row in saved.get("samples", {}).get(rid, []):
                    sample = Sample(**row)
                    if all(math.isfinite(v) for v in asdict(sample).values()) and now-14*86400 <= sample.time <= now:
                        self.samples[rid].append(sample)
            except (KeyError, TypeError, ValueError):
                self.models.pop(rid, None)
            if rid in self.models and r["tuning_mode"] == "auto":
                self.pids[rid].tune(*self.models[rid].gains(self.config["pwm_seconds"]))
                self.applied[rid] = self.models[rid].fitted_at
        entities = {self.config["heater"], self.config["outdoor_sensor"], self.config["home_sensor"]}
        for r in self.rooms:
            entities.update(r["temperature_sensors"] + r["occupancy_sensors"])
        self.unsubs.append(async_track_state_change_event(self.hass, list(entities - {""}), self.changed))
        self.unsubs.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=30)))
        await self.tick()

    def signature(self, room):
        sensors = sorted(room["temperature_sensors"]) if room["id"] != AVERAGE else sorted([r["id"],sorted(r["temperature_sensors"])] for r in self.rooms)
        return [self.config["heater"], self.config["outdoor_sensor"], sensors]

    @callback
    def changed(self, event):
        self.hass.async_create_task(self.tick())

    @callback
    def notify(self):
        for listener in list(self.listeners):
            listener()

    @callback
    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def numeric_temperature(self, entity_id, now):
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        # last_reported includes identical readings on supported HA versions.
        stamp = getattr(state, "last_reported", state.last_updated).timestamp()
        if now - stamp > self.config["sensor_timeout_minutes"] * 60:
            return None
        try:
            return celsius(state.state, state.attributes.get("unit_of_measurement"))
        except (ValueError, TypeError):
            return None

    def home(self):
        state = self.hass.states.get(self.config["home_sensor"])
        return presence(state.state if state else None)

    def morning(self, room, now, temperature, away):
        if away or not room["morning_enabled"] or self.preset in ("away", "boost"):
            return {"active": False}
        local = dt_util.as_local(dt_util.utc_from_timestamp(now))
        hour, minute = map(int, room["morning_time"].split(":"))
        plans = []
        # Yesterday can still be within its hold period; tomorrow may preheat before midnight.
        for offset in (-1, 0, 1):
            date = local.date() + timedelta(days=offset)
            if date.weekday() not in room["morning_days"]:
                continue
            candidate = local.replace(year=date.year, month=date.month, day=date.day,
                                      hour=hour, minute=minute, second=0, microsecond=0, fold=0)
            # Resolve nonexistent wall times by round-tripping through UTC (spring DST).
            deadline = dt_util.as_local(dt_util.as_utc(candidate)).timestamp()
            plan = deadline_plan(now, deadline, room["morning_duration"] * 60,
                                 temperature, room["morning_target"], self.model(room["id"], now),
                                 self.outdoor, self.config["fallback_heat_rate"],
                                 self.config["max_preheat_minutes"] * 60)
            plans.append(plan)
        return next((p for p in plans if p["active"]), min(plans, key=lambda p: abs(p["deadline"]-now)) if plans else {"active": False})

    def model(self, rid, now):
        model = self.models.get(rid)
        return model if model and now - model.fitted_at < 14*86400 else None

    async def tick(self, _now=None):
        async with self.lock:
            if self.closed:
                return
            now = dt_util.utcnow().timestamp()
            dt = max(0, min(120, now - self.last_tick)) if self.last_tick else 30
            if self.last_tick and dt < 1:
                return
            self.last_tick = now
            state = self.hass.states.get(self.config["heater"])
            self.actual = (state.state == "on") if state and state.state in ("on", "off") else None
            self.outdoor = self.numeric_temperature(self.config["outdoor_sensor"], now)
            home = self.home()
            if home is False:
                self.absent_since = self.absent_since if self.absent_since is not None else now
            else:
                self.absent_since = None
            auto_away = self.absent_since is not None and now-self.absent_since >= self.config["away_delay_minutes"]*60
            if self.preset == "boost" and now >= self.boost_until:
                self.preset = "comfort"
            away = self.preset == "away" or auto_away
            self.room_data = {}
            valid, scores = [], {}
            high_temperature = False
            for room in self.rooms:
                rid = room["id"]
                values = {e: self.numeric_temperature(e, now) for e in room["temperature_sensors"]}
                temperatures = [v for v in values.values() if v is not None]
                high_temperature |= any(v >= self.config["max_temperature"] for v in temperatures)
                # Median rejects a single outlier when three or more sensors are available.
                temperatures.sort()
                size = len(temperatures)
                temperature = (temperatures[(size-1)//2] + temperatures[size//2])/2 if size else None
                states = [self.hass.states.get(e) for e in room["occupancy_sensors"]]
                occupied = any(s and s.state == "on" for s in states)
                scores[rid] = self.occupancy[rid].update(occupied, dt,
                    self.config["occupancy_rise_minutes"]*60, self.config["occupancy_decay_minutes"]*60)
                target = self.targets.get(rid, room["target"])
                if away:
                    target = self.config["away_temperature"]
                elif self.preset == "sleep":
                    target = self.config["sleep_temperature"]
                elif self.preset == "boost":
                    target = self.config["boost_temperature"]
                plan = self.morning(room, now, temperature, away) if temperature is not None else {"active": False}
                if plan["active"]:
                    target = room["morning_target"]
                self.room_data[rid] = {"temperature": temperature, "target": target,
                    "occupancy": scores[rid], "occupied": occupied, "morning": plan,
                    "excluded_sensors": [e for e,v in values.items() if v is None],
                    "occupancy_unavailable": [e for e,s in zip(room["occupancy_sensors"],states) if not s or s.state not in ("on", "off")]}
                if temperature is not None:
                    valid.append(rid)
            source = self.source
            if self.preset == "sleep" and self.config["sleep_room"] and not away:
                source = self.config["sleep_room"]
            selected = weights(scores, valid, average=away or self.preset == "boost",
                               selected="Average" if away or self.preset == "boost" else source)
            morning_rooms = [rid for rid in valid if self.room_data[rid]["morning"]["active"]]
            if morning_rooms and not away:
                # Each scheduled room has standing priority, independent of nighttime occupancy.
                selected = {rid: 1/len(morning_rooms) for rid in morning_rooms}
            average_control = not morning_rooms and (away or self.preset == "boost" or source == "Average" or
                              source == "Auto" and sum(scores.get(rid,0) for rid in valid) < 0.05)
            self.current_temperature = sum(self.room_data[rid]["temperature"] * w for rid,w in selected.items()) if selected else None
            self.target_temperature = sum(self.room_data[rid]["target"] * w for rid,w in selected.items()) if selected else None
            reason = "Away average" if away else "Morning preheat" if morning_rooms else "Room control"
            forced = self.mode == "off" or not selected or high_temperature or self.actual is None
            if self.mode == "off": reason = "Off"
            elif high_temperature: reason = "Safety temperature limit"
            elif self.actual is None: reason = "Heater unavailable"
            elif not selected: reason = "Selected room has no valid temperature" if source not in ("Auto", "Average") else "No valid temperatures"
            duties = {}
            for room in self.rooms:
                rid = room["id"]
                row = self.room_data[rid]
                row["weight"] = selected.get(rid, 0)
                pid = self.pids[rid]
                if row["temperature"] is None:
                    pid.previous = None
                    pid.integral = 0
                    row["duty"] = 0
                    continue
                model = self.model(rid, now)
                if not model and rid in self.applied:
                    pid.tune(*(room[k] for k in ("kp", "ki", "kd")))
                    self.applied.pop(rid)
                feedforward = model.feedforward(row["target"], self.outdoor) if model and self.outdoor is not None and self.applied.get(rid) == model.fitted_at else 0
                duty = pid.update(row["temperature"], row["target"], dt, feedforward,
                                  active=not forced and not average_control and selected.get(rid,0)>0.01,
                                  constrained=self.actual is not None and self.proposed != self.actual)
                # Coast prediction from measured slope anticipates delayed heat already in transit.
                coast = row["temperature"] + max(0, pid.derivative) * (model.delay if model else 600)
                if coast >= row["target"] + 0.3:
                    duty = 0.0
                    pid.integral = min(0, pid.integral)
                duties[rid] = row["duty"] = duty
                row["gains"] = {"kp": pid.kp, "ki": pid.ki, "kd": pid.kd}
                row["model"] = model.to_dict() if model else None
                row["tuning_mode"] = room["tuning_mode"]
                row["recommended_gains"] = dict(zip(("kp", "ki", "kd"), model.gains(self.config["pwm_seconds"]))) if model else None
                row["tuning_status"] = self.learning_status.get(rid, "Collecting")
                row["tuning_applied"] = bool(model and self.applied.get(rid) == model.fitted_at)
            self.duty = sum(selected[rid] * duties.get(rid, 0) for rid in selected) if not forced else 0
            average_pid = self.pids[AVERAGE]
            average_model = self.model(AVERAGE, now) if len(valid) == len(self.rooms) else None
            average_temperature = sum(self.room_data[rid]["temperature"] for rid in valid)/len(valid) if valid else None
            average_target = sum(self.room_data[rid]["target"] for rid in valid)/len(valid) if valid else None
            # Average membership changes are source changes; discard derivative and integral history.
            membership = tuple(sorted(valid))
            if membership != getattr(self, "average_membership", None):
                average_pid.previous = None
                average_pid.derivative = average_pid.integral = 0
                self.average_membership = membership
            if not average_model and AVERAGE in self.applied:
                average_pid.tune(*(self.config[f"average_{k}"] for k in ("kp", "ki", "kd")))
                self.applied.pop(AVERAGE)
            elif average_model and self.config["average_tuning_mode"] == "auto" and self.applied.get(AVERAGE) != average_model.fitted_at:
                average_pid.tune(*average_model.gains(self.config["pwm_seconds"]))
                self.applied[AVERAGE] = average_model.fitted_at
            average_duty = 0.0
            if average_temperature is not None:
                feedforward = average_model.feedforward(average_target,self.outdoor) if average_model and self.outdoor is not None and self.applied.get(AVERAGE) == average_model.fitted_at and len(valid) == len(self.rooms) else 0
                average_duty = average_pid.update(average_temperature,average_target,dt,feedforward,
                    active=not forced and average_control,
                    constrained=self.actual is not None and self.proposed != self.actual)
                coast = average_temperature + max(0,average_pid.derivative)*(average_model.delay if average_model else 600)
                if coast >= average_target+0.3:
                    average_duty = 0
                    average_pid.integral = min(0,average_pid.integral)
                if average_control and not forced:
                    self.duty = average_duty
            self.room_data[AVERAGE] = {"temperature":average_temperature,"target":average_target,
                "duty":average_duty,"active":average_control,"gains":{k:getattr(average_pid,k) for k in ("kp","ki","kd")},
                "tuning_mode":self.config["average_tuning_mode"],"model":average_model.to_dict() if average_model else None,
                "recommended_gains":dict(zip(("kp","ki","kd"),average_model.gains(self.config["pwm_seconds"]))) if average_model else None,
                "tuning_status":self.learning_status.get(AVERAGE,"Collecting"),
                "tuning_applied":bool(average_model and self.applied.get(AVERAGE) == average_model.fitted_at),
                "complete_membership":len(valid) == len(self.rooms)}
            # A deadline is a max-demand objective. It is still bounded by safety/cycling.
            if morning_rooms and not forced:
                self.duty = max(duties.get(rid, 0) for rid in morning_rooms)
            self.proposed = self.relay.decide(now, self.duty, bool(self.actual), force_off=forced)
            self.reason = reason
            if not self.config["shadow"]:
                # Reassert at every tick, both for retry and for ESP relay watchdog keepalive.
                try:
                    await self.hass.services.async_call("switch", "turn_on" if self.proposed else "turn_off",
                        {"entity_id": self.config["heater"]}, blocking=True)
                except HomeAssistantError as err:
                    self.reason = "Heater command failed"
                    _LOGGER.warning("Heater command failed: %s", err)
            if now-self.last_sample >= 29:
                self.last_sample = now
                for rid in valid:
                    if self.actual is not None and self.outdoor is not None:
                        self.samples[rid].append(Sample(now, self.room_data[rid]["temperature"], self.outdoor, float(self.actual)))
                if len(valid) == len(self.rooms) and self.actual is not None and self.outdoor is not None:
                    self.samples[AVERAGE].append(Sample(now,average_temperature,self.outdoor,float(self.actual)))
                if now-self.last_save >= 300:
                    self.last_save = now
                    self.save_later()
            if now-self.last_fit >= 21600:
                self.last_fit = now
                # The executor receives immutable snapshots, never mutable HA state.
                self.hass.async_create_task(self.fit())
            self.notify()

    async def fit(self):
        snapshots = {rid: list(data) for rid, data in self.samples.items()}
        for rid, data in snapshots.items():
            model, status = await self.hass.async_add_executor_job(identify, data, self.models.get(rid))
            if self.closed:
                return
            self.learning_status[rid] = status
            if model:
                self.models[rid] = model
                room = next(r for r in self.plants if r["id"] == rid)
                if room["tuning_mode"] == "auto":
                    self.pids[rid].tune(*model.gains(self.config["pwm_seconds"]))
                    self.applied[rid] = model.fitted_at
        self.save_later()
        self.notify()

    def saved(self):
        return {"preset": self.preset, "source": self.source, "targets": self.targets,
                "models": {k:v.to_dict() for k,v in self.models.items()},
                "samples": {k:[asdict(s) for s in v] for k,v in self.samples.items()},
                "signatures": {r["id"]: self.signature(r) for r in self.plants}}

    @callback
    def save_later(self):
        self.store.async_delay_save(self.saved, 30)

    async def change(self, **changes):
        for key, value in changes.items():
            setattr(self, key, value)
        self.last_tick = 0  # explicit user changes take effect immediately
        self.save_later()
        await self.tick()

    async def stop(self):
        async with self.lock:
            self.closed = True
            for unsub in self.unsubs:
                unsub()
            self.unsubs.clear()
            if not self.config["shadow"]:
                try:
                    await self.hass.services.async_call("switch", "turn_off",
                        {"entity_id": self.config["heater"]}, blocking=True)
                except HomeAssistantError:
                    _LOGGER.warning("Could not confirm heater off during unload")
            await self.store.async_save(self.saved())
