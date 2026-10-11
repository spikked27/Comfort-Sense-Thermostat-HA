"""Read private hourly archive; describe warming episodes without inventing heater labels.

Usage: python scripts/analyze_temperature_archive.py ARCHIVE --output PRIVATE_REPORT
Never commit household archives or this script's output to a public repository.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics


def percentile(values, proportion):
    ordered = sorted(values)
    return ordered[round((len(ordered)-1)*proportion)] if ordered else None


def summarize(rows, start, end):
    selected = [r for r in rows if start <= r["start"]/1000 < end]
    slopes = [(z["mean"]-a["mean"])*5/9 for a,z in zip(selected,selected[1:])
              if z["start"]-a["start"] == 3600000]
    episodes, current = [], []
    for a,z in zip(selected,selected[1:]):
        slope = (z["mean"]-a["mean"])*5/9
        if z["start"]-a["start"] == 3600000 and slope >=0.1:
            current.append(slope)
        else:
            if len(current)>=2: episodes.append(current)
            current=[]
    if len(current)>=2: episodes.append(current)
    rates=[statistics.mean(e) for e in episodes]
    return {"hourly_records":len(selected), "missing_hour_slots":round((end-start)/3600)-len(selected),
        "mean_temperature_c":statistics.mean(r["mean"] for r in selected)*5/9-32*5/9 if selected else None,
        "warming_episodes_at_least_2h":len(episodes),
        "episode_rate_c_per_hour_p10":percentile(rates,0.1),
        "episode_rate_c_per_hour_median":percentile(rates,0.5),
        "episode_rate_c_per_hour_p90":percentile(rates,0.9),
        "median_warming_duration_hours":statistics.median(map(len,episodes)) if episodes else None,
        "hourly_change_c_p10":percentile(slopes,0.1), "hourly_change_c_p90":percentile(slopes,0.9)}


def epoch(text): return datetime.fromisoformat(text).timestamp()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("archive",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    source=json.loads(args.archive.read_text(encoding="utf-8"))
    if source["unit"] != "°F": raise ValueError("This archive adapter expects Fahrenheit")
    windows={"current_home_2026_spring":("2026-03-20T00:00:00-04:00","2026-05-01T00:00:00-04:00"),
             "apartment_2025_spring":("2025-03-20T00:00:00-04:00","2025-05-01T00:00:00-04:00"),
             "apartment_2024_spring":("2024-03-20T00:00:00-04:00","2024-05-01T00:00:00-04:00")}
    result={"created":datetime.now(timezone.utc).isoformat(), "source":"Hourly room temperature statistics",
        "causal_heating_model":False, "heater_state_available":False,
        "warning":"Temperature rises are unlabelled: heating, sun, people and sensor changes can all contribute. No PID gains can be identified from this archive alone.",
        "windows":{name:summarize(source["rows"],epoch(a),epoch(b)) for name,(a,b) in windows.items()}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result["windows"],indent=2))


if __name__=="__main__":main()
