#!/usr/bin/env python3
"""אוסף את מונה ההורדות של כל קבצי ה-Release ושומר שורה רק כשהמספר השתנה."""
import csv, json, os, urllib.request, urllib.error
from datetime import datetime, timezone

API = "https://api.github.com"
USER = os.environ.get("TARGET_USER", "Zvi-Dorsz-Zion")
TOKEN = os.environ.get("GITHUB_TOKEN")
DATA = os.environ.get("DATA_DIR", "data")
HIST = os.path.join(DATA, "history.csv")
FIELDS = ["ts", "repo", "tag", "asset", "count", "release_published"]


def get(url):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "downloads-tracker",
         "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def paged(url):
    out, page = [], 1
    sep = "&" if "?" in url else "?"
    while True:
        d = get(f"{url}{sep}per_page=100&page={page}")
        out += d
        if len(d) < 100:
            return out
        page += 1


def last_counts():
    last = {}
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                last[(row["repo"], row["tag"], row["asset"])] = int(row["count"])
    return last


def main():
    os.makedirs(DATA, exist_ok=True)
    last = last_counts()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for repo in paged(f"{API}/users/{USER}/repos?type=owner"):
        for rel in paged(f"{API}/repos/{USER}/{repo['name']}/releases"):
            for a in rel["assets"]:
                key = (repo["name"], rel["tag_name"], a["name"])
                c = a["download_count"]
                if last.get(key) != c:
                    rows.append([now, *key, c, rel.get("published_at") or ""])
    new_file = not os.path.exists(HIST)
    if rows:
        with open(HIST, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(FIELDS)
            w.writerows(rows)
    print(f"{len(rows)} שורות חדשות")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if rows else 'false'}\n")


if __name__ == "__main__":
    main()
