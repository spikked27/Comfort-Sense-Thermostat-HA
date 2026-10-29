"""Deterministic controls. Time in seconds, temperature in C, duty in [0, 1]."""
from dataclasses import dataclass, field
from collections import deque
import math


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def celsius(value, unit):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite temperature")
    if unit in ("°F", "F"):
        value = (value - 32) * 5 / 9
    elif unit in ("K", "kelvin"):
        value -= 273.15
    elif unit not in ("°C", "C"):
        raise ValueError("Temperature unit required")
    if not -60 <= value <= 70:
        raise ValueError("Implausible temperature")
    return value


def presence(state):
    """Home signal: binary, person/tracker or zone person count. Unknown != away."""
    if state in (None, "unknown", "unavailable"):
        return None
    if state in ("on", "home"):
        return True
    if state in ("off", "not_home"):
        return False
    try:
        value = float(state)
        return value > 0 if math.isfinite(value) else None
    except ValueError:
        return False  # person at a named zone


@dataclass
class Occupancy:
    score: float = 0.0
    history: object = None
    elapsed: float = 0.0

    def moving_average(self, occupied, dt, window=1800):
        """Time-weighted presence over a fixed window; startup history is empty.

        A fully occupied old room and newly occupied room cross at half a window.
        Repeated events within one tick never add sample-count bias.
        """
        if self.history is None:
            self.history = deque()
        dt = max(0, dt)
        self.elapsed += dt
        if dt:
            self.history.append((self.elapsed-dt, self.elapsed, float(bool(occupied))))
        cutoff = self.elapsed-window
        while self.history and self.history[0][1] <= cutoff:
            self.history.popleft()
        self.score = sum((end-max(start, cutoff))*value for start,end,value in self.history)/window
        return self.score

    def update(self, occupied, dt, rise=300, decay=1800):
        # Unavailable occupancy decays; never masquerades as confirmed home absence.
        target = 1.0 if occupied else 0.0
        tau = rise if target > self.score else decay
        self.score = target + (self.score - target) * math.exp(-max(0, dt) / tau)
        return self.score


def weights(scores, valid, average=False, selected="Auto", previous=None, margin=0.0, previous_members=()):
    if not valid:
        return {}
    if selected not in ("Auto", "Average"):
        return {selected: 1.0} if selected in valid else {}
    if average or selected == "Average" or sum(scores.get(r, 0) for r in valid) < 0.05:
        return {r: 1 / len(valid) for r in valid}
    maximum = max(scores.get(r, 0) for r in valid)
    if margin > 0:
        # Symmetric relative difference, matching the original room templates.
        members = [r for r in valid if scores.get(r,0)>0 and
                   2*(maximum-scores[r])/(maximum+scores[r]) <= margin+(0.02 if r in previous_members else 0)+1e-9]
        return {r:1/len(members) for r in members}
    # Keep the current room at a tie instead of oscillating between equal scores.
    winner = previous if previous in valid and scores.get(previous,0) >= maximum-1e-9 else max(valid,key=lambda r:scores.get(r,0))
    return {winner: 1.0}


@dataclass
class RoomGuard:
    hot: bool = False
    cold: bool = False

    def update(self, temperature, target, hot_buffer, cold_buffer, hysteresis=0.2):
        if temperature is None:
            self.hot = self.cold = False
            return
        upper, lower = target+hot_buffer, target-cold_buffer
        self.hot = hot_buffer>0 and (temperature>=upper or self.hot and temperature>upper-min(hysteresis,hot_buffer/2))
        self.cold = cold_buffer>0 and (temperature<lower or self.cold and temperature<lower+min(hysteresis,cold_buffer/2))


@dataclass
class GroupForecast:
    """Conservative arrival estimate: allow each selected room to reach the target."""
    rooms: list

    def time_to_target(self, temperature, target, outdoor):
        return max(model.time_to_target(measured,target,outdoor) for model,measured in self.rooms)

    def duty_to_target(self,temperature,target,outdoor,seconds):
        return max(model.duty_to_target(measured,target,outdoor,seconds) for model,measured in self.rooms)


