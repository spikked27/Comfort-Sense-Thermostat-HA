# Schedules and morning comfort

[← Overview](../README.md) · [User guide](USER_GUIDE.md)

Comfort Sense uses Home Assistant's native **Schedule helpers**. Edit times in the
familiar weekly grid, independently of your rooms, sensors or heating equipment.
Phone alarms can supply a morning deadline to the same warm-up planner.

## Phone-alarm morning comfort

Open **Configure → Scheduling → Morning comfort from phone alarms**. Enable it,
select your phone next-alarm timestamp sensors, choose a target and room/Auto/Average,
and set the hold duration. For example: **68°F by the next alarm, hold 60 minutes**.
The default target is 20°C / 68°F. It is independent of the ordinary thermostat
target, which resumes when the hold ends. The earliest valid phone alarm wins.
No separate scheduler, custom card, or automation is needed.

Under Scheduling, **Associate an alarm with a person (optional)** lets you link each
phone to its HA `person` entity. Only alarms whose associated person is **home**
participate; unknown/unavailable presence excludes that phone. Repeat for the
other phone. Leave Person empty to remove a mapping. Without mappings, the
thermostat's overall home/away detection applies; it cannot distinguish which
owner is home. Owner mappings are shown in the form description when editing.

Use a dedicated room if you want the bedroom ready regardless of nighttime
occupancy history. Auto follows occupancy; Average warms the equal-room average.
Room protection still covers all rooms.

