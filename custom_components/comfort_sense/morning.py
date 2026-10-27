"""Phone-alarm deadlines; no HA I/O or equipment commands."""
from datetime import datetime
import math

from .scheduling import Window


def alarm_timestamp(value):
    """Accept timezone-aware ISO timestamps, never local/ambiguous wall times."""
    try:
        stamp=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (ValueError,TypeError,OverflowError,OSError):
        return None


class MorningAlarms:
    def __init__(self):
        self.events={}
        self.completed_days=set()
        self.status="Disabled"

    def restore(self,data,now):
        self.completed_days={str(d) for d in data.get("completed_days",[]) if isinstance(d,str)}
        for eid,event in data.get("events",{}).items():
            try:
                start=float(event["start"])
                if math.isfinite(start) and now-14400<start<=now+86400:
                    self.events[eid]={"start":start}
            except (ValueError,TypeError,KeyError):
                continue

    def saved(self):
        return {"events":self.events,"completed_days":sorted(self.completed_days)[-3:]}

    def window(self,config,states,now,zone):
        """Earliest home owner's alarm; latch a fired event through its hold.

        Before firing, cancellation/unavailability removes a plan. After firing,
        the phone advancing/clearing its next alarm must not erase today's hold.
        At most one morning session runs per local day.
        """
        if not config["morning_enabled"]:
            self.events={}
            self.status="Disabled"
            return None
        duration=config["morning_duration"]*60
        candidates={}
        for eid in config["alarm_sensors"]:
            owner=config["alarm_owners"].get(eid)
            if owner:
                person=states.get(owner)
                if not person or person.state!="home":
                    continue
            old=self.events.get(eid)
            start=old["start"] if old else None
            if start is not None and now>=start:
                day=datetime.fromtimestamp(start,zone).date().isoformat()
                if now<start+duration:
                    candidates[eid]={"start":start}
                    continue
                self.completed_days.add(day)
            state=states.get(eid)
            stamp=alarm_timestamp(state.state) if state else None
            if stamp is None or not now-duration<stamp<=now+86400:
                continue
            day=datetime.fromtimestamp(stamp,zone).date().isoformat()
            if day not in self.completed_days:
                candidates[eid]={"start":stamp}
        candidates={e:v for e,v in candidates.items()
                    if datetime.fromtimestamp(v["start"],zone).date().isoformat() not in self.completed_days}
        self.events=candidates
        # Once one alarm has fired, other phones must not extend its hold.
        fired=[(e,v) for e,v in candidates.items() if v["start"]<=now]
        available=fired or list(candidates.items())
        if not available:
            self.status="Waiting for a valid alarm from someone home"
            return None
        eid,event=min(available,key=lambda item:(item[1]["start"],item[0]))
        start=event["start"]
        self.status="Morning comfort" if start<=now else "Alarm connected"
        return Window("morning_alarm",eid,"Morning comfort",config["morning_source"],
                      config["morning_target"],start,start+duration,True,10)


class ArrivalLearning:
    """Small bounded corrections to model lead time from uninterrupted arrivals."""
    def __init__(self):
        self.corrections={}
        self.sessions={}
        self.last_arrival={}

    def restore(self,data):
        self.corrections={k:float(v) for k,v in data.items()
                          if isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=1800}

    def observe(self,plans,selected,now,temperature,eligible,rate):
        selected_ids={(p["binding_id"],p["start"]) for p in selected}
        # Overlapping room deadlines have different measurements; don't mix their feedback.
        eligible=eligible and len(selected)==1
        for plan in plans:
            key=(plan["binding_id"],plan["start"])
            if now<plan["start"] and plan["active"]:
                session=self.sessions.setdefault(key,{"last":now,"valid":eligible,"ready":None})
                session["valid"] &= eligible and key in selected_ids and now-session["last"]<=90
                session["last"]=now
                if temperature is not None and temperature>=plan["target"] and session["ready"] is None:
                    session["ready"]=now
            elif now>=plan["start"] and key in self.sessions:
                session=self.sessions.pop(key)
                if not session["valid"] or not eligible or key not in selected_ids or now-session["last"]>90 or temperature is None:
                    continue
                source=plan["source"]
                error=plan["target"]-temperature
                timing=(error/max(0.1,rate)*3600 if error>0 else
                        (session["ready"]-plan["start"] if session["ready"] is not None else 0))
                adjustment=max(-300,min(300,timing*0.2))
                self.corrections[source]=max(-1800,min(1800,self.corrections.get(source,0)+adjustment))
                self.last_arrival={"deadline":plan["start"],"source":source,"target":plan["target"],
                                   "temperature":temperature,"error":error,"lead_correction_seconds":self.corrections[source]}
        self.sessions={k:v for k,v in self.sessions.items() if now-k[1]<300 and k in selected_ids}
