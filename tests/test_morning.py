"""Alarm lifecycle, presence, deadlines and bounded arrival feedback."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from datetime import datetime, timezone
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components/comfort_sense"
package=ModuleType("comfort_alarm_test");package.__path__=[str(ROOT)]
sys.modules[package.__name__]=package
for name in ("units","scheduling","morning"):
    spec=importlib.util.spec_from_file_location(f"{package.__name__}.{name}",ROOT/f"{name}.py")
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
morning=sys.modules["comfort_alarm_test.morning"]


class AlarmTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,27,5,tzinfo=timezone.utc).timestamp()
        self.config={"morning_enabled":True,"alarm_sensors":["sensor.matt","sensor.wife"],
            "alarm_owners":{"sensor.matt":"person.matt","sensor.wife":"person.wife"},
            "morning_target":20,"morning_source":"Average","morning_duration":60}
        self.states={"sensor.matt":SimpleNamespace(state="2026-10-27T06:00:00+00:00"),
            "sensor.wife":SimpleNamespace(state="2026-10-27T06:30:00+00:00"),
            "person.matt":SimpleNamespace(state="home"),"person.wife":SimpleNamespace(state="home")}
        self.alarms=morning.MorningAlarms()

    def plan(self,offset=0):
        return self.alarms.window(self.config,self.states,self.now+offset,timezone.utc)

    def test_earliest_home_owner_and_unknown_presence(self):
        self.assertEqual(self.plan().entity_id,"sensor.matt")
        self.states["person.matt"].state="not_home"
        self.assertEqual(self.plan().entity_id,"sensor.wife")
        self.states["person.wife"].state="unknown"
        self.assertIsNone(self.plan())

    def test_cancel_and_reschedule_before_firing(self):
        self.plan()
        self.states["sensor.matt"].state="unavailable"
        self.assertEqual(self.plan().entity_id,"sensor.wife")
        self.states["sensor.matt"].state="2026-10-27T05:30:00Z"
        self.assertEqual(self.plan().start,self.now+1800)

    def test_fire_latches_and_later_phone_does_not_extend_morning(self):
        self.plan()
        self.states["sensor.matt"].state="2026-10-28T06:00:00Z"
        self.assertEqual(self.plan(3600).start,self.now+3600)
        self.assertEqual(self.plan(5400).end,self.now+7200)
        # At 07:00, wife's 06:30 alarm must not create a second session.
        upcoming=self.plan(7200)
        self.assertGreater(upcoming.start,self.now+86400)

    def test_persist_fired_hold_across_restart_and_expire_it(self):
        self.plan()
        saved=self.alarms.saved()
        self.alarms=morning.MorningAlarms()
        self.alarms.restore(saved,self.now+3660)
        self.states["sensor.matt"].state="unknown"
        self.assertEqual(self.plan(3660).start,self.now+3600)
        self.assertIsNone(self.plan(10800))

    def test_disabled_unmapped_and_invalid_timestamps(self):
        self.config["alarm_owners"]={}
        self.states["person.matt"].state="not_home"
        self.assertIsNotNone(self.plan())
        for value in ("unknown","unavailable","2026-10-27T06:00:00","garbage"):
            self.assertIsNone(morning.alarm_timestamp(value))
        self.states["sensor.matt"].state="2026-10-20T06:00:00Z"
        self.states["sensor.wife"].state="2026-11-20T06:00:00Z"
        self.assertIsNone(self.plan())
        self.config["morning_enabled"]=False
        self.assertIsNone(self.plan())
        self.assertEqual(self.alarms.status,"Disabled")

    def test_offset_timestamp_is_same_instant(self):
        self.assertEqual(morning.alarm_timestamp("2026-10-27T06:00:00-04:00"),
                         morning.alarm_timestamp("2026-10-27T10:00:00Z"))


class ArrivalTests(unittest.TestCase):
    def plan(self):
        return {"binding_id":"morning","start":3600,"source":"Average","target":20,"active":True}

    def test_late_arrival_adjusts_gradually_and_is_bounded(self):
        learning=morning.ArrivalLearning();plan=self.plan()
        learning.observe([plan],[plan],3570,19,True,1)
        learning.observe([plan],[plan],3600,19,True,1)
        self.assertEqual(learning.corrections["Average"],300)
        self.assertEqual(learning.last_arrival["error"],1)
        learning.observe([plan],[plan],3630,19,True,1)
        self.assertEqual(learning.corrections["Average"],300)

    def test_early_arrival_reduces_lead_and_interrupted_runs_never_train(self):
        learning=morning.ArrivalLearning();plan=self.plan()
        for now in range(3000,3601,30):
            learning.observe([plan],[plan],now,20,True,1)
        self.assertEqual(learning.corrections["Average"],-120)
        learning=morning.ArrivalLearning()
        learning.observe([plan],[plan],3570,19,False,1)
        learning.observe([plan],[plan],3600,19,True,1)
        self.assertFalse(learning.corrections)

    def test_missing_ticks_and_multiple_room_plans_do_not_train(self):
        learning=morning.ArrivalLearning();plan=self.plan()
        learning.observe([plan],[plan],3000,19,True,1)
        learning.observe([plan],[plan],3600,19,True,1)
        self.assertFalse(learning.corrections)
        learning.restore({"Average":float("nan"),"Auto":2000,"room":100})
        self.assertEqual(learning.corrections,{"room":100})
