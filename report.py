#!/usr/bin/env python3
"""מפיק REPORT.md מתוך data/history.csv."""
import csv, os, statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DATA = os.environ.get("DATA_DIR", "data")
OUT = os.environ.get("REPORT_FILE", "REPORT.md")
IL = ZoneInfo("Asia/Jerusalem")
DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def p(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def main():
    with open(os.path.join(DATA, "history.csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_key = defaultdict(list)
    for r in rows:
        by_key[(r["repo"], r["tag"], r["asset"])].append(r)

    ev = []  # dict: ts, repo, tag, asset, d, after_pub (דקות), win (דקות או None)
    for (repo, tag, asset), lst in by_key.items():
        lst.sort(key=lambda r: r["ts"])
        prev = None
        for r in lst:
            ts, c = p(r["ts"]), int(r["count"])
            pub = p(r["release_published"]) if r["release_published"] else None
            ws = r.get("window_start") or ""
            win = (ts - p(ws)).total_seconds() / 60 if ws else None
            if prev is None:
                d = c if pub and ts - pub <= timedelta(hours=2) else 0
            else:
                d = c - prev
            prev = c
            if d > 0:
                ev.append(dict(ts=ts, repo=repo, tag=tag, asset=asset, d=d, win=win,
                               after_pub=(ts - pub).total_seconds() / 60 if pub else None, sweep=False))
    ev.sort(key=lambda e: e["ts"])

    # זיהוי "סריקה": באותה דגימה, באותו פרויקט, +1 על 6 קבצים לפחות מ-3 גרסאות לפחות
    groups = defaultdict(list)
    for e in ev:
        groups[(e["ts"], e["repo"])].append(e)
    for g in groups.values():
        ones = [e for e in g if e["d"] == 1]
        if len(ones) >= 6 and len({e["tag"] for e in ones}) >= 3:
            for e in ones:
                e["sweep"] = True

    total = sum(e["d"] for e in ev)
    sweep = sum(e["d"] for e in ev if e["sweep"])
    wins = [e["win"] for e in ev if e["win"] is not None]
    L = ["# דוח הורדות", ""]
    L.append(f"סה\"כ הורדות שנצפו מאז תחילת המעקב: **{total}**")
    L.append(f"מתוכן בדפוס של סריקה (+1 על כל הקבצים של כמה גרסאות בבת אחת): **{sweep}**")
    if wins:
        L.append(f"אורך חלון הבדיקה בהורדות האחרונות: חציון {statistics.median(wins):.0f} דקות, מקסימום {max(wins):.0f} דקות")
    L += ["", "> זמן כל שורה הוא זמן הדגימה. ההורדות קרו בין הדגימה הקודמת (חלון) לדגימה הזו.", ""]

    now = datetime.now(timezone.utc)
    L += ["## 48 השעות האחרונות (שעון ישראל)", "", "| שעה | הורדות | פירוט |", "|---|---|---|"]
    hours = defaultdict(lambda: defaultdict(int))
    for e in ev:
        if now - e["ts"] <= timedelta(hours=48):
            h = e["ts"].astimezone(IL).strftime("%Y-%m-%d %H:00")
            hours[h][f"{e['repo']} {e['tag']}" + (" (סריקה)" if e["sweep"] else "")] += e["d"]
    if not hours:
        L.append("| – | 0 | |")
    for h in sorted(hours, reverse=True):
        det = ", ".join(f"{k} ×{v}" for k, v in sorted(hours[h].items(), key=lambda x: -x[1]))
        L.append(f"| {h} | {sum(hours[h].values())} | {det} |")
    L.append("")

    L += ["## לפי מהדורה: הורדות אחרי הפרסום", "",
          "| פרויקט | מהדורה | עד 15 דק' | עד שעה | עד 24 שעות | סה\"כ שנצפה |", "|---|---|---|---|---|---|"]
    rel = defaultdict(lambda: [0, 0, 0, 0])
    for e in ev:
        r = rel[(e["repo"], e["tag"])]
        r[3] += e["d"]
        m = e["after_pub"]
        if m is not None:
            if m <= 15: r[0] += e["d"]
            if m <= 60: r[1] += e["d"]
            if m <= 1440: r[2] += e["d"]
    for (repo, tag), r in sorted(rel.items()):
        L.append(f"| {repo} | {tag} | {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    L.append("")

    L += ["## לפי יום בשבוע (שעון ישראל)", "", "| יום | הורדות | מתוכן סריקות |", "|---|---|---|"]
    wd = defaultdict(lambda: [0, 0])
    for e in ev:
        k = e["ts"].astimezone(IL).weekday()
        wd[k][0] += e["d"]
        wd[k][1] += e["d"] if e["sweep"] else 0
    for k in [6, 0, 1, 2, 3, 4, 5]:
        L.append(f"| {DAYS[k]} | {wd[k][0]} | {wd[k][1]} |")
    L.append("")

    L += ["## לפי שעה ביום (שעון ישראל)", "",
          "נספרות רק הורדות שחלון הבדיקה שלהן עד 30 דקות, כדי שהשעה תהיה אמינה.", "", "```"]
    hod = defaultdict(int)
    unknown = 0
    for e in ev:
        if e["win"] is not None and e["win"] <= 30:
            hod[e["ts"].astimezone(IL).hour] += e["d"]
        else:
            unknown += e["d"]
    mx = max(hod.values(), default=1)
    for h in range(24):
        L.append(f"{h:02d}:00 {'█' * round(20 * hod[h] / mx):<20} {hod[h]}")
    L += ["```", "", f"הורדות בלי שעה אמינה (חלון גדול או לא ידוע): {unknown}", ""]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("נכתב", OUT)


if __name__ == "__main__":
    main()
