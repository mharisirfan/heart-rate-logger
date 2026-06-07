"""
Heart Rate Dashboard Server
Receives:
timestamp, watch_hr, prototype_hr, D, F, R

- Uses timestamp/millis for x-axis
- Shows actual sampling rate
- Allows enable/disable plotting per channel
"""

from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
from collections import deque
import threading
import logging

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

live_buffer = deque(maxlen=1000)
buffer_lock = threading.Lock()

baseline_data = {
    "watch_hr": [],
    "prototype_hr": [],
    "D": [],
    "F": [],
    "R": []
}

baseline_lock = threading.Lock()


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def calculate_stats(values):
    values = [v for v in values if v is not None]

    if not values:
        return None

    values = sorted(values)
    n = len(values)

    return {
        "min": values[0],
        "q1": values[n // 4],
        "median": values[n // 2],
        "q3": values[(3 * n) // 4],
        "max": values[-1]
    }


def add_data_point(timestamp, watch_hr, prototype_hr, D, F, R):
    data_point = {
        "timestamp": timestamp,
        "watch_hr": safe_float(watch_hr),
        "prototype_hr": safe_float(prototype_hr),
        "D": safe_float(D),
        "F": safe_float(F),
        "R": safe_float(R)
    }

    with buffer_lock:
        live_buffer.append(data_point)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/live-data")
def live_data():
    with buffer_lock:
        return jsonify(list(live_buffer))


@app.route("/api/upload", methods=["POST"])
def upload_data():
    try:
        data = request.get_json()

        print(
            f"✓ Received | timestamp={data.get('timestamp')} | "
            f"Watch={data.get('watch_hr')} | "
            f"Proto={data.get('prototype_hr')} | "
            f"D={data.get('D')} | F={data.get('F')} | R={data.get('R')}"
        )

        add_data_point(
            data.get("timestamp"),
            data.get("watch_hr"),
            data.get("prototype_hr"),
            data.get("D"),
            data.get("F"),
            data.get("R")
        )

        return jsonify({"status": "OK"})

    except Exception as e:
        print(f"✗ Error receiving data: {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/capture-baseline", methods=["POST"])
def capture_baseline():
    with buffer_lock:
        for key in baseline_data:
            baseline_data[key] = [
                p[key] for p in live_buffer if p.get(key) is not None
            ]

    count = len(baseline_data["D"])
    print(f"✓ Baseline captured: {count} spectral samples")

    return jsonify({"status": "Baseline captured", "count": count})


@app.route("/api/baseline-stats")
def baseline_stats():
    stats = []

    with baseline_lock:
        for key, label in [
            ("watch_hr", "Watch HR"),
            ("prototype_hr", "Prototype HR"),
            ("D", "D"),
            ("F", "F"),
            ("R", "R")
        ]:
            s = calculate_stats(baseline_data[key])
            if s:
                stats.append({
                    "channel": label,
                    "type": "baseline",
                    **s
                })

    with buffer_lock:
        for key, label in [
            ("watch_hr", "Watch HR"),
            ("prototype_hr", "Prototype HR"),
            ("D", "D"),
            ("F", "F"),
            ("R", "R")
        ]:
            vals = [p[key] for p in live_buffer if p.get(key) is not None]
            s = calculate_stats(vals)
            if s:
                stats.append({
                    "channel": label,
                    "type": "current",
                    **s
                })

    return jsonify(stats)


@app.route("/api/reset", methods=["POST"])
def reset():
    with buffer_lock:
        live_buffer.clear()

    with baseline_lock:
        for key in baseline_data:
            baseline_data[key] = []

    return jsonify({"status": "System reset"})


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Heart Rate Monitor Dashboard</title>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@sgratzl/chartjs-chart-boxplot@3.10.0/build/index.umd.min.js"></script>

    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: Arial, sans-serif;
            background: #f0f2f5;
        }

        .header {
            min-height: 10vh;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            padding: 12px 30px;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            flex-wrap: wrap;
        }

        .header h1 {
            font-size: 1.5rem;
            color: #333;
        }

        .controls {
            display: flex;
            align-items: center;
            gap: 20px;
            flex-wrap: wrap;
        }

        .checkbox-group {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            font-size: 0.9rem;
        }

        .checkbox-group label {
            cursor: pointer;
            font-weight: bold;
        }

        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        button {
            padding: 9px 16px;
            font-size: 0.9rem;
            font-weight: bold;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            color: white;
        }

        #baselineBtn { background-color: #36A2EB; }
        #resetBtn { background-color: #777; }
        #toggleBtn { background-color: #ff4d4d; }

        .smallBtn {
            background-color: #333;
            padding: 7px 12px;
            font-size: 0.8rem;
        }

        .container {
            display: flex;
            flex-direction: column;
            height: 90vh;
            padding: 10px;
            gap: 10px;
        }

        .card {
            flex: 1;
            background: white;
            border-radius: 12px;
            padding: 15px;
            display: flex;
            flex-direction: column;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .chart-wrapper {
            flex-grow: 1;
            position: relative;
            min-height: 0;
        }

        h3 {
            margin-bottom: 10px;
            color: #333;
        }

        .status {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 5px;
        }
    </style>
</head>

<body>
    <div class="header">
        <h1>❤️ Heart Rate Monitor Dashboard</h1>

        <div class="controls">
            <div class="checkbox-group">
                <label style="color:#FF0000;">
                    <input type="checkbox" checked onchange="toggleDataset(0, this)">
                    Watch HR
                </label>

                <label style="color:#00AA00;">
                    <input type="checkbox" checked onchange="toggleDataset(1, this)">
                    Prototype HR
                </label>

                <label style="color:#0066FF;">
                    <input type="checkbox" checked onchange="toggleDataset(2, this)">
                    D
                </label>

                <label style="color:#FFAA00;">
                    <input type="checkbox" checked onchange="toggleDataset(3, this)">
                    F
                </label>

                <label style="color:#AA00FF;">
                    <input type="checkbox" checked onchange="toggleDataset(4, this)">
                    R
                </label>

                <button class="smallBtn" onclick="showAll()">Show All</button>
                <button class="smallBtn" onclick="hideAll()">Hide All</button>
                <button class="smallBtn" onclick="showOnly(4)">Only R</button>
                <button class="smallBtn" onclick="showOnly(3)">Only F</button>
                <button class="smallBtn" onclick="showOnly(2)">Only D</button>
            </div>

            <div class="btn-group">
                <button id="baselineBtn" onclick="captureBaseline()">Set Baseline</button>
                <button id="resetBtn" onclick="resetDemo()">Reset</button>
                <button id="toggleBtn" onclick="toggleUpdates()">Stop Updates</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="card" style="flex: 0.7;">
            <h3>Live Heart Rate + Spectral Channels</h3>
            <p class="status" id="liveStatus">Waiting for data...</p>
            <div class="chart-wrapper">
                <canvas id="lineChart"></canvas>
            </div>
        </div>

        <div class="card" style="flex: 0.3;">
            <h3>Baseline vs Current</h3>
            <p class="status" id="boxStatus">Click Set Baseline to capture baseline</p>
            <div class="chart-wrapper">
                <canvas id="boxChart"></canvas>
            </div>
        </div>
    </div>

<script>
    let isRunning = true;

    const channels = ["Watch HR", "Prototype HR", "D", "F", "R"];
    const colors = ["#FF0000", "#00AA00", "#0066FF", "#FFAA00", "#AA00FF"];

    const lineChart = new Chart(document.getElementById("lineChart"), {
        type: "line",
        data: {
            labels: [],
            datasets: channels.map((c, i) => ({
                label: c,
                borderColor: colors[i],
                backgroundColor: colors[i],
                borderWidth: 2,
                pointRadius: 2,
                tension: 0.25,
                data: [],
                yAxisID: i < 2 ? "y" : "y1"
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: true }
            },
            scales: {
                y: {
                    title: { display: true, text: "BPM" },
                    min: 40,
                    max: 200
                },
                y1: {
                    title: { display: true, text: "Spectral Value" },
                    position: "right",
                    grid: {
                        drawOnChartArea: false
                    }
                },
                x: {
                    title: { display: true, text: "Time (seconds)" },
                    ticks: {
                        display: true,
                        maxTicksLimit: 15
                    }
                }
            }
        }
    });

    const boxChart = new Chart(document.getElementById("boxChart"), {
        type: "boxplot",
        data: {
            labels: channels,
            datasets: [
                {
                    label: "Baseline",
                    backgroundColor: "#36A2EB",
                    borderColor: "#36A2EB",
                    data: Array(channels.length).fill(null)
                },
                {
                    label: "Current",
                    backgroundColor: "#FF9F40",
                    borderColor: "#FF9F40",
                    data: Array(channels.length).fill(null)
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: true }
            }
        }
    });

    function parseTimestampToMs(timestamp) {
        if (timestamp === null || timestamp === undefined) {
            return null;
        }

        const numericValue = Number(timestamp);

        if (!Number.isNaN(numericValue)) {
            return numericValue;
        }

        const dateValue = new Date(timestamp).getTime();

        if (!Number.isNaN(dateValue)) {
            return dateValue;
        }

        return null;
    }

    function buildTimeAxis(data) {
        const validTimes = data.map(d => parseTimestampToMs(d.timestamp));

        if (validTimes.length === 0 || validTimes[0] === null) {
            return data.map((_, i) => i);
        }

        const firstTime = validTimes[0];

        return validTimes.map((t, i) => {
            if (t === null) {
                return i;
            }
            return (t - firstTime) / 1000.0;
        });
    }

    function calculateSamplingRate(timeSeconds) {
        if (timeSeconds.length < 2) {
            return "---";
        }

        const totalTime = timeSeconds[timeSeconds.length - 1] - timeSeconds[0];

        if (totalTime <= 0) {
            return "---";
        }

        const fs = (timeSeconds.length - 1) / totalTime;
        return fs.toFixed(2);
    }

    function toggleDataset(index, checkbox) {
        const meta = lineChart.getDatasetMeta(index);
        meta.hidden = !checkbox.checked;
        lineChart.update("none");
    }

    function updateCheckboxesFromChart() {
        const checkboxes = document.querySelectorAll(".checkbox-group input[type='checkbox']");
        checkboxes.forEach((box, index) => {
            const meta = lineChart.getDatasetMeta(index);
            box.checked = !meta.hidden;
        });
    }

    function showOnly(index) {
        lineChart.data.datasets.forEach((_, i) => {
            const meta = lineChart.getDatasetMeta(i);
            meta.hidden = i !== index;
        });

        updateCheckboxesFromChart();
        lineChart.update("none");
    }

    function showAll() {
        lineChart.data.datasets.forEach((_, i) => {
            lineChart.getDatasetMeta(i).hidden = false;
        });

        updateCheckboxesFromChart();
        lineChart.update("none");
    }

    function hideAll() {
        lineChart.data.datasets.forEach((_, i) => {
            lineChart.getDatasetMeta(i).hidden = true;
        });

        updateCheckboxesFromChart();
        lineChart.update("none");
    }

    function captureBaseline() {
        fetch("/api/capture-baseline", { method: "POST" })
            .then(r => r.json())
            .then(data => {
                document.getElementById("boxStatus").textContent =
                    `Baseline captured with ${data.count} samples`;
                updateBoxplot();
            });
    }

    function resetDemo() {
        fetch("/api/reset", { method: "POST" }).then(() => {
            lineChart.data.labels = [];
            lineChart.data.datasets.forEach(ds => ds.data = []);

            boxChart.data.datasets[0].data = Array(channels.length).fill(null);
            boxChart.data.datasets[1].data = Array(channels.length).fill(null);

            lineChart.update();
            boxChart.update();

            document.getElementById("liveStatus").textContent = "Waiting for data...";
            document.getElementById("boxStatus").textContent = "Click Set Baseline to capture baseline";
        });
    }

    function toggleUpdates() {
        isRunning = !isRunning;
        document.getElementById("toggleBtn").innerText =
            isRunning ? "Stop Updates" : "Resume Updates";
    }

    function updateLineChart() {
        if (!isRunning) return;

        fetch("/api/live-data")
            .then(r => r.json())
            .then(data => {
                if (!data.length) return;

                const timeSeconds = buildTimeAxis(data);
                const fsText = calculateSamplingRate(timeSeconds);

                lineChart.data.labels = timeSeconds.map(t => Number(t).toFixed(2));

                lineChart.data.datasets[0].data = data.map(d => d.watch_hr);
                lineChart.data.datasets[1].data = data.map(d => d.prototype_hr);
                lineChart.data.datasets[2].data = data.map(d => d.D);
                lineChart.data.datasets[3].data = data.map(d => d.F);
                lineChart.data.datasets[4].data = data.map(d => d.R);

                const last = data[data.length - 1];

                document.getElementById("liveStatus").textContent =
                    `Samples: ${data.length} | ` +
                    `Actual Fs: ${fsText} Hz | ` +
                    `Watch: ${last.watch_hr ?? "---"} BPM | ` +
                    `Prototype: ${last.prototype_hr ?? "---"} BPM | ` +
                    `D=${last.D !== null && last.D !== undefined ? Number(last.D).toFixed(2) : "---"}, ` +
                    `F=${last.F !== null && last.F !== undefined ? Number(last.F).toFixed(2) : "---"}, ` +
                    `R=${last.R !== null && last.R !== undefined ? Number(last.R).toFixed(2) : "---"}`;

                lineChart.update("none");
            })
            .catch(err => console.error("Live chart error:", err));
    }

    function updateBoxplot() {
        fetch("/api/baseline-stats")
            .then(r => r.json())
            .then(stats => {
                const baselineMap = {};
                const currentMap = {};

                stats.forEach(s => {
                    const box = {
                        min: s.min,
                        q1: s.q1,
                        median: s.median,
                        q3: s.q3,
                        max: s.max
                    };

                    if (s.type === "baseline") {
                        baselineMap[s.channel] = box;
                    } else {
                        currentMap[s.channel] = box;
                    }
                });

                boxChart.data.datasets[0].data = channels.map(ch => baselineMap[ch] || null);
                boxChart.data.datasets[1].data = channels.map(ch => currentMap[ch] || null);

                document.getElementById("boxStatus").textContent =
                    `Baseline: ${Object.keys(baselineMap).length} channels | ` +
                    `Current: ${Object.keys(currentMap).length} channels`;

                boxChart.update("none");
            })
            .catch(err => console.error("Boxplot error:", err));
    }

    setInterval(updateLineChart, 250);
    setInterval(updateBoxplot, 1000);
</script>

</body>
</html>
"""


if __name__ == "__main__":
    print("\\n" + "=" * 60)
    print("Heart Rate Monitor Dashboard Server")
    print("=" * 60)
    print("Dashboard: http://localhost:5000/")
    print("Waiting for BLE logger data...")
    print("=" * 60 + "\\n")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False
    )