#!/usr/bin/env python3
"""מפיק REPORT.md מתוך data/history.csv: הורדות לפי שעה, ולפי זמן מאז פרסום המהדורה."""
import csv, os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DATA = os.environ.get("DATA_DIR", "data")
OUT = os.environ.get("REPORT_FILE", "REPORT.md")
IL = ZoneInfo("Asia/Jerusalem")


def p(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def main():
    with open(os.path.join(DATA, "history.csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_key = defaultdict(list)
    for r in rows:
        by_key[(r["repo"], r["tag"], r["asset"])].append(r)

    events = []  # (ts, repo, tag, asset, delta, minutes_after_publish)
    for (repo, tag, asset), lst in by_key.items():
        lst.sort(key=lambda r: r["ts"])
        prev = None
        for r in lst:
            ts, c = p(r["ts"]), int(r["count"])
            pub = p(r["release_published"]) if r["release_published"] else None
            if prev is None:
                # הופעה ראשונה: אם המהדורה פורסמה ממש לפני כן, כל הספירה היא הורדות חדשות. אחרת זו נקודת התחלה.
                d = c if pub and ts - pub <= timedelta(hours=2) else 0
            else:
                d = c - prev
            prev = c
            if d > 0:
                mins = (ts - pub).total_seconds() / 60 if pub else None
                events.append((ts, repo, tag, asset, d, mins))
    events.sort()

    L = ["# דוח הורדות", ""]
    L.append(f"סה\"כ הורדות שנצפו מאז תחילת המעקב: **{sum(e[4] for e in events)}**")
    L.append("")
    L.append("> הזמן בכל שורה הוא זמן הבדיקה. ההורדות קרו בין הבדיקה הקודמת לבדיקה הזו.")
    L.append("")

    # 48 שעות אחרונות לפי שעה
    now = datetime.now(timezone.utc)
    L += ["## 48 השעות האחרונות (שעון ישראל)", "", "| שעה | הורדות | פירוט |", "|---|---|---|"]
    hours = defaultdict(lambda: defaultdict(int))
    for ts, repo, tag, asset, d, _ in events:
        if now - ts <= timedelta(hours=48):
            h = ts.astimezone(IL).strftime("%Y-%m-%d %H:00")
            hours[h][f"{repo} {tag}"] += d
    if not hours:
        L.append("| – | 0 | |")
    for h in sorted(hours, reverse=True):
        det = ", ".join(f"{k} ×{v}" for k, v in sorted(hours[h].items(), key=lambda x: -x[1]))
        L.append(f"| {h} | {sum(hours[h].values())} | {det} |")
    L.append("")

    # לפי מהדורה: כמה הורדות בדקות הראשונות
    L += ["## לפי מהדורה: מהירות ההורדות אחרי הפרסום", "",
          "| פרויקט | מהדורה | עד 15 דק' | עד שעה | עד 24 שעות | סה\"כ שנצפה |", "|---|---|---|---|---|---|"]
    rel = defaultdict(lambda: [0, 0, 0, 0])
    for ts, repo, tag, asset, d, m in events:
        r = rel[(repo, tag)]
        r[3] += d
        if m is not None:
            if m <= 15: r[0] += d
            if m <= 60: r[1] += d
            if m <= 1440: r[2] += d
    for (repo, tag), r in sorted(rel.items()):
        L.append(f"| {repo} | {tag} | {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    L.append("")
    L.append("> הורדות רבות בדקות הראשונות, בעיקר בשעות לא שגרתיות ובכמות זהה בכל הקבצים, מחשידות כאוטומציה.")
    L.append("")

    # התפלגות לפי שעה ביום
    L += ["## התפלגות לפי שעה ביום (שעון ישראל)", "", "```"]
    hod = defaultdict(int)
    for ts, *_rest in events:
        hod[ts.astimezone(IL).hour] += _rest[3]
    mx = max(hod.values(), default=1)
    for h in range(24):
        L.append(f"{h:02d}:00 {'█' * round(20 * hod[h] / mx):<20} {hod[h]}")
    L += ["```", ""]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("נכתב", OUT)


if __name__ == "__main__":
    main()
