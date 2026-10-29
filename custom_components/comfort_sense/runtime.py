"""HA boundary: reads observations, persists learning and arbitrates one heat relay."""
import asyncio
from collections import deque
from copy import deepcopy
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
from .control import Occupancy, PID, Relay, RoomGuard, GroupForecast, celsius, deadline_plan, presence, weights
from .learning import Sample, ThermalModel, identify
from .settings import validate
from .scheduling import windows, choose
from .morning import MorningAlarms, ArrivalLearning
from .memory import MAX_BIAS, MAX_AGE, recovered_bias

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
        self.auto_members = ()
        self.group_pid = PID()
        self.group_members = ()
        self.group_data = {}
        self.guards = {r["id"]:RoomGuard() for r in self.rooms}
        self.cold_pids = {r["id"]:PID(*(r[k] for k in ("kp","ki","kd"))) for r in self.rooms}
        self.guard_data = {}
        self.applied = {}
        self.relay = Relay(self.config["pwm_seconds"], self.config["min_on_seconds"], self.config["min_off_seconds"])
        self.mode, self.preset, self.source = "off", "comfort", "Auto"
        self.boost_until = 0.0
        self.absent_since = None
        self.last_tick = self.last_sample = self.last_fit = self.last_save = 0.0
        self.force_tick = False
        self.outdoor = None
        self.actual = None
        self.duty = 0.0
        self.proposed = False
        self.reason = "Starting"
        self.current_temperature = self.target_temperature = None
        self.target_origin="Comfort preset"
        self.room_data = {}
        self.schedule_cache, self.schedule_status = {}, {}
        self.schedule_plans = []
        self.last_schedule_refresh = 0.0
        self.morning=MorningAlarms()
        self.arrivals=ArrivalLearning()
        self.preheat_latches={}
        self.listeners, self.unsubs = [], []
        self.lock = asyncio.Lock()
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.closed = False
        self.startup_pending=False
        self.pending_pid_memory=None
        self.memory_restore_status="No saved compensation"

    async def start(self):
        saved = await self.store.async_load() or {}
        # Restore user intent only, never an energized pulse or stale occupancy.
        self.mode=saved.get("mode","off") if saved.get("control_signature")==self.control_signature() else "off"
        if self.mode not in ("off","heat"):
            self.mode="off"
        self.startup_pending=self.mode=="heat"
        self.pending_pid_memory=saved.get("pid_memory") if self.mode=="heat" else None
        if self.pending_pid_memory is not None:
            self.memory_restore_status="Awaiting fresh control context"
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
        self.morning.restore(saved.get("morning",{}),now)
        if saved.get("signatures",{})=={r["id"]:self.signature(r) for r in self.plants}:
            self.arrivals.restore(saved.get("arrival_corrections",{}))
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
        entities.update(self.config["alarm_sensors"])
        entities.update(self.config["alarm_owners"].values())
        for r in self.rooms:
            entities.update(r["temperature_sensors"] + r["occupancy_sensors"])
        self.unsubs.append(async_track_state_change_event(self.hass, list(entities - {""}), self.changed))
        self.unsubs.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=30)))
        await self.tick()

    def signature(self, room):
        sensors = sorted(room["temperature_sensors"]) if room["id"] != AVERAGE else sorted([r["id"],sorted(r["temperature_sensors"])] for r in self.rooms)
        return [self.config["heater"], self.config["outdoor_sensor"], sensors]

    def control_signature(self):
        return [self.config["heater"],self.config["shadow"]]

    def primary_controller(self):
        members=sorted(r["id"] for r in self.rooms if self.room_data.get(r["id"],{}).get("weight",0)>0)
        if self.room_data.get(AVERAGE,{}).get("active"):
            return AVERAGE,self.pids[AVERAGE],members
        if self.group_data.get("active"):
            return "_group",self.group_pid,members
        if len(members)==1:
            return members[0],self.pids[members[0]],members
        return None,None,members

    def memory_context(self,key,pid,members,temperature,target,now):
        members=sorted(members)
        fresh=bool(members)
        entities=[]
        for room in self.rooms:
            if room["id"] in members:
                excluded=self.room_data.get(room["id"],{}).get("excluded_sensors",[])
                entities.extend(e for e in room["temperature_sensors"] if e not in excluded)
        if self.config["outdoor_sensor"]:
            entities.append(self.config["outdoor_sensor"])
        for eid in entities:
            state=self.hass.states.get(eid)
            stamp=getattr(state,"last_reported",getattr(state,"last_updated",None)) if state else None
            fresh &= bool(stamp and -5<=now-stamp.timestamp()<=MAX_AGE and state.state not in ("unknown","unavailable"))
        return {"time":now,"controller":key,"members":members,"source":self.source,"preset":self.preset,
            "signature":[self.control_signature(),[[r["id"],self.signature(r)] for r in sorted(self.rooms,key=lambda r:r["id"]) if r["id"] in members]],
            "temperature":temperature,"target":target,"outdoor":self.outdoor,"fresh":fresh,
            "gains":[pid.kp,pid.ki,pid.kd]}

    def restore_control_memory(self,key,pid,members,temperature,target,now,allowed):
        if self.pending_pid_memory is None or not allowed or not self.memory_inputs_ready(now):
            return
        bias,status=recovered_bias(self.pending_pid_memory,self.memory_context(key,pid,members,temperature,target,now))
        self.memory_restore_status=status
        self.pending_pid_memory=None
        if bias is not None:
            pid.integral=bias

    def memory_inputs_ready(self,now):
        """Defer validation while startup entities reconnect, without extending age."""
        saved=self.pending_pid_memory
        if saved is None:
            return False
        try:
            age=now-saved["time"]
            if not math.isfinite(age) or not 0<=age<=MAX_AGE:
                raise ValueError("expired")
            members=saved["members"]
            if not isinstance(members,list) or not members or not set(members)<={r["id"] for r in self.rooms}:
                raise ValueError("invalid members")
        except (KeyError,TypeError,ValueError,OverflowError):
            self.pending_pid_memory=None
            self.memory_restore_status="Saved compensation expired or invalid"
            return False
        entities=[self.config["heater"]]
        temperature_entities={eid for room in self.rooms if room["id"] in members for eid in room["temperature_sensors"]}
        temperature_entities.add(self.config["outdoor_sensor"])
        for room in self.rooms:
            if room["id"] in members:
                entities.extend(room["temperature_sensors"])
            if self.source=="Auto":
                entities.extend(room["occupancy_sensors"])
        if self.config["outdoor_sensor"]:
            entities.append(self.config["outdoor_sensor"])
        for eid in entities:
            state=self.hass.states.get(eid)
            if not state or state.state in ("unknown","unavailable") or state.attributes.get("restored"):
                self.memory_restore_status="Waiting for startup entities"
                return False
            if eid in temperature_entities and self.numeric_temperature(eid,now) is None:
                self.memory_restore_status="Waiting for valid startup temperatures"
                return False
            if eid==self.config["heater"]:
                continue
            stamp=getattr(state,"last_reported",getattr(state,"last_updated",None))
            if not stamp or not -5<=now-stamp.timestamp()<=MAX_AGE:
                self.memory_restore_status="Waiting for fresh startup reports"
                return False
        return True

    def pid_memory_snapshot(self):
        if self.mode=="heat" and isinstance(self.pending_pid_memory,dict):
            return deepcopy(self.pending_pid_memory)  # preserve the original timestamp
        key,pid,members=self.primary_controller()
        if self.mode!="heat" or pid is None or not pid.terms.get("active") or pid.ki<=0:
            return None
        context=self.memory_context(key,pid,members,self.current_temperature,self.target_temperature,self.last_tick)
        if not context["fresh"]:
            return None
        context["integral"]=max(-MAX_BIAS,min(MAX_BIAS,pid.integral))
        return context

    def limiting_condition(self):
        if self.reason not in ("Room control","Away average","Scheduled comfort","Schedule preheat"):
            return self.reason
        elapsed=self.last_tick-self.relay.changed if self.relay.changed is not None else 0
        if self.actual is False and not self.proposed and self.duty>0:
            return "Minimum off time" if elapsed<self.relay.min_off else "PWM off interval or accumulating minimum pulse"
        if self.actual is True and self.proposed and self.duty<=0:
            return "Minimum on time"
        _,pid,_=self.primary_controller()
        if pid and pid.output>0 and self.duty<=0:
            return "Predictive coast cutoff"
        return "None"

    def control_diagnostics(self):
        key,pid,members=self.primary_controller()
        return {"mode":self.mode,"preset":self.preset,"controller":key,"members":members,
                "terms_unit":"fraction of available heating duty","temperature_unit":"°C",
                "terms":dict(pid.terms,stored_integral=pid.integral) if pid else {},
                "requested_duty":self.duty,"proposed_relay_on":self.proposed,"observed_relay_on":self.actual,
                "limiting_condition":self.limiting_condition(),"restart_memory":self.memory_restore_status}

    def outdoor_compensation(self):
        """Explain the physical feedforward term without inventing a manual Ke."""
        key,pid,members=self.primary_controller()
        controllers=members if key=="_group" else [key] if key else []
        models=[self.model(rid,self.last_tick) for rid in controllers]
        learned=[model for rid,model in zip(controllers,models) if model and self.applied.get(rid)==model.fitted_at]
        manual=bool(controllers) and all((self.config["average_tuning_mode"] if rid==AVERAGE else
            next(room["tuning_mode"] for room in self.rooms if room["id"]==rid))=="manual" for rid in controllers)
        status=("No outdoor sensor" if not self.config["outdoor_sensor"] else "Outdoor reading unavailable" if self.outdoor is None
                else "Manual PID · compensation off" if manual else "Waiting for accepted model" if not learned
                else "Learned" if len(learned)==len(controllers) else "Partly learned")
        return {"method":"learned heat-loss feedforward","status":status,
            "coefficient":sum(model.loss_rate/model.heat_rate for model in learned)/len(controllers) if learned else None,
            "coefficient_unit":"duty fraction per °C","applied_duty_percent":round(pid.terms.get("feedforward",0)*100,2) if pid else 0,
            "active":bool(pid and pid.terms.get("active"))}

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
        if state is None or state.state in ("unknown", "unavailable") or state.attributes.get("restored"):
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
        local=dt_util.as_local(dt_util.utc_from_timestamp(now))
        alarm=self.morning.window(self.config,self.hass.states,now,local.tzinfo)
        self.schedule_status["morning_alarm"]=self.morning.status
        if away or self.preset=="boost":
            self.schedule_plans=[]
            self.preheat_latches.clear()
            return []
        plans=[]
        bindings=list(self.config["schedules"])
        if alarm:
            bindings.append({"id":"morning_alarm","entity_id":"","alarm_window":alarm})
        for binding in bindings:
            if "alarm_window" in binding:
                candidates=[binding["alarm_window"]]
            else:
                candidates=None
            weekly=binding.get("weekly") if not binding["entity_id"] else self.schedule_cache.get(binding["entity_id"])
            if weekly is None and candidates is None:
                continue
            if binding["entity_id"]:
                state=self.hass.states.get(binding["entity_id"])
                if not state or state.state not in ("on","off"):
                    continue  # never run cached blocks from an unavailable helper
            try:
                if candidates is None:
                    candidates=windows(binding,weekly,local,self.rooms,self.config["max_temperature"])
                candidates=sorted((w for w in candidates if w.end>now),key=lambda w:w.start)
                upcoming=next((w for w in candidates if w.start>now),None)
                for window in candidates:
                    if window.start>now+self.config["max_preheat_minutes"]*60 and window is not upcoming:
                        continue
                    selection=weights(scores,valid,selected=window.source,previous=self.auto_room,
                        margin=self.config["occupancy_margin"]/100,previous_members=self.auto_members)
                    temperature=sum(self.room_data[rid]["temperature"]*weight for rid,weight in selection.items()) if selection else None
                    model=self.model(next(iter(selection)),now) if window.source=="Auto" and len(selection)==1 and sum(scores.get(rid,0) for rid in valid)>=0.05 else self.model(window.source,now) if window.source not in ("Auto","Average") else (
                        self.model(AVERAGE,now) if len(valid)==len(self.rooms) and (window.source=="Average" or sum(scores.get(rid,0) for rid in valid)<0.05) else None)
                    if window.source=="Auto" and len(selection)>1 and sum(scores.get(rid,0) for rid in valid)>=0.05:
                        model=GroupForecast([(self.model(rid,now),self.room_data[rid]["temperature"]) for rid in selection]) if all(self.model(rid,now) for rid in selection) else None
                    prediction=(deadline_plan(now,window.start,window.end-window.start,temperature,
                        window.target,model,self.outdoor,self.config["fallback_heat_rate"],self.config["max_preheat_minutes"]*60)
                        if temperature is not None else {"lead_seconds":0,"reachable":False,"confidence":"input unavailable"})
                    if prediction["confidence"]=="learned":
                        prediction["lead_seconds"]=max(0,min(self.config["max_preheat_minutes"]*60,
                            prediction["lead_seconds"]+self.arrivals.corrections.get(window.source,0)))
                    prediction["estimated_start"]=window.start-prediction["lead_seconds"] if window.preheat else window.start
                    prediction["required_duty"]=(model.duty_to_target(temperature,window.target,self.outdoor,window.start-now)
                        if model is not None and self.outdoor is not None and temperature is not None and now<window.start else 0)
                    in_block=window.start<=now<window.end
                    key=(window.binding_id,window.start)
                    preheating=(not in_block and window.preheat and temperature is not None and
                                (key in self.preheat_latches or temperature<window.target and window.start-prediction["lead_seconds"]<=now<window.start))
                    if preheating:
                        self.preheat_latches.setdefault(key,prediction["estimated_start"])
                    if key in self.preheat_latches:
                        prediction["estimated_start"]=self.preheat_latches[key]
                    plans.append({**prediction,"active":in_block or preheating,"phase":"active" if in_block else "preheat",
                        "binding_id":window.binding_id,"entity_id":window.entity_id,"name":window.name,
                        "source":window.source,"target":window.target,"start":window.start,"end":window.end,
                        "priority":window.priority})
            except (ValueError,TypeError,KeyError,OverflowError):
                self.schedule_status[binding["id"]]="Invalid schedule block data"
        self.schedule_plans=plans
        present={(p["binding_id"],p["start"]) for p in plans}
        self.preheat_latches={k:v for k,v in self.preheat_latches.items() if k in present}
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
            if self.last_tick and dt < 1 and not self.force_tick:
                return
            self.force_tick=False
            self.last_tick = now
            await self.refresh_schedules(now)
            state = self.hass.states.get(self.config["heater"])
            self.actual = (state.state == "on") if state and state.state in ("on", "off") and not state.attributes.get("restored") else None
            if self.startup_pending and self.actual is False:
                self.startup_pending=False
                self.relay=Relay(self.config["pwm_seconds"],self.config["min_on_seconds"],self.config["min_off_seconds"])
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
            auto_selection = weights(scores,valid,previous=self.auto_room,margin=self.config["occupancy_margin"]/100,
                previous_members=self.auto_members)
            self.auto_members = tuple(sorted(auto_selection))
            self.auto_room = next(iter(auto_selection)) if len(auto_selection)==1 else None
            if self.preset == "sleep" and self.config["sleep_room"] and not away:
                source = self.config["sleep_room"]
            scheduled=self.plan_schedules(now,valid,scores,away)
            self.target_origin=("Away · home presence" if away and self.preset!="away" else "Away preset" if away
                else " + ".join(p["name"] for p in scheduled) if scheduled else self.preset.title()+" preset")
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
                               selected="Average" if away or self.preset == "boost" else source,previous=self.auto_room,
                               margin=self.config["occupancy_margin"]/100,previous_members=self.auto_members)
            if scheduled and all(p["source"] not in ("Auto","Average") for p in scheduled):
                selected = {rid: 1/len(scheduled_rooms) for rid in scheduled_rooms}
            average_control = not scheduled_rooms and (away or self.preset == "boost" or source == "Average" or
                              source == "Auto" and sum(scores.get(rid,0) for rid in valid) < 0.05)
            group_control = not average_control and not scheduled_rooms and len(selected)>1
            self.active_source = "Average" if average_control and selected else " + ".join(r["name"] for r in self.rooms if r["id"] in selected) if selected else "Unavailable"
            self.current_temperature = sum(self.room_data[rid]["temperature"] * w for rid,w in selected.items()) if selected else None
            self.target_temperature = sum(self.room_data[rid]["target"] * w for rid,w in selected.items()) if selected else self.comfort_temperature
            reason = "Away average" if away else ("Schedule preheat" if any(p["phase"]=="preheat" for p in scheduled)
                else "Scheduled comfort") if scheduled else "Room control"
            self.guard_data = {}
            for room in self.rooms:
                rid=room["id"];row=self.room_data[rid]
                guard=self.guards[rid]
                buffer=self.config["room_buffer"]
                guard.update(row["temperature"],self.target_temperature,buffer,buffer)
                self.guard_data[rid]={"name":room["name"],"hot":guard.hot,"cold":guard.cold,
                    "upper":self.target_temperature+buffer if buffer else None,
                    "lower":self.target_temperature-buffer if buffer else None,
                    "available":row["temperature"] is not None}
            hot_rooms=[row["name"] for row in self.guard_data.values() if row["hot"]]
            forced = self.mode == "off" or self.startup_pending or not selected or high_temperature or bool(hot_rooms) or self.actual is None
            if self.mode == "off": reason = "Off"
            elif high_temperature: reason = "Safety temperature limit"
            elif hot_rooms: reason = "Warm room protection: " + ", ".join(hot_rooms)
            elif self.actual is None: reason = "Heater unavailable"
            elif self.startup_pending: reason = "Startup: waiting for heater off confirmation"
            elif not selected: reason = "Selected room has no valid temperature" if source not in ("Auto", "Average") else "No valid temperatures"
            if self.pending_pid_memory is not None:
                if self.mode=="off" or high_temperature or hot_rooms:
                    self.pending_pid_memory=None
                    self.memory_restore_status="Discarded by Off or temperature protection"
                else:
                    self.memory_inputs_ready(now)
            duties = {}
            for room in self.rooms:
                rid = room["id"]
                row = self.room_data[rid]
                row["weight"] = selected.get(rid, 0)
                pid = self.pids[rid]
                if row["temperature"] is None:
                    pid.previous = None
                    pid.derivative = pid.integral = 0
                    pid.terms={"active":False,"limit":"input unavailable"}
                    row["duty"] = 0
                    continue
                model = self.model(rid, now)
                if not model and rid in self.applied:
                    pid.tune(*(room[k] for k in ("kp", "ki", "kd")))
                    self.applied.pop(rid)
                self.restore_control_memory(rid,pid,[rid],row["temperature"],row["target"],now,
                    not forced and not average_control and not group_control and selected.get(rid,0)>0.01 and len(selected)==1)
                feedforward = model.feedforward(row["target"], self.outdoor) if model and self.outdoor is not None and self.applied.get(rid) == model.fitted_at else 0
                duty = pid.update(row["temperature"], row["target"], dt, feedforward,
                                  active=not forced and not average_control and not group_control and selected.get(rid,0)>0.01,
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
                self.restore_control_memory(AVERAGE,average_pid,valid,average_temperature,average_target,now,not forced and average_control)
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
            else:
                average_pid.terms={"active":False,"limit":"input unavailable"}
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
            membership=tuple(sorted(selected)) if group_control else ()
            if membership != self.group_members:
                self.group_pid=PID()
                self.group_members=membership
            self.group_data={"active":group_control,"members":list(membership)}
            if group_control:
                # Control the mean measurement, rather than averaging clipped room outputs.
                controllers=[self.pids[rid] for rid in membership]
                gains=(min(p.kp for p in controllers),min(p.ki for p in controllers),max(p.kd for p in controllers))
                if gains != (self.group_pid.kp,self.group_pid.ki,self.group_pid.kd):
                    self.group_pid.tune(*gains)
                self.restore_control_memory("_group",self.group_pid,membership,self.current_temperature,self.target_temperature,now,not forced)
                delay=max((self.model(rid,now).delay if self.model(rid,now) else 600 for rid in membership))
                feedforward=sum((self.model(rid,now).feedforward(self.target_temperature,self.outdoor)
                    if self.outdoor is not None and self.model(rid,now) and self.applied.get(rid)==self.model(rid,now).fitted_at else 0)
                    for rid in membership)/len(membership)
                group_duty=self.group_pid.update(self.current_temperature,self.target_temperature,dt,feedforward,
                    active=not forced,constrained=self.actual is not None and self.proposed!=self.actual)
                if self.current_temperature+max(0,self.group_pid.derivative)*delay >= self.target_temperature+0.3:
                    group_duty=0
                    self.group_pid.integral=min(0,self.group_pid.integral)
                if not forced:self.duty=group_duty
                self.group_data.update(duty=group_duty,gains=dict(zip(("kp","ki","kd"),gains)))
            cold_demands={}
            # A model's full-output arrival estimate needs corresponding heat delivery.
            # Raise ordinary PID demand only during preheat; coast and room guards win.
            if not forced:
                for plan in scheduled:
                    if plan["phase"]!="preheat" or not plan.get("required_duty"):
                        continue
                    if plan["source"] in valid:
                        measured=self.room_data[plan["source"]]["temperature"]
                        controller=self.pids[plan["source"]]
                        model=self.model(plan["source"],now)
                    else:
                        measured=self.current_temperature
                        controller=average_pid if average_control else self.group_pid if group_control else self.pids[next(iter(selected))]
                        models=[self.model(rid,now) for rid in selected]
                        model=average_model if average_control else max((m for m in models if m),key=lambda m:m.delay,default=None)
                    delay=model.delay if model else 600
                    if measured is not None and measured+max(0,controller.derivative)*delay<plan["target"]:
                        self.duty=max(self.duty,plan["required_duty"])
            for room in self.rooms:
                rid=room["id"];row=self.room_data[rid];pid=self.cold_pids[rid]
                main=self.pids[rid]
                gains=(main.kp,main.ki,main.kd)
                if gains != (pid.kp,pid.ki,pid.kd):pid.tune(*gains)
                if row["temperature"] is None:
                    pid.previous=None;pid.integral=pid.derivative=0
                    continue
                buffer=self.config["room_buffer"]
                floor=self.target_temperature-buffer
                duty=pid.update(row["temperature"],floor+min(0.2,buffer/2),dt,
                    active=not forced and self.guards[rid].cold,
                    constrained=self.actual is not None and self.proposed!=self.actual)
                self.guard_data[rid]["cold_duty"]=duty
                if self.guards[rid].cold:cold_demands[room["name"]]=duty
            if not forced and cold_demands:
                protective=max(cold_demands.values())
                if protective>self.duty:
                    self.duty=protective
                    reason="Cold room protection: " + ", ".join(cold_demands)
            self.proposed = self.relay.decide(now, self.duty, bool(self.actual), force_off=forced)
            self.reason = reason
            # Only learn timing corrections from uninterrupted, real, learned-model control.
            arrival_eligible=(not forced and not self.config["shadow"] and bool(scheduled)
                and all(p["confidence"]=="learned" for p in scheduled)
                and reason in ("Schedule preheat","Scheduled comfort"))
            rate=self.config["fallback_heat_rate"]
            if scheduled:
                source=scheduled[0]["source"]
                plant_model=self.model(AVERAGE if source=="Average" else source,now)
                if plant_model and self.outdoor is not None and self.current_temperature is not None:
                    rate=plant_model.heat_rate-plant_model.loss_rate*(self.current_temperature-self.outdoor)+plant_model.bias
            if not self.config["shadow"]:
                # Reassert at every tick, both for retry and for ESP relay watchdog keepalive.
                try:
                    await self.hass.services.async_call("switch", "turn_on" if self.proposed else "turn_off",
                        {"entity_id": self.config["heater"]}, blocking=True)
                except HomeAssistantError as err:
                    self.reason = "Heater command failed"
                    _LOGGER.warning("Heater command failed: %s", err)
            self.arrivals.observe(self.schedule_plans,scheduled,now,self.current_temperature,
                                  arrival_eligible and self.reason!="Heater command failed",rate)
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
        return {"mode":self.mode,"control_signature":self.control_signature(),
                "pid_memory":self.pid_memory_snapshot(),
                "preset": self.preset, "source": self.source, "comfort_temperature":self.comfort_temperature,
                "morning":self.morning.saved(),"arrival_corrections":self.arrivals.corrections,
                "models": {k:v.to_dict() for k,v in self.models.items()},
                "samples": {k:[asdict(s) for s in v] for k,v in self.samples.items()},
                "signatures": {r["id"]: self.signature(r) for r in self.plants}}

    @callback
    def save_later(self):
        self.store.async_delay_save(self.saved, 30)

    async def change(self, **changes):
        for key, value in changes.items():
            setattr(self, key, value)
        if changes.get("mode")=="off":
            self.pending_pid_memory=None
            self.memory_restore_status="Cleared by Off"
        elif isinstance(self.pending_pid_memory,dict) and any(k in changes and changes[k]!=self.pending_pid_memory.get(k) for k in ("source","preset")):
            self.pending_pid_memory=None
            self.memory_restore_status="Cleared by source or preset change"
        self.force_tick = True  # act immediately without inventing occupancy time
        if "mode" in changes:
            # Persist explicit Off/Heat immediately, including before an unexpected restart.
            try:
                await self.store.async_save(self.saved())
            finally:
                # A storage failure must never prevent an explicit Off reaching the relay.
                await self.tick()
        else:
            self.save_later()
            await self.tick()

    async def configure(self, values, room_id=None):
        """Persist entity settings immediately, without unloading an active controller."""
        async with self.lock:
            candidate=deepcopy(self.config)
            if room_id:
                next(r for r in candidate["rooms"] if r["id"]==room_id).update(values)
            else:
                candidate.update(values)
            candidate=validate(candidate)
            if not room_id and "comfort_temperature" in values:
                self.comfort_temperature=candidate["comfort_temperature"]
                self.save_later()
            self.config=candidate
            self.rooms=candidate["rooms"]
            for room in self.rooms:
                plant=next(p for p in self.plants if p["id"]==room["id"])
                plant.update(room)
            self.plants[-1].update(tuning_mode=candidate["average_tuning_mode"],
                **{k:candidate["average_"+k] for k in ("kp","ki","kd")})
            for plant in self.plants:
                rid=plant["id"];model=self.model(rid,dt_util.utcnow().timestamp())
                gains=model.gains(candidate["pwm_seconds"]) if model and plant["tuning_mode"]=="auto" else tuple(plant[k] for k in ("kp","ki","kd"))
                self.pids[rid].tune(*gains)
                if model and plant["tuning_mode"]=="auto":self.applied[rid]=model.fitted_at
                else:self.applied.pop(rid,None)
            self.hass.config_entries.async_update_entry(self.entry,options=deepcopy(candidate))
            self.force_tick=True
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
