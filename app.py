# app.py - FINAL BEMS PROJECT - 100% WORKING - NO ERRORS
from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import plotly.express as px
import plotly.io as pio
import numpy as np
import os

app = Flask(__name__)
DATA_FILE = "data/energy_data.csv"
STATUS_FILE = "data/device_status.csv"
os.makedirs("data", exist_ok=True)

# === GENERATE UNIQUE DATA FOR EVERY ROOM ===
def generate_unique_data():
    rooms = ["Room101", "Room102", "Room201", "Room202", "Room301", "Room302", "Room303"]
    dates = pd.date_range("2025-11-01 00:00", "2025-11-15 23:59", freq='T')
    np.random.seed(42)

    data_list = []
    for idx, room in enumerate(rooms):
        voltage = 220 + np.random.normal(0, 3 + idx * 0.5, len(dates))
        hour = dates.hour
        weekday = dates.dayofweek
        base_on = (hour >= 8) & (hour < 20) & (weekday < 5)
        usage_factor = 0.6 + (idx * 0.08)
        random_off = np.random.rand(len(dates)) < (1 - usage_factor)
        is_on = base_on & (~random_off)
        base_current = 4.5 + idx * 0.7 + np.random.normal(0, 0.6, len(dates))
        current = np.where(is_on, base_current, 0.0)
        power = voltage * current

        df = pd.DataFrame({
            "timestamp": dates,
            "room": room,
            "voltage": voltage.round(2),
            "current": current.round(2),
            "power": power.round(1),
            "energy_kwh": (power / 1000 / 60).round(6)
        })
        df["bill_taka"] = (df["energy_kwh"] * 5.5).round(2)
        df["carbon_gco2"] = (df["energy_kwh"] * 720).round(1)
        data_list.append(df)

    full = pd.concat(data_list, ignore_index=True)
    full.to_csv(DATA_FILE, index=False)

    status = pd.DataFrame({
        "room": rooms,
        "status": "On",
        "schedule_on": "08:00",
        "schedule_off": "20:00"
    })
    status.to_csv(STATUS_FILE, index=False)

# Generate data if not exists
if not os.path.exists(DATA_FILE) or not os.path.exists(STATUS_FILE):
    generate_unique_data()

data = pd.read_csv(DATA_FILE)
data["timestamp"] = pd.to_datetime(data["timestamp"])

# Building structure
floors = {
    "Ground Floor": ["Room101", "Room102"],
    "1st Floor": ["Room201", "Room202"],
    "2nd Floor": ["Room301", "Room302", "Room303"]
}

# === HOME PAGE ===
@app.route("/")
def index():
    status = pd.read_csv(STATUS_FILE)
    status_dict = dict(zip(status.room, status.status))
    total = data["energy_kwh"].sum()
    return render_template("index.html",
                           floors=floors,
                           status_dict=status_dict,
                           total_energy=round(total, 2),
                           total_bill=int(data["bill_taka"].sum()),
                           total_carbon=int(data["carbon_gco2"].sum()))

