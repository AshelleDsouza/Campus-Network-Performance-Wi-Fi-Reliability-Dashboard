"""
Campus Network Performance & Wi-Fi Reliability Dashboard  (CHRIST University)

How this file is organised (read top to bottom):
  PART 1  Setup and loading the data
  PART 2  Sidebar filters (the user chooses dates, locations, limits)
  PART 3  Calculations (summary table, health score, KPIs)
  PART 4  The 7 tabs (each tab = one feature of the dashboard)
"""
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from generate_data import generate

# ======================================================================
# PART 1: SETUP AND LOADING DATA
# ======================================================================
st.set_page_config(page_title="Campus Network Dashboard", page_icon="📶", layout="wide")

DATA_FOLDER = Path(__file__).parent / "data"
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CHART_STYLE = "plotly_white"


@st.cache_data  # cache = read the files only once, not on every click
def load_data():
    """Read the two CSV files (or create them if they are missing)."""
    measurements_file = DATA_FOLDER / "network_measurements.csv"
    outage_file = DATA_FOLDER / "outage_log.csv"

    if measurements_file.exists() and outage_file.exists():
        measurements = pd.read_csv(measurements_file, parse_dates=["timestamp"])
        outages = pd.read_csv(outage_file, parse_dates=["start_time", "end_time"])
    else:
        measurements, outages = generate()

    # Extra columns that make grouping easy later
    measurements["date"] = measurements["timestamp"].dt.date
    measurements["hour"] = measurements["timestamp"].dt.hour
    measurements["weekday"] = measurements["timestamp"].dt.day_name()
    return measurements, outages


all_data, all_outages = load_data()

# ======================================================================
# PART 2: SIDEBAR FILTERS
# ======================================================================
st.sidebar.title("📶 Filters")

# Date range
first_day = all_data["date"].min()
last_day = all_data["date"].max()
default_start = max(first_day, last_day - timedelta(days=13))
chosen_dates = st.sidebar.date_input("Date range", (default_start, last_day),
                                     min_value=first_day, max_value=last_day)
if len(chosen_dates) != 2:
    st.info("Please pick both a start date and an end date in the sidebar.")
    st.stop()
start_date, end_date = chosen_dates

# Locations
location_list = sorted(all_data["location"].unique())
chosen_locations = st.sidebar.multiselect("Locations", location_list, default=location_list)
if len(chosen_locations) == 0:
    st.warning("Please select at least one location.")
    st.stop()

# Limits used for alerts (service-level thresholds)
st.sidebar.markdown("### Service limits")
min_download = st.sidebar.slider("Minimum download (Mbps)", 5, 100, 25)
max_latency = st.sidebar.slider("Maximum latency (ms)", 20, 200, 60)
max_loss = st.sidebar.slider("Maximum packet loss (%)", 0.5, 10.0, 2.0, step=0.5)

# Keep only the rows the user asked for
selected = (all_data["date"] >= start_date) & (all_data["date"] <= end_date) \
           & all_data["location"].isin(chosen_locations)
data = all_data[selected]
if data.empty:
    st.warning("No data for these filters.")
    st.stop()

# 'online' = only the moments when the network was working
online = data[data["is_online"]].copy()

# Outage events inside the chosen dates and locations
outages = all_outages[
    all_outages["location"].isin(chosen_locations)
    & (all_outages["start_time"].dt.date >= start_date)
    & (all_outages["start_time"].dt.date <= end_date)
]

# ======================================================================
# PART 3: CALCULATIONS
# ======================================================================


def get_kpis(df):
    """The 5 headline numbers for any slice of data."""
    working = df[df["is_online"]]
    return {
        "download": working["download_mbps"].mean(),
        "upload": working["upload_mbps"].mean(),
        "latency": working["latency_ms"].mean(),
        "loss": working["packet_loss_pct"].mean(),
        "uptime": df["is_online"].mean() * 100,
    }


def get_rating(score):
    """Turn a 0-100 health score into a word."""
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Fair"
    else:
        return "Poor"


