"""
Latency tracking for the evaluation dashboard (Tech Stack item 7).
Every agent response gets timed and logged here -- this is what lets
"latency" actually be answered with a real number instead of a guess,
satisfying requirement #3 on Esam's list.
"""

import time
import csv
import os
from datetime import datetime
from contextlib import contextmanager

LOG_PATH = "data/latency_log.csv"
_FIELDS = ["timestamp", "task", "query", "latency_seconds"]


def _ensure_log_exists():
    if not os.path.exists(LOG_PATH):
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_FIELDS).writeheader()


def log_latency(task: str, query: str, latency_seconds: float):
    """Appends one row to the latency log. Called automatically by the
    time_response() context manager below -- you shouldn't normally need
    to call this directly."""
    _ensure_log_exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "task": task,
            "query": query,
            "latency_seconds": round(latency_seconds, 2),
        })


@contextmanager
def time_response(task: str, query: str):
    """Usage:
        with time_response("stock_position", user_query):
            result = agent.invoke(...)
    Times the block, logs it automatically when the block exits -- even
    if the block raises an error, so a slow failure still gets logged.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log_latency(task, query, elapsed)


def get_latency_summary() -> dict:
    """Quick stats for the evaluation dashboard -- avg/min/max latency
    per task, from everything logged so far."""
    if not os.path.exists(LOG_PATH):
        return {"message": "No responses logged yet -- ask the copilot something first."}

    import pandas as pd
    df = pd.read_csv(LOG_PATH)
    if df.empty:
        return {"message": "No responses logged yet."}

    summary = df.groupby("task")["latency_seconds"].agg(["mean", "min", "max", "count"]).round(2)
    return summary.to_dict(orient="index")


if __name__ == "__main__":
    import json
    print(json.dumps(get_latency_summary(), indent=2, default=str))