@dataclass
class PID:
    kp: float = 0.2
    ki: float = 0.000035
    kd: float = 0.0
    integral: float = 0.0
    previous: float | None = None
    derivative: float = 0.0
    output: float = 0.0
    last_target: float | None = None
    terms: dict = field(default_factory=dict)

    def update(self, temperature, target, dt, feedforward=0.0, active=True,
               constrained=False):
        dt = clamp(dt, 0, 120)
        if self.previous is not None and dt > 0:
            slope = (temperature - self.previous) / dt
            alpha = 1 - math.exp(-dt / 600)
            self.derivative += alpha * (slope - self.derivative)
        self.previous = temperature
        if not active:
            self.integral = 0.0
            self.output = 0.0
            self.last_target = target
            self.terms={"active":False,"proportional":0.0,"integral":0.0,"derivative":0.0,
                        "feedforward":0.0,"unclamped":0.0,"output":0.0,"limit":"inactive"}
            return 0.0
        error = target - temperature
        base = feedforward + self.kp * error - self.kd * self.derivative
        if self.last_target is not None and self.last_target-target > 0.2:
            # Shed excess heat after a setback. Raising the same source's target
            # retains its maintenance compensation and produces a proportional response.
            self.integral = min(self.integral,0.0)
        raw = base + self.integral
        if not constrained and (0 < raw < 1 or raw >= 1 and error < 0 or raw <= 0 and error > 0):
            self.integral = clamp(self.integral + self.ki * error * dt, -0.5, 1)
        self.output = clamp(base + self.integral)
        self.last_target = target
        self.terms={"active":True,"proportional":self.kp*error,"integral":self.integral,
                    "derivative":-self.kd*self.derivative,"feedforward":feedforward,
                    "unclamped":base+self.integral,"output":self.output,
                    "limit":"actuator" if constrained else "high" if base+self.integral>=1 else "low" if base+self.integral<=0 else "none"}
        return self.output

    def tune(self, kp, ki, kd=0.0):
        """Hold the last output on gain changes; derivative remains on measurement."""
        if self.previous is not None and self.last_target is not None:
            self.integral += (self.kp - kp) * (self.last_target - self.previous)
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral = clamp(self.integral, -0.5, 1)


@dataclass
class Relay:
    """Fixed-window slow PWM with carried duty debt for sub-minimum pulses.

    A 5% demand can earn one 5-minute pulse over several 20-minute windows.
    Output decisions are based on observed relay state, never command success alone.
    """
    window: float = 1200
    min_on: float = 300
    min_off: float = 300
    credit: float = 0.0
    pulse_end: float = 0.0
    changed: float | None = None
    observed: bool | None = None
    start: float | None = None

    def observe(self, now, on):
        if self.observed is None or self.observed != on:
            self.changed = now
            self.observed = on

    def decide(self, now, duty, on, force_off=False):
        self.observe(now, on)
        if force_off:
            self.credit = 0.0
            self.pulse_end = now
            self.start = now
            return False
        if duty <= 0:
            self.credit = 0.0
            self.pulse_end = now
        if self.start is None:
            self.start = now - self.window
        if now - self.start >= self.window:
            self.start = now
            self.credit = min(self.credit + clamp(duty) * self.window, 2 * self.window)
            if self.credit >= self.min_on:
                length = min(self.credit, self.window)
                # Avoid an off interval shorter than min_off inside the window.
                if self.window - length < self.min_off:
                    length = self.window
                self.credit -= length
                self.pulse_end = now + length
        wanted = now < self.pulse_end and duty > 0
        if wanted != on and now - self.changed < (self.min_on if on else self.min_off):
            return on
        return wanted


def deadline_plan(now, deadline, duration, temperature, target, model=None,
                  outdoor=None, fallback_rate=0.5, maximum=14400):
    """Return preheat status and feasibility. Caller supplies timezone-aware epochs."""
    lead = (max(0, target - temperature) / fallback_rate) * 3600 + 1800
    confidence = "fallback"
    if model is not None and outdoor is not None:
        lead = model.time_to_target(temperature, target, outdoor)
        confidence = "learned"
    reachable = math.isfinite(lead) and lead <= maximum
    lead = min(maximum, lead * 1.15)  # conservative allowance; bounded energy budget
    active = deadline - lead <= now < deadline + duration
    return {"active": active, "lead_seconds": lead, "reachable": reachable,
            "confidence": confidence, "deadline": deadline}