# --- Summary table: one row per location ---
summary = online.groupby("location").agg(
    avg_download=("download_mbps", "mean"),
    avg_upload=("upload_mbps", "mean"),
    avg_latency=("latency_ms", "mean"),
    avg_loss=("packet_loss_pct", "mean"),
).reset_index()

uptime_per_location = data.groupby("location")["is_online"].mean() * 100
summary["uptime_pct"] = summary["location"].map(uptime_per_location)

# --- Health score (0-100) ---
# Each part is turned into a score between 0 and 1 (1 = best)
summary["speed_score"] = (summary["avg_download"] / 50).clip(0, 1)
summary["latency_score"] = (1 - (summary["avg_latency"] - 10) / 150).clip(0, 1)
summary["loss_score"] = (1 - summary["avg_loss"] / 5).clip(0, 1)
summary["uptime_score"] = ((summary["uptime_pct"] - 95) / 5).clip(0, 1)

# Weighted total: speed 30%, latency 20%, packet loss 20%, uptime 30%
summary["health_score"] = 100 * (0.30 * summary["speed_score"]
                                 + 0.20 * summary["latency_score"]
                                 + 0.20 * summary["loss_score"]
                                 + 0.30 * summary["uptime_score"])
summary["rating"] = summary["health_score"].apply(get_rating)

# ======================================================================
# HEADER AND KPI CARDS
# ======================================================================
st.title("📶 Campus Network Performance & Wi-Fi Reliability Dashboard")
st.caption("CHRIST University · Data shown here is simulated for demonstration.")

current = get_kpis(data)

# Previous period = the same number of days just before the chosen dates
days_selected = (end_date - start_date).days + 1
prev_start = start_date - timedelta(days=days_selected)
prev_end = start_date - timedelta(days=1)
prev_rows = all_data[(all_data["date"] >= prev_start) & (all_data["date"] <= prev_end)
                     & all_data["location"].isin(chosen_locations)]
previous = get_kpis(prev_rows) if len(prev_rows) > 0 else None


def change(name, decimals=1):
    """Difference between now and the previous period (None if no previous data)."""
    if previous is None or pd.isna(previous[name]) or pd.isna(current[name]):
        return None
    return round(current[name] - previous[name], decimals)


col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Avg download", f"{current['download']:.1f} Mbps", change("download"))
col2.metric("Avg upload", f"{current['upload']:.1f} Mbps", change("upload"))
col3.metric("Avg latency", f"{current['latency']:.1f} ms", change("latency"), delta_color="inverse")
col4.metric("Avg packet loss", f"{current['loss']:.2f} %", change("loss", 2), delta_color="inverse")
col5.metric("Uptime", f"{current['uptime']:.2f} %", change("uptime", 2))
st.caption(f"Small arrows compare with the previous {days_selected} day(s).")

# ======================================================================
# PART 4: THE TABS
# ======================================================================
tab_overview, tab_speed, tab_latency, tab_downtime, tab_compare, tab_peak, tab_trends = st.tabs(
    ["🏠 Overview", "⚡ Speed", "⏱ Latency & Loss", "🔌 Downtime",
     "📍 Compare", "🔥 Peak Usage", "📈 Trends"]
)

