# Control design

## Occupancy and measurement

Every room has a score between zero and one. Any selected occupancy sensor reporting
On raises it with a five-minute exponential time constant by default. Off or unknown
occupancy decays it over thirty minutes. Scores are updated using elapsed time,
then squared and normalized to favor the most occupied room gradually. No arbitrary
pair-of-rooms thresholds are needed. No significant occupancy falls back to Average;
this is distinct from Away, which requires a confirmed home-absence signal.

A room uses the median of valid temperature readings (the midpoint for an even
number). This resists one outlier when at least three independent sensors are
available. Unknown, unavailable, nonfinite, implausible, missing-unit, and stale
readings are excluded. The default freshness allowance is three hours; choose a
limit consistent with sensor report intervals. `last_reported` includes unchanged
readings on supported HA versions. A template that keeps republishing stale upstream
data cannot be diagnosed automatically; prefer physical sensor entities.

Room controllers use their own measurements. The algorithm never differentiates a
temperature that abruptly switches from one room to another. This removes source
changes as false temperature slopes. Room demand is occupancy weighted when multiple
rooms are in use. Manual room selection gives that room full priority.

## Dedicated Average controller

Average is an equal-room mean, rather than a mean over all physical sensors. A room
with three sensors has the same house-average weight as a room with one sensor.
The average target is the mean of included room targets, or the common Away/Boost
target when those presets apply. Average has independent Kp/Ki/Kd and Manual/Automatic
tuning. Its controller produces the output directly, rather than averaging room PID
outputs. Automatic no-occupancy fallback also uses this controller.

The average's derivative and integral reset whenever valid-room membership changes.
Its learned model and gains are used only with complete configured membership;
otherwise it temporarily uses its manual fallback gains. Learning samples are only
collected when all configured rooms are valid. Unavailable-room events must be
reviewed before trusting learning or comfort predictions.

## PID and relay

Each active controller uses proportional error, a bounded integral with conditional
anti-windup, and a low-pass-filtered derivative on measurement. Inactive controllers
clear integral. Stored excess integral is removed after a substantial target setback.
An accepted automatic model can supply bounded outdoor-loss feedforward. Manual
mode never silently replaces selected gains.

Positive measured temperature slope is projected through the learned delivery delay,
or a ten-minute fallback. A projected overshoot of 0.3°C removes demand and positive
integral. This is an overshoot limiter, not a guarantee: unmodelled solar gains and
heat already stored in the system can still warm the room after the relay turns off.

Slow PWM defaults to twenty minutes with five-minute minimum on/off times. Tiny duty
requests accumulate across windows instead of disappearing below a minimum pulse
width. Actual relay state establishes dwell timing. Manual Off and invalid-input or
high-temperature shutdown override minimum-on duration. Active mode reasserts the
desired relay state every thirty seconds for retry/watchdog-compatible keepalive.
Unavailable relay feedback suppresses heat and retries Off; a failed command is
reported, not treated as confirmed actuation.

An independent equipment watchdog and original furnace limits remain important:
software cannot switch off an unreachable relay. This controls a simple heating
switch, not a compressor, modulating boiler bus, multi-stage furnace, or cooling loop.

## Passive slow-system identification

Thirty-second observations are retained for at most fourteen days. Temperature
slopes use overlapping fifteen-minute intervals on a five-minute grid to reduce
quantization noise on slow systems; relay observations are integrated
over the delayed interval. A small least-squares model estimates:

```
dT/dt = h * observed_heat(t - delay) - c * (T - outdoor) + b
```

Here `h` is °C/hour at full duty, `c` is 1/hour, and `b` is background °C/hour.
The relay is a proxy for delivered heat, so delays, burner cycling, sensor precision,
sun, windows and household gains can confound identification. An unreliable fit is
rejected rather than forcing a gain recommendation.

Delay candidates range from zero to three hours in five-minute steps. The first 75%
of observations fit/select the delay. The final 25% is an untouched chronological
holdout. All delays use the same initial coverage. At least 48 hours, 400 valid
observations, twelve heater transitions, and both heating states in the holdout are
required. Singular fits, implausible coefficients, discontinuous data, and extreme
slopes are rejected. No slope window crosses the train/holdout boundary, and
outages start new segments that cannot be bridged even if brief. Held-out slope
RMSE must be at most 0.6°C/hour and improve at
least 25% over a constant training-slope baseline. These gates are engineering
filters; they are not a calibrated statistical confidence interval.

Validated first-order-plus-delay models yield conservative PI recommendations based
on [Skogestad's SIMC method](https://skoge.folk.ntnu.no/publications/2003/tuningPID/README.html).
The response time is deliberately slow and includes PWM-equivalent delay. Gains are
bounded; automatic Kd is zero because this model does not identify a second thermal
lag well enough to justify an aggressive derivative term. Identification runs every
six hours off HA's event loop, without running a relay excitation experiment.

Models are invalidated after fourteen days without refresh or when sensor/actuator
configuration changes. Each room and Average can opt into automatic adoption
independently. Saved manual fallback settings remain the user's chosen values.

## Morning warm-up

A validated room model estimates full-power reach time from a cold start, including
cooling during delivery delay. A 15% allowance advances the start. Until a model is
available, a configurable 0.5°C/hour default and thirty-minute allowance estimate
lead time. Maximum preheat is four hours by default. This bounded fallback is a
planning estimate, not a causal tune derived from historical temperature rises.

Weekly time blocks live in native HA Schedule helpers. Equipment, room and
scheduling settings are separate. Bindings choose a target, source and priority;
optional block data can override target/source. The read-only schedule.get_schedule
action supplies future blocks so preheating can begin before a helper turns On.

The schedule evaluates weekly blocks in the HA timezone, so preheating
can start before midnight and connected overnight blocks can span a date boundary. Spring DST
nonexistent wall times roll forward by the timezone round trip; repeated autumn
times use the first occurrence. The active room controllers use the largest scheduled
demand when several morning targets compete for a shared relay. All safety and
cycling limits still apply. Each plan reports its deadline, lead time, learned versus
fallback basis, and reachability.

## References

The existing [Smart Thermostat integration](https://github.com/ScratMan/HASmartThermostat)
provides the baseline functionality this project replaces. Comfort Sense Thermostat's implementation
is original; upstream code was inspected to understand units and restored gains.
HA integration/entity boundaries follow the official [config-flow documentation](https://developers.home-assistant.io/docs/core/integration/config_flow/)
and [climate entity contract](https://developers.home-assistant.io/docs/core/entity/climate/).
