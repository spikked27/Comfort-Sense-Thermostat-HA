"""Meaningful deterministic controls and slow-plant identification regressions."""
import importlib.util
from pathlib import Path
import sys
import unittest
import math
import random

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "comfort_sense"


def module(name):
    spec = importlib.util.spec_from_file_location(name, COMPONENT / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


control = module("control")
learning = module("learning")


def plant(days=5, noise=0.0, delay=1800):
    rng = random.Random(818)
    temperature = 20.0
    rows, heat = [], []
    for i in range(days*288):
        time = i*300.0
        outdoor = 7 + 5*math.sin(time/86400*2*math.pi)
        on = float((i // (13 if i < 900 else 17)) % 3 != 0)
        heat.append(on)
        rows.append(learning.Sample(time, temperature + rng.gauss(0,noise), outdoor, on))
        delayed = heat[max(0, i-int(delay/300))] if i*300 >= delay else 0
        equilibrium = outdoor + (1.8*delayed + 0.15)/0.06
        temperature = equilibrium + (temperature-equilibrium)*math.exp(-0.06/12)
    return rows


class ControlTests(unittest.TestCase):
    def test_temperature_units_and_nonfinite(self):
        self.assertAlmostEqual(control.celsius(68,"°F"),20)
        self.assertAlmostEqual(control.celsius(293.15,"K"),20)
        for value,unit in [(math.nan,"°C"),(20,None),(100,"°C")]:
            with self.assertRaises(ValueError): control.celsius(value,unit)

    def test_unknown_presence_not_away(self):
        self.assertIsNone(control.presence("unavailable"))
        self.assertFalse(control.presence("0"))
        self.assertTrue(control.presence("2"))
        self.assertTrue(control.presence("home"))

    def test_occupancy_accumulates_and_decays_gradually(self):
        o = control.Occupancy()
        self.assertLess(o.update(True,30),0.1)
        for _ in range(60): o.update(True,30)
        self.assertGreater(o.score,0.99)
        before = o.score
        o.update(False,30)
        self.assertGreater(o.score,before*0.98)
        self.assertAlmostEqual(o.update(False,1800), before*math.exp(-1830/1800))

    def test_room_weights_and_away_equal_room_average(self):
        w=control.weights({"a":1,"b":0.5},["a","b"])
        self.assertEqual(w,{"a":1.0})
        self.assertEqual(control.weights({},["a","b"],True),{"a":0.5,"b":0.5})
        self.assertEqual(control.weights({},["b"],selected="a"),{})
        self.assertEqual(control.weights({},[]),{})

    def test_derivative_no_setpoint_kick(self):
        p=control.PID(kp=0.2,ki=0,kd=600)
        p.update(20,20,30)
        p.update(20,22,30)
        self.assertEqual(p.derivative,0)
        self.assertAlmostEqual(p.output,0.4)

    def test_fixed_window_changes_room_after_half_window_and_keeps_tie(self):
        for window in (600,1800,3600):
            old,new=control.Occupancy(),control.Occupancy()
            old.moving_average(True,window,window)
            new.moving_average(False,window,window)
            old.moving_average(False,window/2,window)
            new.moving_average(True,window/2,window)
            self.assertEqual(control.weights({"old":old.score,"new":new.score},["old","new"],previous="old"),{"old":1.0})
            old.moving_average(False,30,window)
            new.moving_average(True,30,window)
            self.assertEqual(control.weights({"old":old.score,"new":new.score},["old","new"],previous="old"),{"new":1.0})
            new.moving_average(False,window,window)
            self.assertEqual(new.score,0)

    def test_moving_average_is_time_weighted_not_event_count(self):
        a,b=control.Occupancy(),control.Occupancy()
        a.moving_average(True,600,1800)
        for _ in range(600): b.moving_average(True,1,1800)
        self.assertAlmostEqual(a.score,b.score)

    def test_relative_occupancy_groups_use_equal_room_mean(self):
        self.assertEqual(control.weights({"a":0.6,"b":0.5,"c":0.2},["a","b","c"],margin=0.3),{"a":0.5,"b":0.5})
        self.assertEqual(control.weights({"a":1,"b":0.75},["a","b"],margin=0.3),{"a":0.5,"b":0.5})
        self.assertEqual(control.weights({"a":1,"b":0.7},["a","b"],margin=0.3),{"a":1})
        self.assertEqual(control.weights({"a":0.5,"b":0.5,"c":0.5},["a","b","c"],margin=0.3),{"a":1/3,"b":1/3,"c":1/3})
        self.assertEqual(control.weights({"a":1,"b":1},["a","b"],margin=0),{"a":1})

    def test_room_guard_hysteresis_disabled_and_missing_inputs(self):
        guard=control.RoomGuard()
        guard.update(22,21,1,2);self.assertTrue(guard.hot)
        guard.update(21.9,21,1,2);self.assertTrue(guard.hot)
        guard.update(21.7,21,1,2);self.assertFalse(guard.hot)
        guard.update(18.5,21,1,2);self.assertTrue(guard.cold)
        guard.update(19.1,21,1,2);self.assertTrue(guard.cold)
        guard.update(19.3,21,1,2);self.assertFalse(guard.cold)
        guard.update(40,21,0,0);self.assertFalse(guard.hot)
        guard.update(-5,21,0,0);self.assertFalse(guard.cold)
        guard.update(None,21,1,2);self.assertFalse(guard.hot or guard.cold)

    def test_antiwindup_and_off_resets(self):
        p=control.PID()
        for _ in range(300): p.update(15,25,30)
        self.assertEqual(p.integral,0)
        p.update(20,21,30,constrained=True)
        self.assertEqual(p.integral,0)
        p.update(20,21,30)
        self.assertGreater(p.integral,0)
        self.assertEqual(p.update(20,21,30,active=False),0)
        self.assertEqual(p.integral,0)

    def test_relay_minimum_dwell_and_emergency_off(self):
        r=control.Relay()
        self.assertFalse(r.decide(0,1,False))
        self.assertTrue(r.decide(300,1,False))
        r.observe(300,True)
        self.assertTrue(r.decide(330,0,True))
        self.assertFalse(r.decide(331,1,True,force_off=True))

    def test_small_demand_does_not_disappear(self):
        r=control.Relay()
        on=False
        ticks=[]
        for t in range(0,24000,30):
            wanted=r.decide(t,0.05,on)
            if wanted != on: ticks.append((t,wanted))
            on=wanted
        starts=[t for t,state in ticks if state]
        self.assertGreaterEqual(len(starts),3)
        lengths=[b[0]-a[0] for a,b in zip(ticks,ticks[1:]) if a[1]]
        self.assertTrue(all(length >=300 for length in lengths))
        self.assertAlmostEqual(sum(lengths)/24000,0.05,delta=0.015)

    def test_unreachable_deadline_is_bounded_and_reported(self):
        model=learning.ThermalModel(0.5,0.1,0,1800,0,1,0,500)
        plan=control.deadline_plan(0,3600,3600,20,22,model,0)
        self.assertFalse(plan["reachable"])
        self.assertEqual(plan["lead_seconds"],14400)
        self.assertTrue(plan["active"])

    def test_deadline_hold_and_expiry(self):
        plan=control.deadline_plan(3600,3600,1800,20,21)
        self.assertTrue(plan["active"])
        self.assertFalse(control.deadline_plan(5400,3600,1800,20,21)["active"])


class LearningTests(unittest.TestCase):
    def test_learned_pi_on_slow_delayed_closed_loop(self):
        model=learning.ThermalModel(1.8,0.06,0.15,1800,0,1,0,500)
        pid=control.PID(*model.gains())
        relay=control.Relay()
        temperature=18.0
        on=False
        history=[]
        measured=[]
        for i in range(48*120):
            duty=pid.update(temperature,21,30,feedforward=model.feedforward(21,5))
            if temperature+max(0,pid.derivative)*model.delay>=21.3:
                duty=0
                pid.integral=min(0,pid.integral)
            on=relay.decide(i*30,duty,on)
            history.append(float(on))
            delayed=history[i-60] if i>=60 else 0
            temperature=model.forecast(temperature,5,delayed,30)
            measured.append(temperature)
        self.assertLess(max(measured)-21,0.8)
        self.assertLess(sum(abs(t-21) for t in measured[-720:])/720,0.4)

    def test_slow_delayed_plant_identification(self):
        model,status=learning.identify(plant())
        self.assertIsNotNone(model,status)
        self.assertAlmostEqual(model.heat_rate,1.8,delta=0.1)
        self.assertAlmostEqual(model.loss_rate,0.06,delta=0.01)
        self.assertAlmostEqual(model.delay,1800,delta=300)
        self.assertGreater(model.improvement,0.8)
        kp,ki,kd=model.gains()
        self.assertTrue(0<kp<=0.8)
        self.assertTrue(0<ki<=0.0002)
        self.assertEqual(kd,0)

    def test_noisy_data_and_constant_heat_rejected(self):
        self.assertIsNone(learning.identify(plant(noise=0.8))[0])
        rows=[learning.Sample(i*300,20,5,1) for i in range(1000)]
        self.assertIsNone(learning.identify(rows)[0])

    def test_short_record_rejected(self):
        self.assertIsNone(learning.identify(plant(days=1))[0])

    def test_forecast_and_reach_time(self):
        m=learning.ThermalModel(1.8,0.06,0.15,1800,0,1,0,500)
        duration=m.time_to_target(18,21,5)
        cooled=m.forecast(18,5,0,m.delay)
        self.assertAlmostEqual(m.forecast(cooled,5,1,duration-m.delay),21)
        self.assertEqual(m.time_to_target(22,21,5),0)

    def test_missing_data_not_interpolated(self):
        rows=plant()
        rows=rows[:400]+rows[450:]
        model,status=learning.identify(rows)
        self.assertIsNotNone(model,status)
        self.assertLess(model.samples,len(rows))

    def test_small_temperature_quantization_can_still_identify_slow_plant(self):
        rows=[learning.Sample(s.time,round(s.temperature*10)/10,s.outdoor,s.heat) for s in plant()]
        model,status=learning.identify(rows)
        self.assertIsNotNone(model,status)
        self.assertAlmostEqual(model.heat_rate,1.8,delta=0.2)

    def test_outage_segments_not_bridged(self):
        rows=[learning.Sample(s.time,s.temperature,s.outdoor,s.heat,int(i>=500))
              for i,s in enumerate(plant())]
        model,status=learning.identify(rows)
        self.assertIsNotNone(model,status)
        self.assertLess(model.samples,len(rows)-12)


if __name__=="__main__": unittest.main()