# ----------------------------------------------------------------------
# TAB 1: OVERVIEW  (health score, alerts, summary table)
# ----------------------------------------------------------------------
with tab_overview:
    left, right = st.columns([3, 2])

    with left:
        sorted_summary = summary.sort_values("health_score")
        fig = px.bar(sorted_summary, x="health_score", y="location", orientation="h",
                     color="health_score", color_continuous_scale="RdYlGn", range_color=(0, 100),
                     title="Network health score by location (0-100)", template=CHART_STYLE)
        fig.update_layout(coloraxis_showscale=False, yaxis_title=None, xaxis_title="Health score")
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("🚨 Alerts")
        alert_count = 0
        for _, row in summary.iterrows():
            if row["avg_download"] < min_download:
                st.warning(f"**{row['location']}**: download {row['avg_download']:.1f} Mbps is below {min_download}")
                alert_count += 1
            if row["avg_latency"] > max_latency:
                st.warning(f"**{row['location']}**: latency {row['avg_latency']:.1f} ms is above {max_latency}")
                alert_count += 1
            if row["avg_loss"] > max_loss:
                st.warning(f"**{row['location']}**: packet loss {row['avg_loss']:.2f}% is above {max_loss}")
                alert_count += 1
            if row["uptime_pct"] < 99:
                st.warning(f"**{row['location']}**: uptime {row['uptime_pct']:.2f}% is below 99%")
                alert_count += 1
        if alert_count == 0:
            st.success("All selected locations are within the limits.")

    st.subheader("Location summary")
    table = summary[["location", "health_score", "rating", "avg_download", "avg_upload",
                     "avg_latency", "avg_loss", "uptime_pct"]]
    table = table.sort_values("health_score", ascending=False)
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "location": "Location",
        "health_score": st.column_config.ProgressColumn("Health", min_value=0, max_value=100, format="%.0f"),
        "rating": "Rating",
        "avg_download": st.column_config.NumberColumn("Download (Mbps)", format="%.1f"),
        "avg_upload": st.column_config.NumberColumn("Upload (Mbps)", format="%.1f"),
        "avg_latency": st.column_config.NumberColumn("Latency (ms)", format="%.1f"),
        "avg_loss": st.column_config.NumberColumn("Loss (%)", format="%.2f"),
        "uptime_pct": st.column_config.NumberColumn("Uptime (%)", format="%.2f"),
    })

    with st.expander("How is the health score calculated?"):
        st.write("Health = 100 x (0.30 x Speed + 0.20 x Latency + 0.20 x Packet loss + 0.30 x Uptime)")
        st.write("Each part is first converted to a number between 0 (bad) and 1 (good). "
                 "Rating: 80+ Excellent, 60+ Good, 40+ Fair, below 40 Poor.")

# ----------------------------------------------------------------------
# TAB 2: SPEED  (download and upload)
# ----------------------------------------------------------------------
with tab_speed:
    choice = st.radio("Time interval", ["15 min", "Hourly", "Daily"], index=1, horizontal=True)
    interval = {"15 min": "15min", "Hourly": "1h", "Daily": "1D"}[choice]

    # 'period' = the timestamp rounded down to the chosen interval
    online["period"] = online["timestamp"].dt.floor(interval)

    # Chart 1: campus-wide average speed over time
    campus_speed = online.groupby("period")[["download_mbps", "upload_mbps"]].mean().reset_index()
    fig = px.line(campus_speed, x="period", y=["download_mbps", "upload_mbps"],
                  title="Campus-wide average speed", template=CHART_STYLE)
    fig.update_layout(yaxis_title="Mbps", xaxis_title=None, legend_title=None)
    st.plotly_chart(fig, width="stretch")

    left, right = st.columns(2)
    with left:
        # Chart 2: spread of download speeds per location
        fig = px.box(online, x="location", y="download_mbps", color="location",
                     title="Download speed spread", template=CHART_STYLE)
        fig.add_hline(y=min_download, line_dash="dash", line_color="red")
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Mbps")
        st.plotly_chart(fig, width="stretch")

    with right:
        # Chart 3: how often is the speed below the minimum?
        online["too_slow"] = online["download_mbps"] < min_download
        slow_share = online.groupby("location")["too_slow"].mean().reset_index()
        slow_share["too_slow"] = slow_share["too_slow"] * 100
        fig = px.bar(slow_share.sort_values("too_slow"), x="too_slow", y="location", orientation="h",
                     title=f"% of time below {min_download} Mbps", template=CHART_STYLE)
        fig.update_layout(yaxis_title=None, xaxis_title="% of measurements")
        st.plotly_chart(fig, width="stretch")

    # Chart 4: one line per location
    per_location = online.groupby(["location", "period"])["download_mbps"].mean().reset_index()
    fig = px.line(per_location, x="period", y="download_mbps", color="location",
                  title="Download speed by location", template=CHART_STYLE)
    fig.update_layout(yaxis_title="Mbps", xaxis_title=None)
    st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------
