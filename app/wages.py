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


TOLERANCE_MIN = 30    # spoken time may differ from the check-in clock by this much


def minutes(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def compare_times(said_start, said_end, clock_start, clock_end):
    """Plain code, no AI: does what the worker SAID match the check-in / check-out CLOCK?
    'match', 'mismatch' (a gentle warning, never an accusation) or 'not-said'."""
    pairs = [(s, c) for s, c in ((said_start, clock_start), (said_end, clock_end)) if s and c]
    if not pairs:
        return "not-said"
    off = max(min(abs(minutes(s) - minutes(c)), 1440 - abs(minutes(s) - minutes(c))) for s, c in pairs)
    return "match" if off <= TOLERANCE_MIN else "mismatch"


def check_said(said_start, said_end, said_hours, clock_start, clock_end, clock_seconds):
    """Everything the worker said about his time, against the check-in clock. Plain code, no AI."""
    results = []
    t = compare_times(said_start, said_end, clock_start, clock_end)
    if t != "not-said":
        results.append(t)
    if said_hours is not None and clock_seconds is not None:      # "I worked 1 hour" vs the real length
        results.append("match" if abs(said_hours * 3600 - clock_seconds) <= TOLERANCE_MIN * 60 else "mismatch")
    if not results:
        return "not-said"
    return "mismatch" if "mismatch" in results else "match"


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