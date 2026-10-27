"""Native HA weekly schedule blocks and compatibility migration, without HA I/O."""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
import math

from .units import native_temperature

DAYS=("monday","tuesday","wednesday","thursday","friday","saturday","sunday")


def migrate_config(config):
    """Move old room morning fields into independent legacy schedule bindings."""
    result=deepcopy(config)
    if "room_buffer" not in result:
        old=[float(r.get(k,2.0)) for r in result.get("rooms",[]) for k in ("hot_buffer","cold_buffer")]
        result["room_buffer"]=min(old,default=2.0)
    schedules=result.setdefault("schedules",[])
    for room in result.get("rooms",[]):
        room.pop("hot_buffer",None)
        room.pop("cold_buffer",None)
        if room.get("morning_enabled"):
            weekly={day:[] for day in DAYS}
            hour,minute=map(int,room.get("morning_time","07:00").split(":"))
            start=hour*60+minute
            end=start+int(room.get("morning_duration",60))
            for day in room.get("morning_days",[0,1,2,3,4]):
                weekly[DAYS[day]].append({"from":f"{hour:02}:{minute:02}",
                    "to":"24:00" if end>=1440 else f"{end//60:02}:{end%60:02}"})
                if end>1440:
                    weekly[DAYS[(day+1)%7]].append({"from":"00:00","to":f"{(end-1440)//60:02}:{end%60:02}"})
            sid=f"legacy_{room['id']}"
            if not any(s["id"]==sid for s in schedules):
                schedules.append({"id":sid,"name":f"Morning – {room['name']}",
                    "entity_id":"","weekly":weekly,"source":room["id"],
                    "target":room.get("morning_target",room["target"]),
                    "data_temperature_unit":"°C","preheat":True,"priority":0})
        for key in list(room):
            if key.startswith("morning_"):
                del room[key]
    return result


@dataclass(frozen=True)
class Window:
    binding_id: str
    entity_id: str
    name: str
    source: str
    target: float
    start: float
    end: float
    preheat: bool
    priority: int


def wall_time(date, value, zone):
    """Match schedule's 24:00 representation and local DST wall-time behavior."""
    if isinstance(value,time):
        if value==time.max:
            date+=timedelta(days=1)
            value=time(0)
    else:
        parts=str(value).split(":")
        hour,minute=int(parts[0]),int(parts[1])
        second=int(parts[2]) if len(parts)>2 else 0
        if hour==24 and minute==second==0:
            date+=timedelta(days=1)
            hour=0
        value=time(hour,minute,second)
    local=datetime.combine(date,value,tzinfo=zone).replace(fold=0)
    return local.astimezone(timezone.utc).astimezone(zone).timestamp()


def windows(binding, weekly, now_local, rooms, safety_limit):
    result=[]
    room_names={r["name"]:r["id"] for r in rooms}
    sources={"Auto","Average",*(r["id"] for r in rooms)}
    for offset in range(-1,8):
        date=now_local.date()+timedelta(days=offset)
        for block in weekly.get(DAYS[date.weekday()],[]):
            data=block.get("data") or {}
            source=data.get("source",binding["source"])
            source=room_names.get(source,source)
            target=(native_temperature(data["temperature"],data.get("temperature_unit",binding["data_temperature_unit"]))
                    if "temperature" in data else binding["target"])
            if source not in sources or not math.isfinite(target) or not 5<=target<safety_limit:
                raise ValueError("Invalid schedule source or target")
            start=wall_time(date,block["from"],now_local.tzinfo)
            end=wall_time(date,block["to"],now_local.tzinfo)
            if end<=start:
                raise ValueError("Invalid schedule block")
            result.append(Window(binding["id"],binding["entity_id"],binding["name"],source,target,
                                 start,end,binding["preheat"],int(binding["priority"])))
    merged=[]
    for window in sorted(result,key=lambda w:w.start):
        if merged and merged[-1].end==window.start and all(
            getattr(merged[-1],key)==getattr(window,key) for key in ("binding_id","source","target","preheat","priority")):
            merged[-1]=replace(merged[-1],end=window.end)
        else:
            merged.append(window)
    return merged


def choose(plans):
    """Highest priority wins; equal-priority room plans can share one heat demand."""
    active=[p for p in plans if p["active"]]
    if not active:
        return []
    by_binding={}
    for plan in sorted(active,key=lambda p:p["start"]):
        by_binding[plan["binding_id"]]=plan
    active=list(by_binding.values())
    priority=max(p["priority"] for p in active)
    active=[p for p in active if p["priority"]==priority]
    if all(p["source"] not in ("Auto","Average") for p in active):
        chosen={}
        for plan in sorted(active,key=lambda p:(p["start"],p["binding_id"])):
            chosen[plan["source"]]=plan
        return list(chosen.values())
    # Mixed Auto/Average/room sources have an explicit stable winner.
    return [max(active,key=lambda p:(p["phase"]=="active",p["start"],p["binding_id"]))]
