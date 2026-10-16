"""Seed Ramesh's demo month through the SAME seal() code path the app uses.
Each day gets a check-in, a check-out and the day entry, all marked as demo data.
Run from the project folder:  python -m scripts.seed demo/ramesh.csv"""
import csv
import hashlib
import secrets
import sys

from app import chain, db, wages

GARKHEDA = (19.8676, 75.3364)        # demo site location, Chhatrapati Sambhajinagar

db.init()
con = db.connect()
row = con.execute("SELECT id FROM workers WHERE name=?", ("Ramesh Kumar",)).fetchone()
key = secrets.token_urlsafe(18)
if row:
    wid = row["id"]
    con.execute("UPDATE workers SET key_hash=? WHERE id=?", (hashlib.sha256(key.encode()).hexdigest(), wid))
else:
    wid = con.execute(
        "INSERT INTO workers(name, phone, lang, zone, skill, agreed_rate, created_at, key_hash) "
        "VALUES('Ramesh Kumar', NULL, 'hi', 'I', 'unskilled', 600, date('now'), ?)",
        (hashlib.sha256(key.encode()).hexdigest(),)).lastrowid
con.commit()

with open(sys.argv[1], encoding="utf-8") as f:
    for r in csv.DictReader(f):
        where = {"lat": GARKHEDA[0], "lng": GARKHEDA[1], "gps_acc": 15.0}
        cin = chain.seal(con, {"worker_id": wid, "kind": "checkin", "work_date": r["date"],
                               "at_time": f"{r['date']}T{r['start']}:00", **where,
                               "transcript": "[demo check-in seeded from demo/ramesh.csv]"})
        cout = chain.seal(con, {"worker_id": wid, "kind": "checkout", "work_date": r["date"],
                                "at_time": f"{r['date']}T{r['end']}:00", **where, "checkin_id": cin["id"],
                                "transcript": "[demo check-out seeded from demo/ramesh.csv]"})
        chain.seal(con, {
            "worker_id": wid, "kind": "day", "work_date": r["date"],
            "start_time": r["start"], "end_time": r["end"],
            "hours": wages.hours_between(r["start"], r["end"]),
            "site": r["site"], "contractor": r["contractor"],
            "amount_paid": float(r["paid"]),
            "transcript": "[demo row seeded from demo/ramesh.csv]",
            "checkin_id": cin["id"], "checkout_id": cout["id"],
            "said_start": r["start"], "said_end": r["end"], "time_check": "match",
        })
print(f"seeded worker {wid}; head = {chain.head(con, wid)[:16]}")
print(f"Link a device to Ramesh (open once on the laptop and on the phone):")
print(f"  http://localhost:8000/#pair={wid}.{key}")
con.close()
