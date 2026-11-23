"""
generate_data.py - creates the DUMMY (simulated) campus network dataset.

Idea: for every location, every 15 minutes, we decide
  1. how busy the location is (users)      -> depends on the hour of the day
  2. how good the network is               -> gets worse when more users are connected
  3. whether there was an outage           -> random events

Run:  python generate_data.py
Creates: data/network_measurements.csv and data/outage_log.csv
"""
import random
from datetime import timedelta
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# STEP 1: Locations and their normal (empty-network) quality
#   kind, download Mbps, upload Mbps, latency ms, max users
# ----------------------------------------------------------------------
LOCATIONS = {
    "Main Academic Block": ("academic", 180, 90, 12, 900),
    "Library": ("library", 150, 75, 14, 500),
    "Computer Lab Block": ("academic", 250, 125, 9, 400),
    "Hostel A": ("hostel", 100, 40, 22, 600),
    "Hostel B": ("hostel", 80, 30, 26, 600),
    "Cafeteria": ("cafeteria", 90, 35, 20, 450),
    "Auditorium": ("auditorium", 120, 50, 16, 700),
    "Sports Complex": ("sports", 60, 25, 30, 250),
    "Admin Block": ("admin", 200, 100, 10, 150),
}

OUTAGE_CAUSES = ["Power failure", "Access point fault", "Uplink / ISP outage",
                 "Switch reboot", "Scheduled maintenance", "Cable fault"]


# ----------------------------------------------------------------------
# STEP 2: How busy is a location? (0 = empty, 1 = completely full)
# ----------------------------------------------------------------------
def busy_level(kind, hour, is_weekend, event_on):
    if kind == "academic":
        if is_weekend:
            return 0.05
        if 9 <= hour < 13:
            return 0.85          # morning classes
        if 13 <= hour < 17:
            return 0.75          # afternoon classes
        if hour in (8, 17):
            return 0.35
        return 0.05

    if kind == "library":
        if is_weekend:
            return 0.4 if 10 <= hour < 17 else 0.05
        return 0.7 if 9 <= hour < 19 else 0.05

    if kind == "hostel":
        if 19 <= hour <= 23:
            return 0.95          # students online at night
        if hour < 2:
            return 0.6
        if 7 <= hour < 9:
            return 0.5
        return 0.25

    if kind == "cafeteria":
        level = 0.05
        if 12 <= hour < 14:
            level = 0.9          # lunch rush
        elif 8 <= hour < 9 or 16 <= hour < 17:
            level = 0.55
        return level / 2 if is_weekend else level

    if kind == "auditorium":
        return 0.95 if event_on else 0.05

    if kind == "sports":
        if 6 <= hour < 8:
            return 0.6
        if 16 <= hour < 19:
            return 0.85
        return 0.05

    # admin block
    if not is_weekend and 9 <= hour < 17:
        return 0.7
    return 0.03


# ----------------------------------------------------------------------
# STEP 3: Build the whole dataset
# ----------------------------------------------------------------------
def generate(days=30, seed=42):
    random.seed(seed)

    # All 15-minute time slots for the last `days` days
    end = pd.Timestamp.now().floor("15min")
    times = pd.date_range(end=end, periods=days * 96, freq="15min")
    all_dates = sorted(set(t.date() for t in times))

    # Auditorium events: about 1 in 5 days, a 3-hour event starting 9-15h
    event_start = {}
    for d in all_dates:
        if random.random() < 0.2:
            event_start[d] = random.randint(9, 15)

    rows = []
    outage_rows = []

    for name, (kind, base_down, base_up, base_lat, capacity) in LOCATIONS.items():

        # --- random outages for this location (about one every 5 days) ---
        outages = []
        for _ in range(random.randint(days // 8, days // 4)):
            start = random.choice(times[:-8])
            minutes = random.choice([15, 15, 30, 30, 45, 60, 90, 120])
            stop = start + timedelta(minutes=minutes)
            cause = random.choice(OUTAGE_CAUSES)
            outages.append((start, stop))
            outage_rows.append({"location": name, "start_time": start, "end_time": stop,
                                "duration_min": minutes, "cause": cause})

        # --- random "slow periods" (interference / congestion), 1 to 2 hours ---
        slow_periods = []
        for _ in range(random.randint(2, 5)):
            start = random.choice(times[:-8])
            slow_periods.append((start, start + timedelta(minutes=random.choice([60, 90, 120]))))

        # --- one row for every 15-minute slot ---
        for t in times:
            hour = t.hour
            is_weekend = t.dayofweek >= 5
            d = t.date()
            event_on = d in event_start and event_start[d] <= hour < event_start[d] + 3

            # users connected right now
            level = busy_level(kind, hour, is_weekend, event_on)
            users = int(capacity * level * random.uniform(0.85, 1.15))
            load = min(users / capacity, 1.0)          # 0 to 1

            # network quality: more load = slower, higher latency, more loss
            download = base_down * (1 - 0.6 * load) * random.uniform(0.9, 1.1)
            upload = base_up * (1 - 0.5 * load) * random.uniform(0.9, 1.1)
            latency = base_lat * (1 + 2 * load * load) * random.uniform(0.9, 1.1)
            loss = 0.1 + 2.5 * load ** 3 + random.uniform(0, 0.2)
            signal = -55 - 15 * load + random.uniform(-3, 3)

            # slow period -> everything gets worse
            for s, e in slow_periods:
                if s <= t < e:
                    download *= 0.4
                    upload *= 0.45
                    latency *= 3
                    loss += random.uniform(1, 5)

            jitter = latency * 0.12
            online = True

            # outage -> no connection at all
            for s, e in outages:
                if s <= t < e:
                    online = False
                    download = upload = 0
                    users = 0
                    latency = jitter = signal = None
                    loss = 100

            rows.append({
                "timestamp": t,
                "location": name,
                "building_type": kind,
                "download_mbps": round(download, 2),
                "upload_mbps": round(upload, 2),
                "latency_ms": None if latency is None else round(latency, 2),
                "jitter_ms": None if jitter is None else round(jitter, 2),
                "packet_loss_pct": round(loss, 2),
                "connected_users": users,
                "wifi_signal_dbm": None if signal is None else round(signal, 2),
                "is_online": online,
            })

    measurements = pd.DataFrame(rows).sort_values(["timestamp", "location"]).reset_index(drop=True)
    outage_log = pd.DataFrame(outage_rows).sort_values("start_time").reset_index(drop=True)
    outage_log.insert(0, "outage_id", ["OUT-%04d" % (i + 1) for i in range(len(outage_log))])
    return measurements, outage_log


if __name__ == "__main__":
    folder = Path(__file__).parent / "data"
    folder.mkdir(exist_ok=True)
    measurements, outage_log = generate()
    measurements.to_csv(folder / "network_measurements.csv", index=False)
    outage_log.to_csv(folder / "outage_log.csv", index=False)
    print("network_measurements.csv:", len(measurements), "rows")
    print("outage_log.csv:", len(outage_log), "rows")