Alarms must have timezone-aware timestamps within the next 24 hours, or be within
the current hold period. The integration listens for changes to selected alarms
and owners, and checks again every 30 seconds. Before firing, changing an alarm
replans warm-up; clearing it or making it unavailable cancels that phone's plan.
After firing, the current event is retained until its hold ends even if the phone
clears it or advances to tomorrow. A second phone or snooze does not extend the
same day's morning session. Fired events and completed local days are persisted.
If an owner leaves home, their alarm stops participating. All selected clock-app
alarms count, including naps; choose appropriate sources. Android's Next Alarm
allow list should select your actual clock app:
[Companion alarm sensor documentation](https://companion.home-assistant.io/docs/core/sensors/#next-alarm-sensor).

Alarms have priority **10**; weekly helpers default to **0**. You can set a weekly
binding above 10 under its Advanced settings to override morning comfort.
If no valid alarm exists, native weekly schedules continue independently.
Off stays Off, confirmed Away suppresses schedules, and manual Boost takes
temporary priority. Shadow calculates plans without commanding the heater.
Restart still leaves the thermostat Off; select Heat to resume.

## Learning and ready-by status

Normal heating observations identify each room's heat delivery delay, heating rate
and outdoor heat loss. Automatic PID tuning and the warm-up planner share those
validated models. Initially, a conservative fallback rate plans warm-up. A model
needs at least 48 hours, 400 valid samples and 12 heating transitions, plus validation;
48 hours alone does not guarantee acceptance. Outdoor and relay observations are
required for learning. Manual PID remains available independently of preheating.

Once preheat starts, it stays active through the deadline, maintaining the target
until the weekly block or alarm hold ends. **Ready by** and **Estimated heating
start** sensors show the selected plan (or nearest future plan), its target,
confidence and reachability. Control status reports preheating versus scheduled
comfort. The ordinary **Active room** sensor continues to name the rooms controlled.

Successful uninterrupted real-heating arrivals with a validated model also record
arrival error and slowly adjust future model lead times for that temperature source.
Each arrival changes the correction by at most five minutes, bounded to ±30 minutes
overall and the maximum preheat limit. Shadow runs, unavailable inputs, interrupted
plans, protection overrides, command failures and overlapping independent-room plans
do not train these corrections. Source corrections persist across restart and reset
when the heater, outdoor sensor or room sensor signatures change. These estimates
cannot guarantee arrival when heating capacity or room protections prevent it.

## Create a schedule

1. Open **Settings → Devices & services → Helpers → Create helper → Schedule**.
2. Name it, such as **Weekday morning comfort**.
3. Drag blocks on the days you want. For example, Monday–Friday **07:00–09:00**.
4. Save it.
5. Open **Integrations → Comfort Sense Thermostat → Configure → Scheduling**.
6. Choose **Connect a Schedule helper**, select it, and choose a room, **Auto** or
   **Average**, your desired target, and whether to preheat. Review and save.

When preheat is enabled, **the block start is the desired comfort arrival time**.
Comfort Sense estimates how early to start using the selected room's model, or
Average's model for Average control. The schedule block stays unchanged: 07:00 is
still the time you asked for comfort, even if warm-up begins at 05:00.

With preheat disabled, the target takes effect at the block start. At the block
end, ordinary Comfort/Sleep/occupancy control resumes. Schedules do not turn an Off
thermostat on. Confirmed Away suppresses scheduling, and manual Boost temporarily
takes precedence.

## Scheduling settings

| Setting | Purpose |
|---|---|
| **Schedule helper** | Owns the weekly timing. Edit its blocks in HA Helpers. |
| **Temperature source** | A room, occupancy-based Auto, or the dedicated Average controller. |
| **Scheduled target** | Target for blocks without a temperature override, in your HA temperature unit. |
| **Warm up before a block starts** | Enable learned/fallback preheat to aim for comfort at the start. |
| **Priority (advanced)** | Default zero. Higher values win when separate schedules overlap. |
| **Block data temperature unit (advanced)** | Unit for any optional numeric temperature values in the helper's Additional data. |

**Scheduling → Advanced settings for [schedule]** contains priority and block-data units; the normal connection form has only five fields.

**Scheduling → Warm-up planning settings** controls maximum preheat and the fallback
warming rate. Both live in Scheduling, rather than equipment or room setup. Warming
rates follow HA's temperature unit; for example, 0.5°C/hour is 0.9°F/hour.

## Optional block overrides

A connected helper can use different targets or rooms in different blocks. Open a
block in HA's weekly editor and add optional **Additional data**, for example:

```yaml
temperature: 70
temperature_unit: "°F"
source: Living Room
```

Another block might contain:

```yaml
temperature: 65
temperature_unit: "°F"
source: Average
```

Without these fields, the binding's target and source are used. A block temperature
without an explicit unit uses the binding's selected **Block data temperature unit**.
That unit is saved so a later HA unit-preference change does not reinterpret old
schedule data. Sources can be Auto, Average, or an exact configured room name.

Comfort Sense reads the complete weekly schedule using HA's `schedule.get_schedule`
action. This makes preheat possible before the helper switches On. Changes are
picked up on schedule state/attribute changes, and the weekly definitions refresh
at least once a minute. No other thermostat automation is needed.

## Overlap, overnight blocks and daylight saving

Home Assistant rejects overlapping blocks within one helper. To cross midnight,
create touching blocks on consecutive days, such as **22:00–24:00** and
**00:00–05:00**. Comfort Sense accepts HA's midnight representation.

Across connected helpers, the highest-priority plans win. Equal-priority plans for
separate individual rooms share heat using the largest room demand. Mixed Auto,
Average and individual-room sources choose a deterministic winner; use distinct
priorities when you want an explicit preference. Within a helper, preheat can
anticipate a higher target in the next touching block.

Times use HA's configured timezone. Nonexistent spring-forward times roll forward;
repeated autumn times use the first occurrence. Preheat remains bounded by the
configured maximum and actual heating capacity. A reachable plan is an estimate,
not a promise that weather changes cannot affect the arrival temperature.

## Upgrading old morning settings

The 0.1 room-level morning settings are removed from room configuration. Any enabled
morning plan migrates into an independent schedule binding so timing and targets
continue to work. It is labelled **migrated** in Scheduling.

To edit its timing with HA's weekly grid, create a Schedule helper with equivalent
blocks, then edit the migrated binding and connect that helper. Room IDs, comfort
targets, PID gains and stored learning data are preserved. Disabled old morning
fields are simply removed. You do not need to delete or recreate the integration.

The [official Schedule helper documentation](https://www.home-assistant.io/integrations/schedule/)
explains its weekly editor, Additional data and native actions.
