"""
Plot heart rate data from heart_rate_log.csv
"""

import csv
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def plot_heart_rate_data(csv_file: str = "heart_rate_log.csv") -> None:
    """Read CSV and plot heart rate over time."""
    timestamps = []
    heart_rates = []

    try:
        with open(csv_file, mode="r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Parse ISO format timestamp
                    ts = datetime.fromisoformat(row["timestamp"])
                    timestamps.append(ts)
                    heart_rates.append(int(row["heart_rate"]))
                except (ValueError, KeyError) as e:
                    print(f"Warning: Skipping invalid row: {row} ({e})")
    except FileNotFoundError:
        print(f"Error: {csv_file} not found.")
        return

    if not timestamps:
        print("No valid data found in CSV file.")
        return

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(timestamps, heart_rates, marker="o", linestyle="-", linewidth=2, markersize=4, color="red")

    # Format the plot
    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Heart Rate (BPM)", fontsize=12)
    ax.set_title("Heart Rate Over Time", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)

    # Format x-axis to show times nicely
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    plt.xticks(rotation=45, ha="right")

    # Add some statistics
    avg_hr = sum(heart_rates) / len(heart_rates)
    min_hr = min(heart_rates)
    max_hr = max(heart_rates)
    stats_text = f"Avg: {avg_hr:.1f} BPM | Min: {min_hr} BPM | Max: {max_hr} BPM"
    ax.text(0.5, 0.95, stats_text, transform=ax.transAxes, ha="center", va="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5), fontsize=10)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    plot_heart_rate_data()
