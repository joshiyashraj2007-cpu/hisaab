"""All money maths lives here. The AI never calculates rupees."""
import json
from datetime import date

with open("data/rates.json", encoding="utf-8") as f:
    RATES = json.load(f)

NORMAL_HOURS = 8      # normal working day
OT_MULTIPLIER = 2     # overtime at twice the ordinary rate


def hours_between(start, end):
    if not start or not end:
        return None
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    mins = (eh * 60 + em) - (sh * 60 + sm)
    if mins < 0:
        mins += 24 * 60          # shift crossed midnight
    return round(mins / 60, 2)


def day_rate(zone, skill, agreed):
    monthly = RATES["construction"][zone][skill]
    return round(max(monthly / RATES["days_per_month"], agreed or 0), 2)


def compute(entries, rate):
    hourly = rate / NORMAL_HOURS
    rows, due, paid, ot_due, first_short = [], 0.0, 0.0, 0.0, None
    for e in entries:
        h = e["hours"] or 0
        normal, ot = min(h, NORMAL_HOURS), max(h - NORMAL_HOURS, 0)
        d = round(hourly * normal + hourly * OT_MULTIPLIER * ot, 2)
        p = e["amount_paid"] or 0
        short = round(d - p, 2)
        if short > 0 and first_short is None:
            first_short = e["work_date"]
        rows.append({**e, "due": d, "short": short, "ot_hours": ot})
        due += d
        paid += p
        ot_due += hourly * OT_MULTIPLIER * ot
    return {
        "rows": rows,
        "days": len(rows),
        "day_rate": rate,
        "due": round(due),
        "paid": round(paid),
        "overtime_due": round(ot_due),
        "shortfall": round(due - paid),
        "first_unpaid_date": first_short,
        "file_before": three_years_after(first_short),
    }


def three_years_after(iso):
    """Code on Wages s.45(6): claims within three years."""
    if not iso:
        return None
    d = date.fromisoformat(iso)
    try:
        return d.replace(year=d.year + 3).isoformat()
    except ValueError:           # 29 Feb
        return d.replace(year=d.year + 3, day=28).isoformat()