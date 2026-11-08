#!/usr/bin/env python3
"""אוסף את מונה ההורדות של קבצי ה-Release.

מצב רגיל: דגימה אחת.  מצב לולאה: LOOP_MINUTES>0 דוגם כל INTERVAL_SECONDS שניות.
נשמרת שורה רק כשמונה השתנה, יחד עם window_start = זמן הדגימה הקודמת (אורך חלון אי-הוודאות).
"""
import csv, json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
USER = os.environ.get("TARGET_USER", "Zvi-Dorsz-Zion")
TOKEN = os.environ.get("GITHUB_TOKEN")
DATA = os.environ.get("DATA_DIR", "data")
HIST = os.path.join(DATA, "history.csv")
SAMPLE = os.path.join(DATA, "last_sample.txt")
FIELDS = ["ts", "repo", "tag", "asset", "count", "release_published", "window_start"]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "downloads-tracker",
         "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise last


def paged(url):
    out, page = [], 1
    sep = "&" if "?" in url else "?"
    while True:
        d = get(f"{url}{sep}per_page=100&page={page}")
        out += d
        if len(d) < 100:
            return out
        page += 1


def ensure_schema():
    """מוסיף את העמודה window_start לקובץ ישן, פעם אחת."""
    if not os.path.exists(HIST):
        return
    with open(HIST, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if rows and "window_start" not in rows[0]:
        rows[0].append("window_start")
        for r in rows[1:]:
            r.append("")
        with open(HIST, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)


def last_counts():
    last = {}
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                last[(row["repo"], row["tag"], row["asset"])] = int(row["count"])
    return last


def read_sample_ts():
    try:
        return open(SAMPLE, encoding="utf-8").read().strip()
    except OSError:
        return ""


def sample(last, prev_ts):
    ts = now()
    rows = []
    for repo in paged(f"{API}/users/{USER}/repos?type=owner"):
        for rel in paged(f"{API}/repos/{USER}/{repo['name']}/releases"):
            for a in rel["assets"]:
                key = (repo["name"], rel["tag_name"], a["name"])
                c = a["download_count"]
                if last.get(key) != c:
                    rows.append([ts, *key, c, rel.get("published_at") or "", prev_ts])
    return ts, rows


def write_rows(rows):
    new_file = not os.path.exists(HIST)
    with open(HIST, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(FIELDS)
        w.writerows(rows)


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def publish(msg):
    if os.environ.get("CI_COMMIT") != "1":
        return
    sh("git", "config", "user.name", "downloads-bot")
    sh("git", "config", "user.email", "downloads-bot@users.noreply.github.com")
    if os.path.exists(HIST):
        subprocess.run([sys.executable, "report.py"])
    sh("git", "add", "data", "REPORT.md")
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        return
    sh("git", "commit", "-m", msg)
    for _ in range(3):
        if sh("git", "push").returncode == 0:
            return
        sh("git", "pull", "--rebase", "--autostash")


def main():
    os.makedirs(DATA, exist_ok=True)
    ensure_schema()
    last = last_counts()
    prev_ts = read_sample_ts()
    loop = float(os.environ.get("LOOP_MINUTES", "0"))
    interval = max(30, int(os.environ.get("INTERVAL_SECONDS", "180")))
    end = time.time() + loop * 60
    total_new = 0
    while True:
        t0 = time.time()
        try:
            ts, rows = sample(last, prev_ts)
            if rows:
                write_rows(rows)
                for r in rows:
                    last[(r[1], r[2], r[3])] = r[4]
                total_new += len(rows)
                print(f"{ts}: {len(rows)} שורות חדשות", flush=True)
            open(SAMPLE, "w", encoding="utf-8").write(ts)
            prev_ts = ts
            if rows:
                publish("update downloads")
        except Exception as e:  # noqa
            print("שגיאה בדגימה:", e, flush=True)
        if loop <= 0 or time.time() + interval >= end:
            break
        time.sleep(max(5, interval - (time.time() - t0)))
    publish("heartbeat")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if total_new else 'false'}\n")


if __name__ == "__main__":
    main()
