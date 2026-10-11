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
from .scheduling import windows, choose

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
        self.segments = {r["id"]: 0 for r in self.plants}
        self.training_valid = {r["id"]: False for r in self.plants}
        self.models, self.learning_status, self.targets = {}, {}, {}
        self.comfort_temperature = self.config["comfort_temperature"]
        self.active_source = "Average"
        self.auto_room = None
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
        self.schedule_cache, self.schedule_status = {}, {}
        self.schedule_plans = []
        self.last_schedule_refresh = 0.0
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
        previous = saved.get("comfort_temperature")
        if previous is None:
            previous = next((self.targets[r["id"]] for r in self.rooms if r["id"] in self.targets), self.comfort_temperature)
        if isinstance(previous,(int,float)) and math.isfinite(previous) and 5 <= previous < self.config["max_temperature"]:
            self.comfort_temperature = previous
        now = dt_util.utcnow().timestamp()
        for r in self.plants:
            rid = r["id"]
            if saved.get("signatures", {}).get(rid) != self.signature(r):
                continue  # sensor/actuator changes invalidate plant history and learned gains
            try:
                model_data = saved.get("models",{}).get(rid)
                if model_data:
                    model = ThermalModel(**model_data)
                    if all(math.isfinite(v) for v in asdict(model).values()) and 0.05 <= model.heat_rate <= 10 and 0.002 <= model.loss_rate <= 0.5 and 0 <= model.delay <= 10800 and now-model.fitted_at < 14*86400:
                        self.models[rid] = model
                for row in saved.get("samples", {}).get(rid, []):
                    sample = Sample(**row)
                    if all(math.isfinite(v) for v in asdict(sample).values()) and now-14*86400 <= sample.time <= now:
                        self.samples[rid].append(sample)
            except (KeyError, TypeError, ValueError):
                self.models.pop(rid, None)
            self.segments[rid] = max((s.segment for s in self.samples[rid]), default=0) + 1
            if rid in self.models and r["tuning_mode"] == "auto":
                self.pids[rid].tune(*self.models[rid].gains(self.config["pwm_seconds"]))
                self.applied[rid] = self.models[rid].fitted_at
        entities = {self.config["heater"], self.config["outdoor_sensor"], self.config["home_sensor"]}
        entities.update(s["entity_id"] for s in self.config["schedules"])
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
        if event.data.get("entity_id","").startswith("schedule."):
            self.last_schedule_refresh = 0.0
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

    async def refresh_schedules(self,now):
        if now-self.last_schedule_refresh<60:
            return
        self.last_schedule_refresh=now
        for binding in self.config["schedules"]:
            eid=binding["entity_id"]
            if not eid:
                self.schedule_status[binding["id"]]="Migrated weekly schedule; connect a Schedule helper to edit times"
                continue
            state=self.hass.states.get(eid)
            if not state or state.state not in ("on","off"):
                self.schedule_cache.pop(eid,None)
                self.schedule_status[binding["id"]]="Schedule helper unavailable"
                continue
            try:
                async with asyncio.timeout(5):
                    response=await self.hass.services.async_call("schedule","get_schedule",
                        {"entity_id":eid},blocking=True,return_response=True)
                weekly=response[eid]
                self.schedule_cache[eid]=weekly
                self.schedule_status[binding["id"]]="Connected"
            except (HomeAssistantError,TimeoutError,KeyError,TypeError):
                self.schedule_cache.pop(eid,None)
                self.schedule_status[binding["id"]]="Could not read Schedule helper"

    def plan_schedules(self,now,valid,scores,away):
        if away or self.preset=="boost":
            self.schedule_plans=[]
            return []
        local=dt_util.as_local(dt_util.utc_from_timestamp(now))
        plans=[]
        for binding in self.config["schedules"]:
            weekly=binding.get("weekly") if not binding["entity_id"] else self.schedule_cache.get(binding["entity_id"])
            if weekly is None:
                continue
            if binding["entity_id"]:
                state=self.hass.states.get(binding["entity_id"])
                if not state or state.state not in ("on","off"):
                    continue  # never run cached blocks from an unavailable helper
            try:
                candidates=windows(binding,weekly,local,self.rooms,self.config["max_temperature"])
                candidates=sorted((w for w in candidates if w.end>now),key=lambda w:w.start)
                upcoming=next((w for w in candidates if w.start>now),None)
                for window in candidates:
                    if window.start>now+self.config["max_preheat_minutes"]*60 and window is not upcoming:
                        continue
                    selection=weights(scores,valid,selected=window.source,previous=self.auto_room)
                    temperature=sum(self.room_data[rid]["temperature"]*weight for rid,weight in selection.items()) if selection else None
                    model=self.model(next(iter(selection)),now) if window.source=="Auto" and len(selection)==1 and sum(scores.get(rid,0) for rid in valid)>=0.05 else self.model(window.source,now) if window.source not in ("Auto","Average") else (
                        self.model(AVERAGE,now) if len(valid)==len(self.rooms) and (window.source=="Average" or sum(scores.get(rid,0) for rid in valid)<0.05) else None)
                    prediction=(deadline_plan(now,window.start,window.end-window.start,temperature,
                        window.target,model,self.outdoor,self.config["fallback_heat_rate"],self.config["max_preheat_minutes"]*60)
                        if temperature is not None else {"lead_seconds":0,"reachable":False,"confidence":"input unavailable"})
                    in_block=window.start<=now<window.end
                    preheating=(not in_block and window.preheat and temperature is not None and
                                temperature<window.target and window.start-prediction["lead_seconds"]<=now<window.start)
                    plans.append({**prediction,"active":in_block or preheating,"phase":"active" if in_block else "preheat",
                        "binding_id":window.binding_id,"entity_id":window.entity_id,"name":window.name,
                        "source":window.source,"target":window.target,"start":window.start,"end":window.end,
                        "priority":window.priority})
            except (ValueError,TypeError,KeyError,OverflowError):
                self.schedule_status[binding["id"]]="Invalid schedule block data"
        self.schedule_plans=plans
        return choose(plans)

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
            await self.refresh_schedules(now)
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
                scores[rid] = self.occupancy[rid].moving_average(occupied, dt,
                    {"fast":600,"medium":1800,"slow":3600}[self.config["reaction_time"]])
                target = self.comfort_temperature
                if away:
                    target = self.config["away_temperature"]
                elif self.preset == "sleep":
                    target = self.config["sleep_temperature"]
                elif self.preset == "boost":
                    target = self.config["boost_temperature"]
                self.room_data[rid] = {"temperature": temperature, "target": target,
                    "occupancy": scores[rid], "occupied": occupied, "schedule": {"active":False},
                    "excluded_sensors": [e for e,v in values.items() if v is None],
                    "occupancy_unavailable": [e for e,s in zip(room["occupancy_sensors"],states) if not s or s.state not in ("on", "off")]}
                if temperature is not None:
                    valid.append(rid)
            source = self.source
            auto_selection = weights(scores,valid,previous=self.auto_room)
            self.auto_room = next(iter(auto_selection)) if len(auto_selection)==1 else None
            if self.preset == "sleep" and self.config["sleep_room"] and not away:
                source = self.config["sleep_room"]
            scheduled=self.plan_schedules(now,valid,scores,away)
            scheduled_rooms=[]
            if scheduled:
                if all(p["source"] not in ("Auto","Average") for p in scheduled):
                    scheduled_rooms=[p["source"] for p in scheduled if p["source"] in valid]
                    for plan in scheduled:
                        self.room_data[plan["source"]]["target"]=plan["target"]
                        self.room_data[plan["source"]]["schedule"]=plan
                else:
                    plan=scheduled[0]
                    source=plan["source"]
                    for rid in self.room_data:
                        if source in ("Auto","Average") or source==rid:
                            self.room_data[rid]["target"]=plan["target"]
                            self.room_data[rid]["schedule"]=plan
            selected = weights(scores, valid, average=away or self.preset == "boost",
                               selected="Average" if away or self.preset == "boost" else source,previous=self.auto_room)
            if scheduled and all(p["source"] not in ("Auto","Average") for p in scheduled):
                selected = {rid: 1/len(scheduled_rooms) for rid in scheduled_rooms}
            average_control = not scheduled_rooms and (away or self.preset == "boost" or source == "Average" or
                              source == "Auto" and sum(scores.get(rid,0) for rid in valid) < 0.05)
            self.active_source = "Average" if average_control and selected else ", ".join(r["name"] for r in self.rooms if r["id"] in selected) if selected else "Unavailable"
            self.current_temperature = sum(self.room_data[rid]["temperature"] * w for rid,w in selected.items()) if selected else None
            self.target_temperature = sum(self.room_data[rid]["target"] * w for rid,w in selected.items()) if selected else self.comfort_temperature
            reason = "Away average" if away else ("Schedule preheat" if any(p["phase"]=="preheat" for p in scheduled)
                else "Scheduled comfort") if scheduled else "Room control"
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
            if scheduled_rooms and not forced:
                self.duty = max(duties.get(rid, 0) for rid in scheduled_rooms)
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
                for plant in self.plants:
                    rid = plant["id"]
                    usable = self.actual is not None and self.outdoor is not None and (
                        len(valid) == len(self.rooms) if rid == AVERAGE else rid in valid)
                    if not usable and self.training_valid[rid]:
                        self.segments[rid] += 1
                    self.training_valid[rid] = usable
                    if usable:
                        self.samples[rid].append(Sample(now,self.room_data[rid]["temperature"],
                            self.outdoor,float(self.actual),self.segments[rid]))
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
        return {"preset": self.preset, "source": self.source, "comfort_temperature":self.comfort_temperature,
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
