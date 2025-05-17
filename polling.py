#!/usr/bin/env python3
"""
Limitless API Polling Script with Transcript and Trigger Alerts

This script continuously polls the Limitless API for new or updated lifelogs,
writes them to a daily transcript, detects trigger words, and sends
notifications via ntfy when triggers occur. It implements an exponential
backoff strategy and maintains a log of all changes.
"""

import difflib
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
import pytz
from pytz import timezone as tz_timezone
from dotenv import load_dotenv

load_dotenv()

# API Configuration
LIMITLESS_API_KEY = os.environ.get("LIMITLESS_API_KEY", "")
LIMITLESS_API_URL = "https://api.limitless.ai/v1/lifelogs"
NTFY_TOPIC = "clark-m-todo"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
LOG_FILE = os.path.join(os.path.dirname(__file__), "polling_log.txt")

# transcript settings
TRANSCRIPT_ROOT = os.path.join(os.path.dirname(__file__), "transcripts")
TZ = tz_timezone("US/Eastern")
TRIGGER_WORDS = [r"to do list", r"perplexity", r"julio"]
TRIGGER_PATTERN = re.compile(
    r"(" + "|".join(TRIGGER_WORDS) + r")", re.IGNORECASE
)
NTFY_TRIGGER_URL = "https://ntfy.sh/clark-m-random"

# API Headers
HEADERS = {
    "X-API-Key": LIMITLESS_API_KEY,
    "Accept": "application/json",
}

# Polling Configuration
BACKOFF_INITIAL = 5  # Initial delay between polls in seconds
BACKOFF_MAX = 300    # Maximum delay between polls in seconds
STABLE_POLLS_REQUIRED = 3  # Number of unchanged polls before considering a lifelog stable

# Initialize EST timezone for date handling
EST = pytz.timezone('US/Eastern')


def today_est_date():
    """Get today's date in EST timezone in YYYY-MM-DD format."""
    return datetime.now(EST).strftime('%Y-%m-%d')


