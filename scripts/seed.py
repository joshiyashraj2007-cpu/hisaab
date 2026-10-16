"""Seed Ramesh's demo month through the SAME seal() code path the app uses.
Run from the project folder:  python -m scripts.seed demo/ramesh.csv"""
import csv
import sys

from app import chain, db, wages

db.init()
con = db.connect()
row = con.execute("SELECT id FROM workers WHERE name=?", ("Ramesh Kumar",)).fetchone()
if row:
    wid = row["id"]
else:
    wid = con.execute(
        "INSERT INTO workers(name, phone, lang, zone, skill, agreed_rate, created_at) "
        "VALUES('Ramesh Kumar', NULL, 'hi', 'I', 'unskilled', 600, date('now'))").lastrowid
    con.commit()

with open(sys.argv[1], encoding="utf-8") as f:
    for r in csv.DictReader(f):
        chain.seal(con, {
            "worker_id": wid, "work_date": r["date"],
            "start_time": r["start"], "end_time": r["end"],
            "hours": wages.hours_between(r["start"], r["end"]),
            "site": r["site"], "contractor": r["contractor"],
            "amount_paid": float(r["paid"]),
            "transcript": "[demo row seeded from demo/ramesh.csv]",
            "audio_file": None, "audio_sha256": None,
        })
print(f"seeded worker {wid}; head = {chain.head(con, wid)[:16]}")
con.close()
