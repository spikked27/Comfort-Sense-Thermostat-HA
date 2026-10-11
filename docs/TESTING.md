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

These integration tests exercise the actual config flow, setup/unload, duplicate
heater checks and invalid-room handling. CI runs them separately so local HA fakes
cannot contaminate real HA imports. **They have not yet been executed locally**;
the available Windows runtime is Python 3.12 and cannot host current HA.

Before a stable release, run Linux CI, install in a development HA instance, test
options/edit/remove/reload and Fahrenheit display conversion, and gather shadow
evidence on a real slow heating system. Then commission one relay with the existing
controller disabled and measure temperature overshoot, arrival-time error, cycle
durations and missing-sensor behavior across multiple weather conditions. A passed
synthetic test does not establish household performance.

The release checker parses Python and JSON, validates matching manifest/HACS
metadata and English strings, and rejects unexpected executable/data artifacts.
The release ZIP includes only integration source and localization, without caches
or household data. This is currently an alpha package, not a published HACS listing.

The repository links use the chosen Comfort-Sense-Thermostat-HA project. Use
a version tag and attach the generated integration
ZIP after CI passes. Broader HACS catalog inclusion is a separate submission.
