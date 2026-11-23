# 📶 Campus Network Performance & Wi-Fi Reliability Dashboard

A smart Streamlit dashboard for the CHRIST University environment that analyses internet speed, latency, packet loss, downtime and usage across campus locations.

**Libraries:** Streamlit · Pandas · NumPy · Plotly

## Features

| Requirement | Where in the app |
|---|---|
| Monitor download / upload speeds | ⚡ Speed tab |
| Latency and packet loss analysis | ⏱ Latency & Loss tab |
| Track connectivity downtime | 🔌 Downtime tab (outage log, timeline, root causes, MTTR) |
| Compare locations | 📍 Compare tab (ranking, radar chart) + Overview health score |
| Peak usage periods | 🔥 Peak Usage tab (weekday × hour heatmap) |
| Performance trends | 📈 Trends tab (rolling averages, improving/degrading verdict) |

Extras: adjustable sidebar filters, threshold-based alerts, composite 0-100 health score, period-over-period KPI deltas.

## Dataset (simulated)

`generate_data.py` creates 30 days of data, 9 locations, every 15 minutes (25,920 rows).

- `data/network_measurements.csv`: timestamp, location, building_type, download_mbps, upload_mbps, latency_ms, jitter_ms, packet_loss_pct, connected_users, wifi_signal_dbm, is_online
- `data/outage_log.csv`: outage_id, location, start_time, end_time, duration_min, cause

Realism built in: usage curves per building type (hostels peak at night, academic blocks at 11:00 and 14:30, cafeteria at lunch), speed falling and latency rising with load, random degradation incidents, and Poisson-distributed outages. To use real data, keep the same column names and replace the CSVs.

Regenerate anytime: `python generate_data.py`

## Run locally

```bash
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

