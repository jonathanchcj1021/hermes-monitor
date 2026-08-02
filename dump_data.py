#!/usr/bin/env python3
"""
Hermes Monitor Data Dumper
==========================
Collects all monitoring data from hermes CLI and writes to monitor_data.json
Run by cron job every 5 minutes.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
OUTPUT_FILE = OUTPUT_DIR / "monitor_data.json"


def run(*args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def parse_field(text, key):
    if not text:
        return "N/A"
    for line in text.splitlines():
        if line.strip().startswith(key):
            return line.split(":", 1)[-1].strip()
    return "N/A"


def parse_int(text, key):
    val = parse_field(text, key)
    try:
        return int(val.split()[0])
    except (ValueError, IndexError):
        return 0


def parse_cron(raw):
    if not raw:
        return []
    jobs = []
    current = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "[" in line and ("active" in line or "paused" in line):
            if current:
                jobs.append(current)
            current = {"status": "active" if "active" in line else "paused"}
        elif current is not None:
            if line.startswith("Name:"):
                current["name"] = line.split(":", 1)[-1].strip()
            elif line.startswith("Schedule:"):
                current["schedule"] = line.split(":", 1)[-1].strip()
            elif line.startswith("Next run:"):
                current["next_run"] = line.split(":", 1)[-1].strip()
            elif line.startswith("Last run:"):
                parts = line.split(":", 1)[-1].strip().rsplit(" ", 1)
                current["last_run"] = parts[0] if parts else ""
                current["last_status"] = parts[-1] if len(parts) > 1 else "unknown"
            elif line.startswith("Workdir:"):
                current["workdir"] = line.split(":", 1)[-1].strip()
    if current:
        jobs.append(current)
    return jobs


def main():
    data = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Agent status
    status_raw = run("hermes", "status", timeout=15)
    data["agent"] = {
        "model": parse_field(status_raw, "Model:"),
        "provider": parse_field(status_raw, "Provider:"),
        "jobs_active": parse_int(status_raw, "Jobs:"),
        "sessions_active": parse_int(status_raw, "Active:"),
        "gateway": "running" in (status_raw or ""),
    }

    # Cron jobs
    cron_raw = run("hermes", "cron", "list", timeout=15)
    data["cron_jobs"] = parse_cron(cron_raw)

    # Session stats
    stats_raw = run("hermes", "sessions", "stats", timeout=15)
    data["session_stats"] = {}
    if stats_raw:
        for line in stats_raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data["session_stats"][k.strip()] = v.strip()

    # Recent sessions
    sessions_raw = run("hermes", "sessions", "list", "--limit", "5", timeout=15)
    data["recent_sessions"] = [s.strip() for s in (sessions_raw or "").splitlines() if s.strip()]

    # Background processes
    proc_raw = run("hermes", "process", "list", timeout=15)
    data["processes"] = [p.strip() for p in (proc_raw or "").splitlines() if p.strip()]

    # System
    data["system"] = {
        "python": run("python3", "--version", timeout=5),
        "hermes": run("hermes", "--version", timeout=5),
    }

    # Write
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"✅ Written to {OUTPUT_FILE}")
    print(f"   Model: {data['agent']['model']}")
    print(f"   Jobs: {data['agent']['jobs_active']} active")
    print(f"   Sessions: {data['agent']['sessions_active']} active")
    print(f"   Gateway: {'ONLINE' if data['agent']['gateway'] else 'OFFLINE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
