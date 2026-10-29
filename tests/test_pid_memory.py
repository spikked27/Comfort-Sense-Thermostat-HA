"""PID compensation policy and guarded restart recovery through the runtime."""
import copy
import json
import unittest
import test_runtime as boundary
from comfort_sense_test.memory import recovered_bias

runtime=boundary.runtime


class MemoryPolicyTests(unittest.TestCase):
    def context(self):
        return {"time":1000,"controller":"a","members":["a"],"source":"a","preset":"comfort",
                "signature":["heater",True],"gains":[0.2,0.000035,0],"target":21,"temperature":20,
                "outdoor":5,"fresh":True,"integral":0.3}

    def test_raise_preserves_compensation_and_setback_sheds_positive_bias(self):
        pid=runtime.PID(kp=0.2,ki=0,integral=0.3,previous=20,last_target=21,output=0.5)
        self.assertAlmostEqual(pid.update(20,22,30),0.7)
        self.assertEqual(pid.integral,0.3)
        self.assertEqual(pid.derivative,0)
        self.assertAlmostEqual(pid.update(20,21,30),0.5)
        self.assertEqual(pid.integral,0.3)
        self.assertAlmostEqual(pid.update(20,22,30),0.7)
        self.assertAlmostEqual(pid.update(20,21.9,30),0.68)
        self.assertEqual(pid.integral,0.3)
        self.assertEqual(pid.update(20,20,30),0)
        self.assertEqual(pid.integral,0)

    def test_pid_terms_explain_unclamped_and_limited_outputs(self):
        pid=runtime.PID(kp=0.2,ki=0,integral=0.3)
        pid.update(20,22,30,feedforward=0.1)
        terms=pid.terms
        self.assertAlmostEqual(sum(terms[k] for k in ("proportional","integral","derivative","feedforward")),terms["unclamped"])
        self.assertAlmostEqual(terms["output"],0.8)
        pid.update(10,22,30)
        self.assertEqual(pid.terms["limit"],"high")
        pid.update(20,22,30,active=False)
        self.assertFalse(pid.terms["active"])
        self.assertEqual(pid.integral,0)

    def test_matching_fresh_context_recovers_bias(self):
        saved=self.context();current=self.context();current["time"]+=60
        self.assertEqual(recovered_bias(saved,current)[0],0.3)

    def test_changed_context_stale_inputs_and_large_outage_reject_bias(self):
        saved=self.context()
        for key,value in (("time",1901),("time",999),("fresh",False),("members",["b"]),
                          ("controller","_average"),("source","Auto"),("preset","sleep"),
                          ("signature",["other",True]),("gains",[0.4,0.000035,0]),
                          ("target",22),("temperature",22),("outdoor",9)):
            current={**saved,key:value}
            with self.subTest(key=key,value=value):
                self.assertIsNone(recovered_bias(saved,current)[0])

    def test_corrupt_or_excessive_bias_is_never_restored(self):
        for value in (float("nan"),float("inf"),0.51,-0.51,"0.3",True):
            self.assertIsNone(recovered_bias({**self.context(),"integral":value},self.context())[0])
        for value in (None,[],{},"invalid"):
            self.assertIsNone(recovered_bias(value,self.context())[0])


class RuntimeMemoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=boundary.RuntimeTests.asyncSetUp
    asyncTearDown=boundary.RuntimeTests.asyncTearDown
    set=boundary.RuntimeTests.set
    advance=boundary.RuntimeTests.advance

    async def prepare_average(self):
        self.set("sensor.a","20","°C");self.set("sensor.b","20","°C")
        await self.r.change(mode="heat",source="Average")
        self.r.pids["_average"].integral=0.35
        self.advance(30);await self.r.tick()
        return json.loads(json.dumps(self.r.saved()))

    async def test_short_restart_restores_average_bias_without_restoring_pulse(self):
        saved=await self.prepare_average()
        before=saved["pid_memory"]["integral"]
        self.advance(60)
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertIn("Restored",restored.memory_restore_status)
        self.assertAlmostEqual(restored.pids["_average"].integral,before,delta=0.002)
        self.assertFalse(restored.proposed)
        self.assertEqual(restored.pids["_average"].derivative,0)
        self.assertEqual(restored.relay.changed,self.now.timestamp())
        await restored.stop()

    async def test_saved_compensation_is_bounded_before_persistence(self):
        await self.prepare_average()
        self.r.pids["_average"].integral=0.9
        self.assertEqual(self.r.saved()["pid_memory"]["integral"],0.5)

    async def test_off_erases_saved_bias_and_group_or_source_changes_reject_it(self):
        saved=await self.prepare_average()
        await self.r.change(mode="off")
        self.assertIsNone(self.r.store.data["pid_memory"])
        saved["source"]="a"
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertNotIn("Restored",restored.memory_restore_status)
        self.assertLess(restored.pids["a"].integral,0.01)
        await restored.stop()

    async def test_stale_readings_or_warm_protection_discard_memory(self):
        saved=await self.prepare_average()
        for stale in (True,False):
            self.set("sensor.a","20" if stale else "25","°C",age=901 if stale else 0)
            restored=runtime.Runtime(self.hass,self.entry);restored.store.data=copy.deepcopy(saved)
            await restored.start()
            self.assertNotIn("Restored",restored.memory_restore_status)
            if not stale:
                self.assertFalse(restored.proposed)
            await restored.stop()

    async def test_matching_group_can_restore_only_from_fresh_occupancy(self):
        self.entry.data["reaction_time"]="fast"
        self.r=runtime.Runtime(self.hass,self.entry)
        self.set("sensor.a","20","°C");self.set("sensor.b","20","°C")
        self.set("binary_sensor.a","on");self.set("binary_sensor.b","on")
        await self.r.change(mode="heat")
        self.assertTrue(self.r.group_data["active"])
        self.r.group_pid.integral=0.3
        saved=self.r.saved()
        self.advance(60)
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertTrue(restored.group_data["active"])
        self.assertIn("Restored",restored.memory_restore_status)
        self.assertAlmostEqual(restored.group_pid.integral,0.3,delta=0.002)
        await restored.stop()

    async def test_missing_startup_sensors_recover_without_losing_saved_bias(self):
        saved=await self.prepare_average()
        self.set("sensor.a","unavailable");self.set("sensor.b","unknown")
        self.set("switch.heat","unavailable")
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertEqual(restored.mode,"heat")
        self.assertFalse(restored.proposed)
        self.assertIsNotNone(restored.pending_pid_memory)
        self.assertEqual(restored.saved()["pid_memory"]["time"],saved["pid_memory"]["time"])
        self.advance(60)
        self.set("sensor.a","20","°C");self.set("sensor.b","20","°C")
        self.set("sensor.outdoor","5","°C");self.set("switch.heat","off")
        await restored.tick()
        self.assertIn("Restored",restored.memory_restore_status)
        self.assertAlmostEqual(restored.pids["_average"].integral,saved["pid_memory"]["integral"],delta=0.005)
        self.assertFalse(restored.proposed)
        self.assertEqual(restored.relay.changed,self.now.timestamp())
        await restored.stop()

    async def test_partial_average_and_missing_outdoor_wait_for_complete_context(self):
        saved=await self.prepare_average()
        self.set("sensor.b","unavailable");self.set("sensor.outdoor","unavailable")
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertIsNotNone(restored.pending_pid_memory)
        self.advance(60);self.set("sensor.b","20","°C")
        await restored.tick()
        self.assertIsNotNone(restored.pending_pid_memory)
        self.set("sensor.outdoor","5","°C");self.advance(30)
        await restored.tick()
        self.assertIn("Restored",restored.memory_restore_status)
        await restored.stop()

    async def test_waiting_expiry_is_not_extended_by_saves_or_another_restart(self):
        saved=await self.prepare_average()
        self.set("sensor.a","unavailable")
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        waiting=restored.saved()
        await restored.stop()
        self.advance(901)
        again=runtime.Runtime(self.hass,self.entry);again.store.data=waiting
        await again.start()
        self.assertIsNone(again.pending_pid_memory)
        self.assertIn("expired",again.memory_restore_status)
        await again.stop()

    async def test_off_and_source_changes_clear_waiting_compensation(self):
        saved=await self.prepare_average();self.set("sensor.a","unavailable")
        for changes in ({"mode":"off"},{"source":"b"},{"preset":"sleep"}):
            restored=runtime.Runtime(self.hass,self.entry);restored.store.data=copy.deepcopy(saved)
            await restored.start()
            self.assertIsNotNone(restored.pending_pid_memory)
            await restored.change(**changes)
            self.assertIsNone(restored.pending_pid_memory)
            await restored.stop()

    async def test_restored_placeholders_do_not_count_as_valid_feedback(self):
        saved=await self.prepare_average()
        self.hass.values["switch.heat"].attributes["restored"]=True
        self.hass.values["sensor.a"].attributes["restored"]=True
        restored=runtime.Runtime(self.hass,self.entry);restored.store.data=saved
        await restored.start()
        self.assertIsNone(restored.actual)
        self.assertIsNone(restored.room_data["a"]["temperature"])
        self.assertFalse(restored.proposed)
        self.assertIsNotNone(restored.pending_pid_memory)
        await restored.stop()
