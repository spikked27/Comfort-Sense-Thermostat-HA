"""On-demand PID diagnostics without adding controls or recording every PID term."""
from copy import deepcopy
from .const import DOMAIN, AVERAGE


async def async_get_config_entry_diagnostics(hass,entry):
    runtime=hass.data[DOMAIN][entry.entry_id]
    aliases={room["id"]:f"room_{i+1}" for i,room in enumerate(runtime.rooms)}
    aliases.update({AVERAGE:"average","_group":"occupancy_group"})
    control=deepcopy(runtime.control_diagnostics())
    control["controller"]=aliases.get(control["controller"],control["controller"])
    control["members"]=[aliases[rid] for rid in control["members"]]
    for prefix,flag in (("Warm room protection:","hot"),("Cold room protection:","cold")):
        if control["limiting_condition"].startswith(prefix):
            control["limiting_condition"]=prefix+" "+", ".join(aliases[rid] for rid,row in runtime.guard_data.items() if row[flag])
    return {"control":control,
        "temperatures":{"unit":"°C","current":runtime.current_temperature,
                        "target":runtime.target_temperature,"outdoor":runtime.outdoor},
        "controllers":{aliases[rid]:{"terms":dict(pid.terms),"stored_integral":pid.integral,
                                     "gains":{k:getattr(pid,k) for k in ("kp","ki","kd")}}
                       for rid,pid in [*runtime.pids.items(),("_group",runtime.group_pid)]},
        "learning":{aliases[rid]:status for rid,status in runtime.learning_status.items()},
        "timing":{k:runtime.config[k] for k in ("min_on_seconds","min_off_seconds","pwm_seconds")},
        "restart_memory":{"maximum_age_seconds":900,"maximum_absolute_integral":0.5}}
