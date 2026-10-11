"""Native weekly blocks, priority and Celsius-preserving migration."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from datetime import datetime, time
from zoneinfo import ZoneInfo
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components/comfort_sense"
package=ModuleType("comfort_schedule_test");package.__path__=[str(ROOT)]
sys.modules[package.__name__]=package
for name in ("units","scheduling"):
    spec=importlib.util.spec_from_file_location(f"{package.__name__}.{name}",ROOT/f"{name}.py")
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
scheduling=sys.modules["comfort_schedule_test.scheduling"]
units=sys.modules["comfort_schedule_test.units"]


class ScheduleTests(unittest.TestCase):
    def binding(self):
        return {"id":"morning","name":"Morning","entity_id":"schedule.morning","source":"Average",
            "target":21,"preheat":True,"priority":0,"data_temperature_unit":"°F"}

    def test_fahrenheit_roundtrip_does_not_change_stored_target(self):
        self.assertAlmostEqual(units.display_temperature(21.111111111,"°F"),70)
        self.assertAlmostEqual(units.native_temperature(70,"°F"),21.111111111)
        self.assertEqual(units.native_temperature(21,"°C"),21)

    def test_rate_conversion_does_not_add_32(self):
        self.assertAlmostEqual(units.display_rate(0.5,"°F"),0.9)
        self.assertAlmostEqual(units.native_rate(0.9,"°F"),0.5)

    def test_legacy_migration_keeps_ids_temperatures_and_schedule(self):
        config={"rooms":[{"id":"bed","name":"Bedroom","target":21.111111111,
            "morning_enabled":True,"morning_time":"23:30","morning_duration":120,
            "morning_days":[0],"morning_target":22}]}
        result=scheduling.migrate_config(config)
        self.assertEqual(result["rooms"][0]["id"],"bed")
        self.assertEqual(result["rooms"][0]["target"],config["rooms"][0]["target"])
        self.assertNotIn("morning_enabled",result["rooms"][0])
        self.assertEqual(result["schedules"][0]["weekly"]["monday"][0]["to"],"24:00")
        self.assertEqual(result["schedules"][0]["weekly"]["tuesday"][0]["to"],"01:30")
        self.assertEqual(scheduling.migrate_config(result),result)

    def test_schedule_data_can_override_target_and_room(self):
        now=datetime.fromisoformat("2026-10-11T12:00:00-04:00")
        weekly={"sunday":[{"from":"13:00","to":"14:00","data":{"temperature":72,"source":"Bedroom"}}]}
        plans=scheduling.windows(self.binding(),weekly,now,[{"id":"bed","name":"Bedroom"}],28)
        self.assertEqual(plans[0].source,"bed")
        self.assertAlmostEqual(plans[0].target,22.2222222222)

    def test_midnight_and_native_time_objects(self):
        now=datetime.fromisoformat("2026-10-11T23:00:00-04:00")
        plans=scheduling.windows(self.binding(),{"sunday":[{"from":time(22),"to":time.max}]},now,[],28)
        self.assertEqual(plans[0].end-plans[0].start,7200)

    def test_dst_spring_gap_resolves_to_real_local_time(self):
        try:zone=ZoneInfo("America/New_York")
        except Exception:self.skipTest("Timezone database unavailable")
        now=datetime(2026,3,8,0,tzinfo=zone)
        start=scheduling.wall_time(now.date(),"02:30",zone)
        self.assertEqual(datetime.fromtimestamp(start,zone).hour,3)

    def test_dst_fall_overlap_uses_first_occurrence(self):
        try:zone=ZoneInfo("America/New_York")
        except Exception:self.skipTest("Timezone database unavailable")
        now=datetime(2026,11,1,0,tzinfo=zone)
        start=scheduling.wall_time(now.date(),"01:30",zone)
        self.assertEqual(datetime.fromtimestamp(start,zone).fold,0)

    def test_invalid_schedule_data_rejected(self):
        now=datetime.fromisoformat("2026-10-11T12:00:00-04:00")
        with self.assertRaises(ValueError):
            scheduling.windows(self.binding(),{"sunday":[{"from":"13:00","to":"14:00",
                "data":{"temperature":100,"source":"Average"}}]},now,[],28)

    def test_priorities_and_equal_priority_room_plans(self):
        plans=[{"active":True,"priority":1,"source":"a","phase":"active","start":1,"binding_id":"a"},
               {"active":True,"priority":1,"source":"b","phase":"preheat","start":2,"binding_id":"b"},
               {"active":True,"priority":0,"source":"Average","phase":"active","start":3,"binding_id":"c"}]
        self.assertEqual({p["source"] for p in scheduling.choose(plans)},{"a","b"})

    def test_adjacent_average_block_can_preheat_next_target(self):
        plans=[{"active":True,"priority":0,"source":"Average","phase":"active","start":1,"binding_id":"a"},
               {"active":True,"priority":0,"source":"Average","phase":"preheat","start":2,"binding_id":"a"}]
        self.assertEqual(scheduling.choose(plans)[0]["start"],2)


if __name__=="__main__":unittest.main()
