"""Bounded PID bias recovery; never restore derivative history or relay pulses."""
import math

MAX_AGE=15*60
MAX_BIAS=0.5


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def recovered_bias(saved,current):
    """Return a bias only for a brief restart with matching, fresh control context."""
    if not isinstance(saved,dict):
        return None,"No saved compensation"
    try:
        age=current["time"]-saved["time"]
        if not finite(age) or not 0<=age<=MAX_AGE:
            return None,"Saved compensation expired"
        if not current["fresh"] or not saved.get("fresh",False):
            return None,"Inputs are stale"
        for key in ("controller","members","source","preset","signature"):
            if saved[key]!=current[key]:
                return None,"Control source or equipment changed"
        old,new=saved["gains"],current["gains"]
        if len(old)!=3 or len(new)!=3 or any(not finite(a) or not finite(b) or not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12) for a,b in zip(old,new)):
            return None,"PID gains changed"
        for key,tolerance in (("target",0.2),("temperature",1.0)):
            if not finite(saved[key]) or not finite(current[key]) or abs(saved[key]-current[key])>tolerance:
                return None,"Target or room temperature changed"
        a,b=saved["outdoor"],current["outdoor"]
        if a is not None or b is not None:
            if not finite(a) or not finite(b) or abs(a-b)>3:
                return None,"Outdoor conditions changed"
        bias=saved["integral"]
        if not finite(bias) or not -MAX_BIAS<=bias<=MAX_BIAS:
            return None,"Invalid saved compensation"
        return bias,"Restored short-restart compensation"
    except (KeyError,TypeError,ValueError,OverflowError):
        return None,"Invalid saved compensation"
