# Security and privacy

Comfort Sense Thermostat makes no external network calls. It reads selected HA sensor states and
commands only the configured switch in active mode. Shadow mode does not command
the heater. Use a single active controller per physical heating relay.

Local learning buffers in HA `.storage` contain household temperature and heating
history. Room diagnostics can reveal occupancy and room names. Share redacted
diagnostics, not complete storage, configuration or archives. Keep HA backups and
access controls appropriate for private household data.

For a suspected vulnerability, contact the repository maintainer privately through
GitHub's security reporting mechanism when enabled. Do not post credentials or
private household evidence in a public issue.
