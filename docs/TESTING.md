# Verification and release

Run locally with Python 3.12+:

```
python -m unittest discover -s tests -v
python scripts/check_release.py
python scripts/build_release.py
```

The unittest suite covers occupancy decay, unit validation, derivative kick,
windup, minimum relay dwell, small-demand pulse accumulation, bounded deadlines,
known delayed synthetic plants, model rejection, and missing-data handling. Runtime
tests use explicitly mocked HA boundary objects to verify Shadow behavior,
unavailable sensors, confirmed Away presence, emergency Off, schedules, command
failure, independent per-room gains, and dedicated Average control/tuning.

For real HA testing on Linux using HA's required Python version:

```
pip install pytest-homeassistant-custom-component 'homeassistant>=2026.10.0,<2026.11.0'
python -m pytest ha_tests -v
```

Twelve integration tests exercise the actual config flow, setup/unload, duplicate
heater checks, invalid-room handling, independent room/Average options, and active
shutdown, integration visibility, Fahrenheit input/output, entry migration and
native weekly schedule preheat/restoration. They pass in Linux GitHub CI alongside
the core/runtime suite (53 tests in the current local build). CI runs
them separately so local HA fakes cannot contaminate real HA imports. The available
Windows runtime is Python 3.12; real HA verification was performed on Linux.

Before a stable release, install in a development HA instance, test broader
options/edit/remove/reload and Fahrenheit display conversion, and gather shadow
evidence on a real slow heating system. Then commission one relay with the existing
controller disabled and measure temperature overshoot, arrival-time error, cycle
durations and missing-sensor behavior across multiple weather conditions. A passed
synthetic test does not establish household performance.

The release checker parses Python and JSON, validates matching manifest/HACS
metadata and English strings, and rejects unexpected executable/data artifacts.
It also verifies brand PNG dimensions and transparency, local README links, and
the HACS install-link parameters. The release ZIP includes integration source,
localization and bundled HA icons, without caches
or household data. This is currently an alpha package, not a published HACS listing.

The repository links use the chosen Comfort-Sense-Thermostat-HA project. Use
a version tag and attach the generated integration
ZIP after CI passes. Broader HACS catalog inclusion is a separate submission.
