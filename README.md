<p align="center">
  <img src="docs/assets/logo.png" alt="Comfort Sense Thermostat logo" width="160" />
</p>

<h1 align="center">Comfort Sense Thermostat</h1>

<p align="center"><strong>Comfort in the rooms you use. Warmth when you need it.</strong><br />
Room-aware heating for Home Assistant, with gradual occupancy changes and learning for slow heating systems.</p>

<p align="center">
  <a href="https://github.com/spikked27/Comfort-Sense-Thermostat-HA/actions/workflows/validate.yml"><img src="https://github.com/spikked27/Comfort-Sense-Thermostat-HA/actions/workflows/validate.yml/badge.svg" alt="Validation status" /></a>
  <img src="https://img.shields.io/badge/Home_Assistant-2026.10%2B-18BCF2" alt="Home Assistant 2026.10 or newer" />
  <img src="https://img.shields.io/badge/HACS-custom_repository-41BDF5" alt="HACS custom repository" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Experimental alpha" />
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=spikked27&amp;repository=Comfort-Sense-Thermostat-HA&amp;category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Add Comfort Sense Thermostat to HACS" /></a>
</p>

<p align="center"><a href="docs/GETTING_STARTED.md">Getting started</a> · <a href="docs/USER_GUIDE.md">User guide</a> · <a href="docs/MIGRATION.md">Switching from Smart Thermostat</a> · <a href="https://github.com/spikked27/Comfort-Sense-Thermostat-HA/issues">Help &amp; issues</a></p>

## What it does

Most thermostats measure one spot in your home. Comfort Sense uses the rooms you
actually spend time in. Add your room temperature and occupancy sensors, choose
one thermostat target, and let Auto follow the most occupied room using a moving occupancy window.
You can also pin a room or use the whole-home average.

| Feature | What it means for you |
|---|---|
| **Room-aware comfort** | One thermostat target follows the most occupied room or equally averages rooms within an adjustable occupancy tolerance. |
| **A proper Average mode** | An equal-room average has its own PID controller and tuning settings, including in Away mode. |
| **Your choice of tuning** | Automatic validated tuning by default; optional manual tuning for each room and Average. |
| **Learning for slow heat** | Learns from ordinary heating, rather than forcing a rapid on/off autotune experiment. |
| **Outdoor temperature** | Helps estimate heat loss and how early a room needs to start warming. |
| **Morning comfort** | Use weekly blocks or phone alarms as arrival times; learned models estimate warm-up lead. |
| **Away, Sleep and Boost** | Use a lower away target, focus on a sleeping room, or apply a temporary boost. |
| **Try it alongside your thermostat** | Shadow mode calculates demand and learns without commanding your heater. |

Comfort Sense controls **one heating switch for one shared heating zone**. All rooms
receive heat together; Auto follows the leading occupancy group. Independent heating zones need separate hardware. Operation and learning stay local to Home Assistant.

## Install with HACS

[![Add Comfort Sense Thermostat to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spikked27&repository=Comfort-Sense-Thermostat-HA&category=integration)

1. Click the button above and open your Home Assistant instance.
2. Add the repository when prompted, then **download Comfort Sense Thermostat** in HACS.
3. **Restart Home Assistant.**
4. Go to **Settings → Devices & services → Integrations → Add integration** and choose
   **Comfort Sense Thermostat**.
5. Choose your heating switch, outdoor temperature sensor, and home-presence source.
   Keep **Shadow mode enabled**, then add your rooms and their sensors.
6. Review the setup and select **Heat** on the new thermostat to start shadow evaluation.

**Requirements:** Home Assistant 2026.10+, HACS for button installation, one heating
switch, and at least one room temperature sensor. Occupancy and home-presence sensors
enable room priority and automatic Away. Outdoor temperature enables thermal learning;
manual PID works without it.

If the button cannot open your instance, add
https://github.com/spikked27/Comfort-Sense-Thermostat-HA through **HACS → Custom
repositories**, choose **Integration**, and download it. This is a custom repository;
it is not yet included in the default HACS catalog.

[Full installation, manual installation, and troubleshooting →](docs/GETTING_STARTED.md)

> [!IMPORTANT]
> **Experimental alpha — start in Shadow mode.** Active control needs commissioning
> on your heating system. HA restarts and options reloads leave the thermostat **Off**
> in this alpha; select Heat to resume. Disable the previous controller before
> turning Shadow off. Temperature fields and the climate card use your
> Home Assistant **Celsius or Fahrenheit** preference.

## Everyday use

| Control | Use it for |
|---|---|
| **Thermostat card** | Heat/Off, the comfort target, and Comfort/Away/Sleep/Boost presets. |
| **Temperature source** | Auto, Average, or a particular room. |
| **Active room and Room occupancy** | Seeing which room Auto follows and its recent occupancy score. |
| **Native Schedule helpers** | Editing weekly time blocks separately from equipment and room settings. |
| **Room and Average temperature sensors** | Readings, learning status and excluded sensors. |
| **Heat demand and Control status** | Understanding heat requests and Shadow behavior. |

The thermostat dial sets one **comfort target**, carried across Auto, pinned rooms and Average. Away uses its configured target and the dedicated Average controller. Boost expires automatically. Basic setup has six fields; presets, relay limits and Average PID live in **Configure → Advanced**.

For morning warm-up, create a **Schedule helper** using HA's weekly time-block
editor, then connect it under **Comfort Sense → Configure → Scheduling**. Choose
a room or Average, a target and whether to preheat. A weekday block from 07:00 to
09:00 means *aim to be comfortable at 07:00 and maintain it until 09:00*. Lead times
remain estimates; changing weather and heating capacity can affect the result.

Morning comfort can also follow the earliest next alarm from selected phones, with optional person associations. Open **Configure → Scheduling → Morning comfort from phone alarms**. See **Ready by** and **Estimated heating start** on the device page.

[Weekly schedules, phone alarms and preheating →](docs/SCHEDULING.md)

[Presets, schedules, tuning choices and diagnostics explained →](docs/USER_GUIDE.md)

[Dashboard cards for active room, temperatures and occupancy →](docs/DASHBOARD.md)

[Occupancy grouping, live Configuration entities and room protection →](docs/ROOM_PROTECTION.md)

## Documentation and support

- [Getting started](docs/GETTING_STARTED.md) — installation, first room and commissioning.
- [User guide](docs/USER_GUIDE.md) — controls, schedules, tuning and common questions.
- [Migration](docs/MIGRATION.md) — replace Smart Thermostat and room templates.
- [Control design](docs/CONTROL.md) — PID units, thermal models and learning quality gates.
- [Weekly schedules](docs/SCHEDULING.md) — the native HA editor, bindings and preheating.
- [Verification](docs/TESTING.md) — control/runtime and real Home Assistant integration tests.
- [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Security and privacy](SECURITY.md).

For help, [open an issue](https://github.com/spikked27/Comfort-Sense-Thermostat-HA/issues/new/choose)
with your version, symptoms and redacted diagnostics. Keep household histories and
credentials out of public reports. Field comfort and warm-up performance still need
validation on real heating systems.

MIT licensed. An independent community project, not an official Home Assistant integration.
