import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

DB_PATH = "data/trading.db"
PIPELINE_LOG = "logs/pipeline.log"
CRON_OUTPUT_LOGS = {
    "news": "logs/collector.log",
    "market": "logs/market_collector.log",
}

RECENT_HOURS = 48          # only show errors newer than this
MAX_SILENCE_HOURS = 2      # the news collector runs every 20 minutes
MAX_CANDLE_AGE_HOURS = 96  # covers weekends and long holidays
MAX_NEWS_AGE_DAYS = 7      # news is sparse, so this is deliberately loose

problems = []


def section(title):
    print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")


def read_lines(path):
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as f:
        return f.read().splitlines()


def parse_log_time(line):
    try:
        return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def check_cron():
    section("CRON JOBS")
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError:
        print("crontab command not found.")
        problems.append("crontab is not available on this machine")
        return
    jobs = [line for line in result.stdout.splitlines()
            if line.strip() and not line.startswith("#")]
    if not jobs:
        print("No cron jobs registered.")
        problems.append("No cron jobs registered, so nothing collects data automatically")
        return
    for job in jobs:
        print(job)


def check_pipeline_log():
    section(f"PIPELINE LOG ({PIPELINE_LOG})")
    lines = read_lines(PIPELINE_LOG)
    if not lines:
        print("Missing or empty.")
        problems.append("pipeline.log is missing or empty")
        return

    now = datetime.now()
    cutoff = now - timedelta(hours=RECENT_HOURS)
    recent_errors = []
    recent_warnings = 0
    last_time = None

    for line in lines:
        t = parse_log_time(line)
        if t is None:
            continue
        last_time = t
        if t < cutoff:
            continue
        if "[ERROR]" in line:
            recent_errors.append(line)
        elif "[WARNING]" in line:
            recent_warnings += 1

    if last_time is None:
        print("No readable timestamps.")
        return

    hours_ago = (now - last_time).total_seconds() / 3600
    print(f"Last activity: {last_time:%Y-%m-%d %H:%M:%S} ({hours_ago:.1f} hours ago)")
    print(f"Last {RECENT_HOURS}h: {len(recent_errors)} errors, {recent_warnings} warnings")
    if hours_ago > MAX_SILENCE_HOURS:
        problems.append(f"Nothing logged for {hours_ago:.1f} hours (laptop off, or collectors crashing)")
    if recent_errors:
        print("Recent errors:")
        for line in recent_errors[-5:]:
            print("  " + line)
        problems.append(f"{len(recent_errors)} error(s) logged in the last {RECENT_HOURS} hours")


def check_cron_output():
    section("CRON OUTPUT FILES (crash detector)")
    for name, path in CRON_OUTPUT_LOGS.items():
        lines = read_lines(path)
        if lines is None:
            print(f"{name}: {path} not found yet")
            continue
        modified = datetime.fromtimestamp(os.path.getmtime(path))
        age_hours = (datetime.now() - modified).total_seconds() / 3600
        crashed = any("Traceback" in line for line in lines[-15:])
        status = "CRASH in last run" if crashed else "no crash"
        print(f"{name}: last written {age_hours:.1f} hours ago, {status}")
        if crashed:
            problems.append(f"The {name} collector crashed on its last cron run (see {path})")
            for line in lines[-3:]:
                print("    " + line)


def check_database():
    section(f"DATABASE ({DB_PATH})")
    if not os.path.exists(DB_PATH):
        print("Database file not found.")
        problems.append("Database file not found")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        now_utc = datetime.now(timezone.utc)

        cur.execute("SELECT COUNT(*), MAX(collected_at) FROM articles")
        count, last = cur.fetchone()
        print(f"Articles: {count}")
        if last:
            days = (now_utc - datetime.fromisoformat(last)).total_seconds() / 86400
            print(f"  last collected: {last} ({days:.1f} days ago)")
            if days > MAX_NEWS_AGE_DAYS:
                problems.append(f"No new article saved for {days:.0f} days")
        cur.execute("SELECT provider, COUNT(*) FROM articles GROUP BY provider")
        for provider, n in cur.fetchall():
            print(f"  from {provider}: {n}")

        cur.execute("""
            SELECT instrument, COUNT(*), MIN(timestamp), MAX(timestamp),
                   SUM(CASE WHEN volume > 0 THEN 1 ELSE 0 END)
            FROM market_candles GROUP BY instrument
        """)
        rows = cur.fetchall()
        print("\nMarket candles:")
        if not rows:
            print("  none")
            problems.append("No market candles stored")
        for instrument, n, first, last, with_volume in rows:
            hours = (now_utc - datetime.fromisoformat(last)).total_seconds() / 3600
            print(f"  {instrument}: {n} candles")
            print(f"    from {first}")
            print(f"    to   {last} ({hours:.1f} hours ago; NSE trades Mon-Fri, 9:15-15:30 IST)")
            print(f"    candles with volume above 0: {with_volume}")
            if hours > MAX_CANDLE_AGE_HOURS:
                problems.append(f"{instrument}: newest candle is {hours:.0f} hours old")
            if not with_volume:
                print("    NOTE: volume is 0 everywhere (Yahoo gives no volume for the index)")
    except sqlite3.OperationalError as e:
        print(f"Database problem: {e}")
        problems.append(f"Database problem: {e}")
    finally:
        conn.close()


def main():
    print(f"Health check run at {datetime.now():%Y-%m-%d %H:%M:%S} (local time)")
    check_cron()
    check_pipeline_log()
    check_cron_output()
    check_database()

    section("SUMMARY")
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}")
    else:
        print("No problems detected.")


if __name__ == "__main__":
    main()