# TAB 3: LATENCY AND PACKET LOSS
# ----------------------------------------------------------------------
with tab_latency:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg latency", f"{online['latency_ms'].mean():.1f} ms")
    c2.metric("95th percentile latency", f"{online['latency_ms'].quantile(0.95):.1f} ms")
    c3.metric("Avg jitter", f"{online['jitter_ms'].mean():.2f} ms")
    bad = (online["latency_ms"] > max_latency) | (online["packet_loss_pct"] > max_loss)
    c4.metric("Measurements over the limits", f"{bad.mean() * 100:.1f} %")

    left, right = st.columns(2)
    with left:
        fig = px.box(online, x="location", y="latency_ms", color="location",
                     title="Latency spread", template=CHART_STYLE)
        fig.add_hline(y=max_latency, line_dash="dash", line_color="red")
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="ms")
        st.plotly_chart(fig, width="stretch")
    with right:
        avg_loss = online.groupby("location")["packet_loss_pct"].mean().reset_index()
        fig = px.bar(avg_loss.sort_values("packet_loss_pct"), x="packet_loss_pct", y="location",
                     orientation="h", title="Average packet loss", template=CHART_STYLE)
        fig.add_vline(x=max_loss, line_dash="dash", line_color="red")
        fig.update_layout(yaxis_title=None, xaxis_title="Packet loss (%)")
        st.plotly_chart(fig, width="stretch")

    # More users -> higher latency (congestion)
    sample = online.sample(min(3000, len(online)), random_state=1)
    fig = px.scatter(sample, x="connected_users", y="latency_ms", color="location", opacity=0.6,
                     title="Latency vs connected users (more users = more delay)", template=CHART_STYLE)
    fig.update_layout(xaxis_title="Connected users", yaxis_title="Latency (ms)")
    st.plotly_chart(fig, width="stretch")

    # Hourly trend of latency and loss
    online["hour_period"] = online["timestamp"].dt.floor("1h")
    hourly = online.groupby("hour_period")[["latency_ms", "packet_loss_pct"]].mean().reset_index()
    left, right = st.columns(2)
    with left:
        fig = px.line(hourly, x="hour_period", y="latency_ms", title="Hourly latency (ms)", template=CHART_STYLE)
        fig.update_layout(xaxis_title=None, yaxis_title="ms")
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = px.line(hourly, x="hour_period", y="packet_loss_pct", title="Hourly packet loss (%)",
                      template=CHART_STYLE)
        fig.update_layout(xaxis_title=None, yaxis_title="%")
        st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------
# TAB 4: DOWNTIME
# ----------------------------------------------------------------------
with tab_downtime:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Number of outages", len(outages))
    c2.metric("Total downtime", f"{int(outages['duration_min'].sum())} min")
    if len(outages) > 0:
        c3.metric("Average outage length", f"{outages['duration_min'].mean():.0f} min")
        c4.metric("Longest outage", f"{int(outages['duration_min'].max())} min")

    if len(outages) == 0:
        st.success("No outages in this selection.")
    else:
        left, right = st.columns(2)
        with left:
            by_location = outages.groupby("location")["duration_min"].sum().reset_index()
            fig = px.bar(by_location.sort_values("duration_min"), x="duration_min", y="location",
                         orientation="h", title="Total downtime by location (minutes)", template=CHART_STYLE)
            fig.update_layout(yaxis_title=None, xaxis_title="Minutes")
            st.plotly_chart(fig, width="stretch")
        with right:
            by_cause = outages.groupby("cause")["duration_min"].sum().reset_index()
            fig = px.pie(by_cause, names="cause", values="duration_min", hole=0.4,
                         title="Downtime by cause", template=CHART_STYLE)
            st.plotly_chart(fig, width="stretch")

        fig = px.timeline(outages, x_start="start_time", x_end="end_time", y="location", color="cause",
                          title="Outage timeline", template=CHART_STYLE)
        fig.update_yaxes(autorange="reversed", title=None)
        st.plotly_chart(fig, width="stretch")

    # Daily uptime %
    daily_uptime = (data.groupby("date")["is_online"].mean() * 100).reset_index()
    daily_uptime.columns = ["date", "uptime"]
    fig = px.line(daily_uptime, x="date", y="uptime", markers=True, title="Daily uptime (%)", template=CHART_STYLE)
    fig.add_hline(y=99.5, line_dash="dash", line_color="green")
    fig.update_layout(xaxis_title=None, yaxis_title="Uptime (%)")
    st.plotly_chart(fig, width="stretch")

    if len(outages) > 0:
        st.subheader("Outage log")
        st.dataframe(outages.sort_values("start_time", ascending=False), hide_index=True, width="stretch")

