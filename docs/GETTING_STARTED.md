# Getting started

[← Overview](../README.md) · [User guide](USER_GUIDE.md)

Comfort Sense uses your existing Home Assistant sensors and heating switch. You
do not need separate room-switching templates or a second PID integration.

## Before you install

| You need | How it is used |
|---|---|
| Home Assistant **2026.10+** | Runs the integration and displays its controls. |
| One switch that requests heat | Receives On/Off commands in active mode. |
| Room temperature sensors | At least one for each configured room. |
| Binary occupancy sensors, optional | Report On while a room is occupied. |
| Outdoor temperature, recommended | Enables learning of heating response and outdoor heat loss. |
| Home presence, recommended | A person, tracker, binary home sensor or home-zone person count for automatic Away. |

This alpha supports a heating relay. It does not directly control cooling,
compressors, multi-stage equipment or a modulating boiler bus.

## 1. Download through HACS

[![Add Comfort Sense Thermostat to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spikked27&repository=Comfort-Sense-Thermostat-HA&category=integration)

The button opens this repository in your instance's HACS interface. If My Home
Assistant asks for your instance address, enter the address you normally use to
open HA. Confirm adding the custom repository, then choose **Download**.

If you prefer the manual HACS route:

1. Open **HACS → menu → Custom repositories**.
2. Enter `https://github.com/spikked27/Comfort-Sense-Thermostat-HA`.
3. Choose category **Integration** and add it.
4. Find **Comfort Sense Thermostat** and download it.
5. Restart Home Assistant.

Without HACS, copy `custom_components/comfort_sense` from this repository to
`/config/custom_components/comfort_sense`, then restart HA. Include its `brand`
subfolder so the logo and icon are installed too.

## 2. Create the thermostat

Open **Settings → Devices & services → Integrations → Add integration**, then select
**Comfort Sense Thermostat**. Existing entries created by 0.1 migrate automatically
and appear in the Integrations view after updating and restarting; do not recreate them.

Choose a name and the heating switch. Select your outdoor temperature and
home-presence sources. Keep **Shadow mode** enabled during the first evaluation;
the old thermostat can continue controlling the relay while Comfort Sense observes.

System settings also contain Away, Sleep and Boost targets; relay timing; and the
dedicated **Average PID** mode and manual gains. Use timing suitable for your
equipment. Defaults are twenty-minute PWM and five-minute minimum On/Off times.

Setup fields and room target controls follow your HA temperature-unit preference.
If HA uses Fahrenheit, enter Fahrenheit values directly. Internally stored targets
remain unchanged when upgrading. Useful equivalents are:

| Fahrenheit | Celsius |
|---|---|
| 65°F | 18.3°C |
| 68°F | 20.0°C |
| 70°F | 21.1°C |
| 72°F | 22.2°C |

## 3. Add rooms

Choose **Add room**, enter a unique name, and select its temperature sensors.
Prefer physical sensors over a helper that switches between rooms. Input sensors
must report °C, °F or Kelvin; Comfort Sense converts them before control.

Choose binary occupancy sensors that reflect time spent in the room. Any selected
sensor On counts as occupied. Without occupancy sensors, manual room selection
and Average still work.

Set the comfort target and choose **Manual PID gains** or **Automatic validated
room tuning**. Every room and Average choose independently. Automatic mode uses
your manual gains until reliable learning data is available. Supplied gains are
starting points, rather than a universal heating-system tune.

Repeat for your other rooms, then choose **Review and save**. Weekly timing is
configured separately with native Schedule helpers under the integration's
**Configure → Scheduling** section. See [weekly scheduling](SCHEDULING.md).

## 4. Evaluate in Shadow mode

The thermostat starts **Off**. Select **Heat** to calculate demand without sending
relay commands. Review the new device's entities:

- **Room temperature:** plausible readings and expected sensor exclusions?
- **Temperature source:** gradual priority for rooms you use?
- **Heat demand:** sensible proposed heating requests?
- **Average temperature:** a reasonable equal-room mean?
- **Learning status:** enough reliable observations for each controller?
- **Morning plan:** a plausible lead time and reachability estimate?

Thermal learning needs room and outdoor temperatures plus observed relay states.
At least 48 hours and twelve heating transitions are required. That is a minimum,
not a promise of an accepted model; nearly constant heating or noisy data can need
more useful observations.

## 5. Switch to active control

After reviewing Shadow behavior, disable the previous thermostat and any scripts
or automations controlling the same relay. Use the [migration guide](MIGRATION.md)
when replacing Smart Thermostat.

Open the integration's **Configure** menu, choose **Equipment and Average PID**, turn Shadow off,
and finish the review. Select **Heat** after the reload. Comfort Sense now commands
the switch while respecting the configured cycle limits.

**Restarts and options reloads leave the alpha Off.** Select Heat to resume.

## Troubleshooting

| Symptom | Check |
|---|---|
| HACS button cannot open HA | Set your instance URL in My Home Assistant, or use the manual HACS steps. |
| Cannot find the integration | Confirm `/config/custom_components/comfort_sense`, restart HA, and search under **Integrations**. Versions 0.1 appeared only under Helpers; update first. |
| No heat after installation or restart | Select **Heat**. Confirm Shadow is off if you intend active control. |
| A room has no temperature | Check units, availability, report age and `excluded_sensors`. |
| No learned model | Check outdoor and relay availability; read that controller's learning status. |
| Away never activates | Configure home presence and allow the confirmed-absence delay to pass. |
| Morning target is missed | Check weekdays, local timezone, maximum preheat and reported reachability. |

For more detail, read the [user guide](USER_GUIDE.md). Report issues with integration
and HA versions, symptoms, and redacted diagnostics.
