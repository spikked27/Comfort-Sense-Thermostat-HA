"""Passive first-order-plus-delay thermal identification; no relay oscillation test.

Fit dT/dt = h*u(t-delay) - c*(T-T_out) + b from actual relay observations.
Rates use C/hour. Search delay on training only, then score untouched holdout.
"""
from bisect import bisect_right
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Sample:
    time: float
    temperature: float
    outdoor: float
    heat: float
    segment: int = 0


@dataclass(frozen=True)
class ThermalModel:
    heat_rate: float
    loss_rate: float
    bias: float
    delay: float
    validation_rmse: float
    improvement: float
    fitted_at: float
    samples: int

    def to_dict(self):
        return asdict(self)

    def gains(self, pwm_seconds=1200):
        # FOPDT gain K=h/c, time constant tau=1/c. Conservative SIMC PI.
        tau = 3600 / self.loss_rate
        gain = self.heat_rate / self.loss_rate
        delay = max(300, self.delay, pwm_seconds / 2)
        response = max(3600, 3 * delay, 0.25 * tau)
        kp = tau / (gain * (response + delay))
        ti = min(tau, 4 * (response + delay))
        return min(0.8, max(0.02, kp)), min(0.0002, max(0.000001, kp / ti)), 0.0

    def feedforward(self, target, outdoor):
        return max(0, min(1, (self.loss_rate * (target - outdoor) - self.bias) / self.heat_rate))

    def time_to_target(self, temperature, target, outdoor):
        if temperature >= target:
            return 0.0
        # Conservative cold-start assumption: room can cool during delivery delay.
        temperature = self.forecast(temperature, outdoor, 0.0, self.delay)
        equilibrium = outdoor + (self.heat_rate + self.bias) / self.loss_rate
        if equilibrium <= target:
            return math.inf
        return self.delay + 3600 / self.loss_rate * math.log(
            (equilibrium - temperature) / (equilibrium - target))

    def forecast(self, temperature, outdoor, duty, seconds):
        equilibrium = outdoor + (self.heat_rate * duty + self.bias) / self.loss_rate
        return equilibrium + (temperature - equilibrium) * math.exp(-self.loss_rate * seconds / 3600)


def solve(matrix, vector):
    """Small least-squares normal system with partial pivoting; reject singular data."""
    rows = [list(row) + [v] for row, v in zip(matrix, vector)]
    n = len(vector)
    for i in range(n):
        pivot = max(range(i, n), key=lambda j: abs(rows[j][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        if abs(rows[i][i]) < 1e-9:
            raise ValueError("Insufficient independent excitation")
        scale = rows[i][i]
        rows[i] = [x / scale for x in rows[i]]
        for j in range(n):
            if j != i:
                scale = rows[j][i]
                rows[j] = [a - scale * b for a, b in zip(rows[j], rows[i])]
    return [row[-1] for row in rows]


def fit_rows(rows):
    matrix = [[sum(x[i] * x[j] for x, _ in rows) for j in range(3)] for i in range(3)]
    vector = [sum(x[i] * y for x, y in rows) for i in range(3)]
    return solve(matrix, vector)


def mse(rows, coefficients):
    return sum((sum(a * b for a, b in zip(x, coefficients)) - y) ** 2
               for x, y in rows) / len(rows)


def identify(samples, previous=None):
    """Return accepted candidate and human-readable status. At least 48h required."""
    data = sorted(samples, key=lambda s: s.time)
    if len(data) < 400 or data[-1].time - data[0].time < 48 * 3600:
        return None, "Collecting: need at least 48 hours and 400 valid samples"
    # Distinct on/off transitions, not just hours of unchanged relay state.
    if sum(a.heat != b.heat and a.segment == b.segment for a, b in zip(data, data[1:])) < 12:
        return None, "Collecting: need at least 12 observed heating transitions"
    times = [s.time for s in data]
    # Preserve 30-second relay observations while fitting 5-minute temperature slopes.
    coarse = [data[0]]
    for sample in data[1:]:
        if sample.time - coarse[-1].time >= 300:
            coarse.append(sample)
    split = data[int(len(data) * 0.75)].time
    best = None
    for delay in range(0, 10801, 300):
        train, holdout = [], []
        # Overlapping fifteen-minute slopes reduce quantization noise on slow plants.
        for a, z in zip(coarse, coarse[3:]):
            dt = z.time - a.time
            if not 840 <= dt <= 1200 or a.segment != z.segment:
                continue
            if a.time - data[0].time < 10800:
                continue  # same initial coverage for every candidate delay
            # Require complete contiguous delayed-input coverage, never bridge outages.
            begin, end = a.time - delay, z.time - delay
            first = bisect_right(times, begin) - 1
            last = bisect_right(times, end) - 1
            current_first = bisect_right(times, a.time) - 1
            current_last = bisect_right(times, z.time) - 1
            if first < 0 or any(times[j+1] - times[j] > 420 for j in range(first, last)) or any(times[j+1]-times[j]>420 for j in range(current_first,current_last)):
                continue
            if any(data[j].segment != a.segment for j in range(first,current_last+1)):
                continue
            if a.time < split <= z.time:
                continue  # no feature windows overlapping the chronological split
            total = 0.0
            for j in range(first, last + 1):
                lo, hi = max(begin, times[j]), min(end, times[j+1] if j+1 < len(times) else end)
                total += max(0, hi-lo) * data[j].heat
            heat = total / dt
            slope = (z.temperature - a.temperature) * 3600 / dt
            if abs(slope) > 6:  # windows, moved sensors, discontinuities
                continue
            row = ([heat, -((a.temperature+z.temperature)/2 - (a.outdoor+z.outdoor)/2), 1.0], slope)
            (train if z.time < split else holdout).append(row)
        if len(train) < 250 or len(holdout) < 100:
            continue
        try:
            coefficients = fit_rows(train)
        except ValueError:
            continue
        h, c, b = coefficients
        if not (0.05 <= h <= 10 and 0.002 <= c <= 0.5 and abs(b) <= 2):
            continue
        score = mse(train, coefficients)
        if best is None or score < best[0]:
            best = (score, coefficients, delay, train, holdout)
    if best is None:
        return None, "Rejected: insufficient excitation or implausible thermal model"
    _, coefficients, delay, train, holdout = best
    baseline = sum(y for _, y in train) / len(train)
    baseline_mse = sum((y-baseline)**2 for _, y in holdout) / len(holdout)
    error = mse(holdout, coefficients)
    improvement = 1 - error / max(1e-9, baseline_mse)
    # Holdout must include both heating states and enough temperature response.
    heat = [x[0] for x, _ in holdout]
    if max(heat) - min(heat) < 0.5 or improvement < 0.25 or math.sqrt(error) > 0.6:
        return None, "Rejected: held-out prediction did not meet quality gates"
    candidate = ThermalModel(*coefficients, float(delay), math.sqrt(error), improvement,
                             data[-1].time, len(train)+len(holdout))
    if previous is not None and mse(holdout, [previous.heat_rate, previous.loss_rate, previous.bias]) < error * 0.95 and previous.delay == candidate.delay:
        return None, "Retained: current model predicts held-out data better"
    return candidate, "Validated passive model; PI recommendation available"
