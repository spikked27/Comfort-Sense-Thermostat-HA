"""Boundary regression tests using explicit HA fakes; real HA tests live in ha_tests."""
import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"comfort_sense"


def fake(name):
    mod=ModuleType(name)
    sys.modules[name]=mod
    return mod


# Only exercised HA surfaces are faked. These tests do not claim full HA integration.
for name in ["homeassistant", "homeassistant.helpers", "homeassistant.util"]: fake(name)
core=fake("homeassistant.core")
core.callback=lambda f:f
exc=fake("homeassistant.exceptions")
class HomeAssistantError(Exception): pass
exc.HomeAssistantError=HomeAssistantError
events=fake("homeassistant.helpers.event")
events.async_track_state_change_event=lambda *a:lambda:None
events.async_track_time_interval=lambda *a:lambda:None
storage=fake("homeassistant.helpers.storage")
class Store:
    def __init__(self,*a): self.data=None
    async def async_load(self): return self.data
    async def async_save(self,data): self.data=data
    def async_delay_save(self,fn,delay): self.data=fn()
storage.Store=Store
dt=fake("homeassistant.util.dt")
dt.utcnow=lambda: datetime(2026,10,11,12,tzinfo=timezone.utc)
dt.utc_from_timestamp=lambda t:datetime.fromtimestamp(t,timezone.utc)
dt.as_local=lambda d:d
dt.as_utc=lambda d:d.astimezone(timezone.utc)
package=fake("comfort_sense_test")
package.__path__=[str(ROOT)]
for name in ["const","settings","control","learning","runtime"]:
    spec=importlib.util.spec_from_file_location(f"comfort_sense_test.{name}",ROOT/f"{name}.py")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
runtime=sys.modules["comfort_sense_test.runtime"]


class Services:
    def __init__(self):self.calls=[];self.fail=False
    async def async_call(self,domain,service,data,**kwargs):
        self.calls.append((domain,service,data))
        if self.fail: raise HomeAssistantError("offline")


class Hass:
    def __init__(self):
        self.states=SimpleNamespace(get=lambda e:self.values.get(e))
        self.values={}
        self.services=Services()
        self.tasks=[]
    def async_create_task(self,coro):
        task=asyncio.create_task(coro)
        self.tasks.append(task)
        return task
    async def async_add_executor_job(self,fn,*args):return fn(*args)