# ----------------------------------------------------------------------
# TAB 5: COMPARE LOCATIONS
# ----------------------------------------------------------------------
with tab_compare:
    metric_options = {
        "Health score": "health_score",
        "Download (Mbps)": "avg_download",
        "Upload (Mbps)": "avg_upload",
        "Latency (ms)": "avg_latency",
        "Packet loss (%)": "avg_loss",
        "Uptime (%)": "uptime_pct",
    }
    label = st.selectbox("Choose a metric", list(metric_options))
    column = metric_options[label]

    # For latency and loss a LOWER number is better
    lower_is_better = column in ["avg_latency", "avg_loss"]

    sorted_summary = summary.sort_values(column, ascending=lower_is_better)
    fig = px.bar(sorted_summary, x="location", y=column, color=column,
                 color_continuous_scale="RdYlGn_r" if lower_is_better else "RdYlGn",
                 title=f"{label} by location", template=CHART_STYLE)
    fig.update_layout(coloraxis_showscale=False, xaxis_title=None, yaxis_title=label)
    st.plotly_chart(fig, width="stretch")

    best = sorted_summary.iloc[0]["location"]
    worst = sorted_summary.iloc[-1]["location"]
    st.info(f"🏆 Best: **{best}**     ⚠️ Needs attention: **{worst}**")

    # Radar chart: compare the quality profile of a few locations
    picked = st.multiselect("Radar chart: pick up to 4 locations", summary["location"].tolist(),
                            default=summary["location"].tolist()[:2], max_selections=4)
    if len(picked) > 0:
        names = ["Speed", "Latency", "Packet loss", "Uptime"]
        fig = go.Figure()
        for loc in picked:
            r = summary[summary["location"] == loc].iloc[0]
            values = [r["speed_score"], r["latency_score"], r["loss_score"], r["uptime_score"]]
            # repeat the first value at the end to close the shape
            fig.add_trace(go.Scatterpolar(r=values + [values[0]], theta=names + [names[0]],
                                          fill="toself", name=loc))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1])), template=CHART_STYLE,
                          title="Quality profile (1 = best)")
        st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------
