# Weekly schedules

[← Overview](../README.md) · [User guide](USER_GUIDE.md)

Comfort Sense uses Home Assistant's native **Schedule helpers**. Edit times in the
familiar weekly grid, independently of your rooms, sensors or heating equipment.

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
| **Priority** | Higher values win when separate schedules overlap. |
| **Block data temperature unit** | Unit for any optional numeric temperature values in the helper's Additional data. |

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
