"""Whole-runtime simulations with delayed plants and explicit HA boundary fakes."""
from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
import test_runtime as boundary

runtime=boundary.runtime


class ThermalScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def simulate(self,hours,scheduled=False,restart=False):
        now=datetime(2026,10,11,tzinfo=timezone.utc)
        hass=boundary.Hass()
        entry=SimpleNamespace(entry_id="thermal",data={"heater":"switch.heat","outdoor_sensor":"sensor.outdoor",
            "home_sensor":"zone.home","shadow":False,"reaction_time":"fast","comfort_temperature":20,
            "rooms":[boundary.room("a"),boundary.room("b")]},options={})
        if scheduled:
            entry.data["schedules"]=[{"id":"wake","name":"Wake","entity_id":"schedule.wake","source":"a",
                "target":21,"data_temperature_unit":"°C","preheat":True,"priority":0}]
            hass.services.schedule_response={"schedule.wake":{day:[{"from":"06:00","to":"09:00"}] for day in ("sunday","monday")}}
        models={"a":runtime.ThermalModel(1.8,0.06,0.15,1800,0.1,0.9,now.timestamp(),1000),
                "b":runtime.ThermalModel(1.65,0.055,0.1,2700,0.1,0.9,now.timestamp(),1000)}
        temperatures={"a":18.0,"b":18.0}
        delay={rid:deque([0.0]*int(m.delay/30)) for rid,m in models.items()}
        r=runtime.Runtime(hass,entry)
        r.mode="heat"
        r.preset="sleep" if scheduled else "comfort"
        for rid,model in models.items():
            r.models[rid]=model;r.pids[rid].tune(*model.gains());r.applied[rid]=model.fitted_at
        # Storage serialization and curve fitting have separate tests; keep this
        # long physics loop focused on the actual control/schedule/relay runtime.
        r.store.async_delay_save=lambda *args:None
        on=False;measurements=[];runs=[];last_switch=None;was_on=False;arrival=[];restart_result=None
        status_samples={}
        for step in range(hours*120):
            boundary.dt.utcnow=lambda:now
            elapsed=step/120
            outdoor=5 if elapsed<12 else 0 if elapsed<24 else 6
            def set_state(eid,value,unit=None):
                hass.values[eid]=SimpleNamespace(state=str(value),attributes={"unit_of_measurement":unit},last_reported=now,last_updated=now)
            set_state("switch.heat","on" if on else "off")
            set_state("sensor.outdoor",outdoor,"°C")
            set_state("zone.home",0 if not scheduled and elapsed>=hours-6 else 1)
            if scheduled:set_state("schedule.wake","on" if 6<=now.hour<9 else "off")
            for rid in temperatures:
                set_state("sensor."+rid,temperatures[rid],"°C")
                occupied=(elapsed<8 and rid=="a") or (8<=elapsed<16 and rid=="b") or 16<=elapsed<24
                set_state("binary_sensor."+rid,"on" if occupied and not scheduled else "off")
            r.last_fit=now.timestamp()
            if restart and step==18*120:
                # Real reload requests Off; emulate the confirmed physical result.
                await r.stop()
                saved=r.store.data
                on=False;set_state("switch.heat","off")
                r=runtime.Runtime(hass,entry);r.store.data=saved
                r.store.async_delay_save=lambda *args:None
                await r.start()
                r.last_fit=now.timestamp()
                restart_result=(r.mode,r.proposed,r.relay.changed)
            await r.tick()
            on=r.proposed
            if on!=was_on:
                if last_switch is not None:runs.append((was_on,now.timestamp()-last_switch,r.reason))
                last_switch=now.timestamp();was_on=on
            for rid,model in models.items():
                delayed=delay[rid].popleft();delay[rid].append(float(on))
                temperatures[rid]=model.forecast(temperatures[rid],outdoor,delayed,30)
            measurements.append((elapsed,*temperatures.values(),r.target_temperature))
            if now.hour==6 and now.minute==0 and now.second==0:
                arrival.append(temperatures["a"])
            if step in (7*120,15*120,23*120,(hours-1)*120):
                status_samples[step//120]=(r.active_source,r.target_temperature)
            now+=timedelta(seconds=30)
        await r.stop()
        await boundary.asyncio.gather(*hass.tasks,return_exceptions=True)
        return {"measurements":measurements,"runs":runs,"arrival":arrival,"restart":restart_result,"status":status_samples}

    async def test_two_day_scheduled_recovery_handles_delivery_delay_and_weather(self):
        result=await self.simulate(48,scheduled=True)
        self.assertEqual(len(result["arrival"]),2)
        self.assertTrue(all(abs(t-21)<1 for t in result["arrival"]),result["arrival"])
        self.assertLess(max(max(a,b) for _,a,b,_ in result["measurements"]),23.5)
        self.assertTrue(all(seconds>=300 or "protection" in reason or reason=="Safety temperature limit"
                            for _,seconds,reason in result["runs"]),result["runs"])

    async def test_occupancy_group_away_and_restart_do_not_replay_old_heat(self):
        result=await self.simulate(36,restart=True)
        self.assertEqual(result["status"][7][0],"A")
        self.assertEqual(result["status"][15][0],"B")
        self.assertEqual(result["status"][23][0],"A + B")
        self.assertEqual(result["status"][35],("Average",18))
        self.assertEqual(result["restart"][:2],("heat",False))
        self.assertLess(max(max(a,b) for _,a,b,_ in result["measurements"]),22.5)