def room(rid="a"):
    return {"id":rid,"name":rid.upper(),"temperature_sensors":[f"sensor.{rid}"],
        "occupancy_sensors":[f"binary_sensor.{rid}"],"target":21,
        "morning_enabled":False,"morning_time":"07:00","morning_target":22,
        "morning_duration":60,"morning_days":list(range(7))}


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now=datetime(2026,10,11,12,tzinfo=timezone.utc)
        dt.utcnow=lambda:self.now
        self.hass=Hass()
        self.entry=SimpleNamespace(entry_id="test",data={"heater":"switch.heat", "rooms":[room(),room("b")],
            "home_sensor":"zone.home", "outdoor_sensor":"sensor.outdoor"},options={})
        self.r=runtime.Runtime(self.hass,self.entry)
        self.set("switch.heat","off")
        self.set("sensor.a","68","°F")
        self.set("sensor.b","22","°C")
        self.set("sensor.outdoor","5","°C")
        self.set("zone.home","1")
        self.r.last_fit=self.now.timestamp()

    def set(self,e,state,unit=None,age=0):
        stamp=datetime.fromtimestamp(self.now.timestamp()-age,timezone.utc)
        self.hass.values[e]=SimpleNamespace(state=state,attributes={"unit_of_measurement":unit},
                                           last_reported=stamp,last_updated=stamp)

    def advance(self,seconds):
        self.now=datetime.fromtimestamp(self.now.timestamp()+seconds,timezone.utc)

    async def asyncTearDown(self):
        await asyncio.gather(*self.hass.tasks,return_exceptions=True)

    async def test_shadow_never_calls_heater(self):
        self.r.mode="heat"
        await self.r.tick()
        self.assertEqual(self.hass.services.calls,[])
        self.assertAlmostEqual(self.r.current_temperature,21)
        await self.r.stop()
        self.assertEqual(self.hass.services.calls,[])

    async def test_away_requires_confirmed_home_absence(self):
        self.r.mode="heat"
        self.set("zone.home","unavailable")
        await self.r.tick()
        self.assertEqual(self.r.reason,"Room control")
        self.set("zone.home","0")
        self.advance(30);await self.r.tick()
        self.advance(1200);await self.r.tick()
        self.assertEqual(self.r.reason,"Away average")
        self.assertEqual(self.r.target_temperature,18)

    async def test_missing_room_excluded_but_selected_missing_fails_off(self):
        self.r.mode="heat"
        self.set("sensor.b","unavailable")
        await self.r.tick()
        self.assertEqual(self.r.current_temperature,20)
        self.assertEqual(self.r.room_data["a"]["weight"],1)
        await self.r.change(source="b")
        self.assertEqual(self.r.duty,0)
        self.assertEqual(self.r.reason,"Selected room has no valid temperature")

    async def test_high_temperature_in_unselected_room_forces_off(self):
        self.r.config["shadow"]=False
        self.r.mode="heat"
        self.r.source="a"
        self.set("sensor.b","30","°C")
        self.set("switch.heat","on")
        await self.r.tick()
        self.assertEqual(self.r.reason,"Safety temperature limit")
        self.assertEqual(self.hass.services.calls[-1][1],"turn_off")

    async def test_stale_temperatures_force_off(self):
        self.r.mode="heat"
        self.set("sensor.a","20","°C",age=20000)
        self.set("sensor.b","20","°C",age=20000)
        await self.r.tick()
        self.assertEqual(self.r.reason,"No valid temperatures")
        self.assertFalse(self.r.proposed)

    async def test_unknown_relay_retries_off_and_does_not_train(self):
        self.r.config["shadow"]=False
        self.r.mode="heat"
        self.set("switch.heat","unavailable")
        await self.r.tick()
        self.assertEqual(self.hass.services.calls[-1][1],"turn_off")
        self.assertEqual(self.r.reason,"Heater unavailable")
        self.assertEqual(len(self.r.samples["a"]),0)

    async def test_command_failure_visible_and_not_treated_as_feedback(self):
        self.r.config["shadow"]=False
        self.r.mode="heat"
        self.hass.services.fail=True
        await self.r.tick()
        self.assertEqual(self.r.reason,"Heater command failed")
        self.assertFalse(self.r.actual)

    async def test_boost_expires_and_away_overrides_boost(self):
        self.r.mode="heat"
        await self.r.change(preset="boost",boost_until=self.now.timestamp()+60)
        self.assertEqual(self.r.target_temperature,22)
        self.advance(61);await self.r.tick()
        self.assertEqual(self.r.preset,"comfort")
        self.set("zone.home","0")
        await self.r.change(preset="boost",boost_until=self.now.timestamp()+3600)
        self.advance(1201);await self.r.tick()
        self.assertEqual(self.r.target_temperature,18)

    async def test_missing_outdoor_does_not_invent_training_data(self):
        self.set("sensor.outdoor","unavailable")
        await self.r.tick()
        self.assertEqual(len(self.r.samples["a"]),0)

    async def test_manual_off_bypasses_minimum_on_time(self):
        self.r.config["shadow"]=False
        self.r.mode="heat"
        self.set("switch.heat","on")
        await self.r.tick()
        await self.r.change(mode="off")
        self.assertEqual(self.hass.services.calls[-1][1],"turn_off")

    async def test_morning_overrides_sleep_occupancy_but_not_away(self):
        self.r.mode="heat"
        self.r.preset="sleep"
        self.r.rooms[0].update(morning_enabled=True,morning_time="12:30")
        await self.r.tick()
        self.assertEqual(self.r.reason,"Morning preheat")
        self.assertEqual(self.r.target_temperature,22)
        await self.r.change(preset="away")
        self.assertEqual(self.r.target_temperature,18)

    async def test_restart_never_restores_heating(self):
        self.assertEqual(self.r.mode,"off")
        self.r.store.data={"preset":"boost","source":"nonexistent","targets":{},"models":{}}
        await self.r.start()
        # start() is only called on a fresh runtime in HA.
        self.assertEqual(self.r.preset,"comfort")
        self.assertEqual(self.r.source,"Auto")
        self.assertEqual(self.r.mode,"off")

    async def test_each_room_has_independent_manual_gains(self):
        self.entry.data["rooms"][0].update(kp=0.4,ki=0.00002,kd=20,tuning_mode="manual")
        self.entry.data["rooms"][1].update(kp=0.1,ki=0.00001,kd=0,tuning_mode="auto")
        r=runtime.Runtime(self.hass,self.entry)
        self.assertEqual(r.pids["a"].kp,0.4)
        self.assertEqual(r.pids["b"].kp,0.1)

    async def test_average_uses_dedicated_pid_not_mean_room_outputs(self):
        self.r.mode="heat"
        self.r.source="Average"
        self.r.pids["_average"].kp=0.6
        self.r.pids["_average"].ki=0
        self.set("sensor.a","19","°C")
        self.set("sensor.b","21","°C")
        await self.r.tick()
        self.assertAlmostEqual(self.r.duty,0.6)
        self.assertEqual(self.r.room_data["a"]["duty"],0)
        self.assertEqual(self.r.room_data["b"]["duty"],0)
        self.assertTrue(self.r.room_data["_average"]["active"])

    async def test_average_own_tuning_and_incomplete_membership_fallback(self):
        self.r.config["average_tuning_mode"]="auto"
        self.r.plants[-1]["tuning_mode"]="auto"
        model=runtime.ThermalModel(1.8,0.06,0.15,1800,0.1,0.9,self.now.timestamp(),800)
        self.r.models["_average"]=model
        self.r.mode="heat"
        self.r.source="Average"
        await self.r.tick()
        self.assertEqual(self.r.pids["_average"].kp,model.gains()[0])
        self.assertIn("_average",self.r.applied)
        self.set("sensor.b","unknown")
        self.advance(30);await self.r.tick()
        self.assertEqual(self.r.pids["_average"].kp,0.2)
        self.assertNotIn("_average",self.r.applied)
        self.assertFalse(self.r.room_data["_average"]["complete_membership"])

    async def test_average_membership_change_does_not_create_derivative_kick(self):
        self.r.mode="heat"
        self.r.source="Average"
        await self.r.tick()
        self.set("sensor.b","unknown")
        self.advance(30);await self.r.tick()
        self.assertEqual(self.r.pids["_average"].derivative,0)

    async def test_average_does_not_learn_from_partial_membership(self):
        self.set("sensor.b","unknown")
        await self.r.tick()
        self.assertEqual(len(self.r.samples["_average"]),0)
        self.assertEqual(len(self.r.samples["a"]),1)

    async def test_brief_sensor_outage_starts_new_learning_segment(self):
        await self.r.tick()
        self.set("sensor.b","unknown")
        self.advance(30);await self.r.tick()
        self.set("sensor.b","22","°C")
        self.advance(30);await self.r.tick()
        self.assertNotEqual(self.r.samples["b"][0].segment,self.r.samples["b"][-1].segment)
        self.assertNotEqual(self.r.samples["_average"][0].segment,self.r.samples["_average"][-1].segment)

    async def test_average_signature_survives_json_roundtrip(self):
        import json
        signature=self.r.signature(self.r.plants[-1])
        self.assertEqual(json.loads(json.dumps(signature)),signature)

    async def test_validated_tune_applies_only_to_auto_room(self):
        self.r.rooms[1]["tuning_mode"]="auto"
        model=runtime.ThermalModel(1.8,0.06,0.15,1800,0.1,0.9,self.now.timestamp(),800)
        original=runtime.identify
        runtime.identify=lambda *a:(model,"Validated")
        try: await self.r.fit()
        finally:runtime.identify=original
        self.assertEqual(self.r.pids["a"].kp,0.2)
        self.assertEqual(self.r.pids["b"].kp,model.gains()[0])
        self.assertNotIn("a",self.r.applied)
        self.assertIn("b",self.r.applied)

    async def test_invalid_cycle_config_rejected(self):
        self.entry.options={"pwm_seconds":120}
        with self.assertRaises(ValueError):runtime.Runtime(self.hass,self.entry)


if __name__=="__main__":unittest.main()