def fetch_lifelogs(date=None, start=None):
    """Fetch lifelogs from the Limitless API."""
    params = {
        "timezone": "US/Eastern",
        "includeMarkdown": "true",
        "includeHeadings": "true",
        "direction": "asc",
        "limit": 100,
    }
    if date:
        params["date"] = date
    if start:
        params["start"] = start

    response = requests.get(LIMITLESS_API_URL, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("lifelogs", [])


def send_ntfy_notification(content, title=None):
    """Send a notification via ntfy with only the most recent line of content."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    most_recent_line = lines[-1] if lines else "(No content)"
    headers = {"Title": title or "Limitless Update"}
    response = requests.post(NTFY_URL, data=most_recent_line.encode("utf-8"), headers=headers)
    response.raise_for_status()
    return response


def log_difference(lifelog_id, prev_content, new_content, content_time, ntfy_time):
    """Log the differences between previous and new content of a lifelog."""
    diff = list(difflib.unified_diff(
        prev_content.splitlines(),
        new_content.splitlines(),
        lineterm="",
    ))
    log_entry = (
        f"\n---\nLifelog ID: {lifelog_id}\nTime of content (Limitless): {content_time}\n"
        f"Time of ntfy notification: {ntfy_time}\n"
        f"Diff between previous and new content:\n{chr(10).join(diff) if diff else 'No difference.'}\n"
    )
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)


def read_last_log():
    """Read and return the contents of the log file."""
    if not os.path.exists(LOG_FILE):
        return "No log entries yet."
    with open(LOG_FILE, "r") as f:
        return f.read()


def handle_trigger(raw: str, entry_time: str, alerted_triggers: set, julio_triggered: bool) -> bool:
    """Detect trigger words in ``raw`` and send ntfy notifications.

    Parameters
    ----------
    raw : str
        The raw lifelog content.
    entry_time : str
        Timestamp used in the transcript and notification.
    alerted_triggers : set
        Set of trigger phrases already alerted during this run.
    julio_triggered : bool
        Whether the ``julio`` trigger has already fired.

    Returns
    -------
    bool
        Updated ``julio_triggered`` state.
    """

    trigger_search = TRIGGER_PATTERN.search(raw)
    if not trigger_search:
        return julio_triggered

    triggered_phrase = trigger_search.group(0).lower()

    # Special handling for the "julio" trigger so it only fires once per run
    if triggered_phrase == "julio":
        if julio_triggered:
            return julio_triggered
        requests.post(
            NTFY_TRIGGER_URL,
            data=f"triggered on 'julio' @ {entry_time}".encode(),
            headers={"Title": "trigger alert"},
        ).raise_for_status()
        return True

    # Generic trigger deduplication
    if triggered_phrase not in alerted_triggers:
        requests.post(
            NTFY_TRIGGER_URL,
            data=f"triggered on '{triggered_phrase}' @ {entry_time}".encode(),
            headers={"Title": "trigger alert"},
        ).raise_for_status()
        alerted_triggers.add(triggered_phrase)

    return julio_triggered


def transcript_path(now):
    """Return the path to today's transcript file, creating folders as needed."""
    y, m, d = now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")
    folder = os.path.join(TRANSCRIPT_ROOT, y, m, d)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{y}-{m}-{d}.md")


def main():
    """Main polling loop."""
    # transcript setup
    current_date = datetime.now(TZ).date()
    transcript_file = transcript_path(datetime.now(TZ))
    if not os.path.exists(transcript_file):
        with open(transcript_file, "w") as f:
            f.write(f"# transcript for {current_date.isoformat()}\n\n")

    last_lifelogs = {}
    last_stable_end_time = None
    backoff = BACKOFF_INITIAL
    alerted_triggers = set()  # Keep track of alerted trigger phrases
    julio_triggered = False  # Ensure "julio" only alerts once per run

    print("Starting polling loop...")
    while True:
        now_est = datetime.now(TZ)
        if now_est.date() != current_date:
            current_date = now_est.date()
            transcript_file = transcript_path(now_est)
            with open(transcript_file, "w") as f:
                f.write(f"# transcript for {current_date.isoformat()}\n\n")

        try:
            date = today_est_date()
            start = last_stable_end_time
            lifelogs = fetch_lifelogs(date=date, start=start)

            updated_ids = set()
            most_recent_update = None

            for lifelog in lifelogs:
                lifelog_id = lifelog.get("id")
                content = lifelog.get("markdown") or ""
                end_time = lifelog.get("endTime")
                title = lifelog.get("title") or "Limitless Update"
                prev = last_lifelogs.get(lifelog_id)

                if not prev:
                    most_recent_update = (lifelog, "")
                    last_lifelogs[lifelog_id] = {"content": content, "endTime": end_time, "stable_count": 1}
                else:
                    if content != prev["content"] or end_time != prev["endTime"]:
                        if most_recent_update is None or end_time > most_recent_update[0]["endTime"]:
                            most_recent_update = (lifelog, prev["content"])
                        last_lifelogs[lifelog_id] = {"content": content, "endTime": end_time, "stable_count": 1}
                    else:
                        last_lifelogs[lifelog_id]["stable_count"] += 1
                updated_ids.add(lifelog_id)

                entry_time = datetime.now(TZ).strftime("%H:%M:%S")
                raw = content

                def highlight(m):
                    return f"**{m.group(0)}**"

                highlighted = TRIGGER_PATTERN.sub(highlight, raw)
                md_entry = f"## {entry_time} — {title}\n\n{highlighted}\n\n"
                with open(transcript_file, "a") as tf:
                    tf.write(md_entry)

                julio_triggered = handle_trigger(
                    raw,
                    entry_time,
                    alerted_triggers,
                    julio_triggered,
                )

            for lifelog_id in list(last_lifelogs.keys()):
                if lifelog_id not in updated_ids:
                    del last_lifelogs[lifelog_id]

            if most_recent_update:
                lifelog, prev_content = most_recent_update
                content = lifelog.get("markdown") or ""
                end_time = lifelog.get("endTime")
                title = lifelog.get("title") or "Limitless Update"
                send_ntfy_notification(content, title=title)
                ntfy_time = datetime.now().isoformat()
                log_difference(lifelog.get("id"), prev_content, content, end_time, ntfy_time)

            stable_lifelogs = [
                (lid, info) for lid, info in last_lifelogs.items()
                if info["stable_count"] >= STABLE_POLLS_REQUIRED
            ]
            if stable_lifelogs:
                latest_stable = max(stable_lifelogs, key=lambda x: x[1]["endTime"])
                if last_stable_end_time != latest_stable[1]["endTime"]:
                    print(f"Stable up to endTime: {latest_stable[1]['endTime']}")
                last_stable_end_time = latest_stable[1]["endTime"]

            time.sleep(backoff)
            backoff = BACKOFF_INITIAL
        except Exception as e:
            print(f"Error occurred: {e}")
            print(f"Will retry in {backoff} seconds...")
            print("Don't worry - script will keep running and catch up when API is available again")
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
            print(f"Next retry will be in {backoff} seconds if error persists")


def print_log():
    """Print the contents of the log file to stdout."""
    print(read_last_log())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "log":
        print_log()
    else:
        main()