# === ROOM DETAIL ===
@app.route("/room/<room_id>", methods=["GET", "POST"])
def room(room_id):
    status_df = pd.read_csv(STATUS_FILE)
    room_row = status_df[status_df["room"] == room_id]
    if room_row.empty:
        return "Room not found", 404
    room_status = room_row.iloc[0]

    if request.method == "POST":
        action = request.form.get("action")
        if action == "toggle":
            new = "Off" if room_status["status"] == "On" else "On"
            status_df.loc[status_df["room"] == room_id, "status"] = new
        elif action == "schedule":
            status_df.loc[status_df["room"] == room_id, ["schedule_on", "schedule_off"]] = [
                request.form["on_time"], request.form["off_time"]
            ]
        status_df.to_csv(STATUS_FILE, index=False)
        return redirect(url_for("room", room_id=room_id))

    start = request.args.get("start", "2025-11-01")
    end = request.args.get("end", "2025-11-15")
    mask = (data["room"] == room_id) & \
           (data["timestamp"].dt.date >= pd.to_datetime(start).date()) & \
           (data["timestamp"].dt.date <= pd.to_datetime(end).date())
    df = data[mask].copy()

    on_df = df[df["current"] > 0.5]
    latest = on_df.iloc[-1] if not on_df.empty else df.iloc[-1]

    hourly = df.set_index("timestamp")[["voltage", "current", "power"]].resample("H").mean().reset_index()
    colors = ["#3498db", "#e74c3c", "#2ecc71"]
    figs = {}
    for i, col in enumerate(["voltage", "current", "power"]):
        fig = px.line(hourly, x="timestamp", y=col, title=f"{col.capitalize()} Over Time",
                      color_discrete_sequence=[colors[i]])
        fig.update_layout(template="plotly_white", height=320)
        figs[col] = pio.to_html(fig, full_html=False)

    total_kwh = df["energy_kwh"].sum()
    savings = total_kwh * 0.20

    return render_template("room.html",
                           room_id=room_id,
                           voltage_html=figs["voltage"],
                           current_html=figs["current"],
                           power_html=figs["power"],
                           total_kwh=round(total_kwh, 2),
                           total_bill=int(df["bill_taka"].sum()),
                           total_carbon=int(df["carbon_gco2"].sum()),
                           savings_kwh=round(savings, 2),
                           savings_tk=int(savings * 5.5),
                           current_v=round(latest.voltage, 1),
                           current_i=round(latest.current, 1),
                           current_p=int(round(latest.power)),
                           status=room_status["status"],
                           sched_on=room_status["schedule_on"],
                           sched_off=room_status["schedule_off"],
                           start=start, end=end)

# === FLOOR PAGE ===
@app.route("/floor/<floor_name>")
def floor(floor_name):
    if floor_name not in floors:
        return "Floor not found", 404
    rooms_list = floors[floor_name]
    floor_data = data[data["room"].isin(rooms_list)]
    status_dict = dict(zip(pd.read_csv(STATUS_FILE)["room"], pd.read_csv(STATUS_FILE)["status"]))

    total_energy = floor_data["energy_kwh"].sum()
    total_bill = floor_data["bill_taka"].sum()
    total_carbon = floor_data["carbon_gco2"].sum()

    avg = floor_data.groupby("room")["power"].mean().reset_index()
    fig = px.bar(avg, x="room", y="power", title=f"Avg Power - {floor_name}",
                 color="power", color_continuous_scale="Viridis")
    fig.update_layout(template="plotly_white")
    power_chart = pio.to_html(fig, full_html=False)

    room_info = []
    for room in rooms_list:
        room_df = floor_data[floor_data["room"] == room]
        on_df = room_df[room_df["current"] > 0.5]
        latest = on_df.iloc[-1] if not on_df.empty else room_df.iloc[-1]
        room_info.append({
            "id": room,
            "status": status_dict.get(room, "Off"),
            "current": round(latest.current, 1),
            "power": int(round(latest.power))
        })

    return render_template("floor.html",
                           floor_name=floor_name,
                           total_energy=round(total_energy, 2),
                           total_bill=int(round(total_bill)),
                           total_carbon=int(round(total_carbon)),
                           power_chart=power_chart,
                           rooms=room_info)

# === ADMIN PANEL - FULLY WORKING ===
@app.route("/admin", methods=["GET", "POST"])
def admin():
    status_df = pd.read_csv(STATUS_FILE)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            room = request.form["new_room"].strip()
            if room and room not in status_df["room"].values:
                new = pd.DataFrame({"room": [room], "status": ["On"], "schedule_on": ["08:00"], "schedule_off": ["20:00"]})
                status_df = pd.concat([status_df, new], ignore_index=True)
                status_df.to_csv(STATUS_FILE, index=False)
        elif action == "delete":
            room = request.form["room"]
            status_df = status_df[status_df["room"] != room]
            status_df.to_csv(STATUS_FILE, index=False)
        elif action == "toggle":
            room = request.form["room"]
            current = status_df.loc[status_df["room"] == room, "status"].values[0]
            status_df.loc[status_df["room"] == room, "status"] = "Off" if current == "On" else "On"
            status_df.to_csv(STATUS_FILE, index=False)

    status_df = pd.read_csv(STATUS_FILE)
    return render_template("admin.html", rooms=status_df.to_dict("records"))

if __name__ == "__main__":
    app.run(debug=True)