# TAB 6: PEAK USAGE
# ----------------------------------------------------------------------
with tab_peak:
    # Total users on campus at each moment
    campus_users = data.groupby("timestamp")["connected_users"].sum().reset_index()
    campus_users["hour"] = campus_users["timestamp"].dt.hour
    campus_users["weekday"] = campus_users["timestamp"].dt.day_name()

    users_by_hour = campus_users.groupby("hour")["connected_users"].mean()
    busiest = users_by_hour.sort_values(ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Busiest hour", f"{busiest.index[0]:02d}:00", f"{busiest.iloc[0]:.0f} users", delta_color="off")
    c2.metric("2nd busiest hour", f"{busiest.index[1]:02d}:00", f"{busiest.iloc[1]:.0f} users", delta_color="off")
    c3.metric("Quietest hour", f"{busiest.index[-1]:02d}:00", f"{busiest.iloc[-1]:.0f} users", delta_color="off")

    # Heatmap 1: weekday x hour
    grid = campus_users.pivot_table(index="weekday", columns="hour", values="connected_users", aggfunc="mean")
    grid = grid.reindex(DAY_ORDER).dropna(how="all")
    fig = px.imshow(grid, aspect="auto", color_continuous_scale="YlOrRd",
                    labels=dict(x="Hour of day", y="", color="Users"),
                    title="Peak usage: average users by weekday and hour", template=CHART_STYLE)
    st.plotly_chart(fig, width="stretch")

    # Heatmap 2: location x hour
    grid2 = data.pivot_table(index="location", columns="hour", values="connected_users", aggfunc="mean")
    fig = px.imshow(grid2, aspect="auto", color_continuous_scale="Blues",
                    labels=dict(x="Hour of day", y="", color="Avg users"),
                    title="When is each location busiest?", template=CHART_STYLE)
    st.plotly_chart(fig, width="stretch")

    # Load vs speed, side by side
    per_hour = online.groupby("hour")[["connected_users", "download_mbps"]].mean().reset_index()
    left, right = st.columns(2)
    with left:
        fig = px.bar(per_hour, x="hour", y="connected_users", title="Average users per hour", template=CHART_STYLE)
        fig.update_layout(xaxis_title="Hour of day", yaxis_title="Users")
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = px.line(per_hour, x="hour", y="download_mbps", title="Average download per hour (dips when busy)",
                      template=CHART_STYLE)
        fig.update_layout(xaxis_title="Hour of day", yaxis_title="Mbps")
        st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------
# TAB 7: TRENDS
# ----------------------------------------------------------------------
with tab_trends:
    trend_options = {
        "Download (Mbps)": "download_mbps",
        "Upload (Mbps)": "upload_mbps",
        "Latency (ms)": "latency_ms",
        "Packet loss (%)": "packet_loss_pct",
        "Connected users": "connected_users",
    }
    c1, c2 = st.columns([2, 1])
    trend_label = c1.selectbox("Metric", list(trend_options), key="trend_metric")
    window = c2.slider("Smoothing (days)", 1, 7, 3)
    column = trend_options[trend_label]

    # Daily average for every location
    daily = online.groupby(["location", "date"])[column].mean().reset_index()
    daily["date"] = pd.to_datetime(daily["date"])

    # Smooth each location with a rolling average, one location at a time
    parts = []
    trend_rows = []
    for loc in daily["location"].unique():
        part = daily[daily["location"] == loc].sort_values("date").copy()
        part["smoothed"] = part[column].rolling(window, min_periods=1).mean()
        parts.append(part)

        # Trend direction: slope of a straight line through the daily values
        if len(part) >= 3:
            slope_per_day = np.polyfit(range(len(part)), part[column], 1)[0]
            slope_per_week = slope_per_day * 7
            if column == "connected_users":
                verdict = "Rising" if slope_per_week > 0 else "Falling"
            elif column in ["latency_ms", "packet_loss_pct"]:
                verdict = "Improving" if slope_per_week < 0 else "Degrading"   # lower is better
            else:
                verdict = "Improving" if slope_per_week > 0 else "Degrading"   # higher is better
            trend_rows.append({"Location": loc, "Change per week": round(slope_per_week, 2), "Trend": verdict})

    smooth_data = pd.concat(parts)
    fig = px.line(smooth_data, x="date", y="smoothed", color="location",
                  title=f"Daily {trend_label} ({window}-day rolling average)", template=CHART_STYLE)
    fig.update_layout(xaxis_title=None, yaxis_title=trend_label)
    st.plotly_chart(fig, width="stretch")

    if len(trend_rows) > 0:
        st.subheader("Trend direction")
        st.dataframe(pd.DataFrame(trend_rows), hide_index=True, width="stretch")

st.divider()
st.caption("Built with Streamlit · Pandas · NumPy · Plotly")
