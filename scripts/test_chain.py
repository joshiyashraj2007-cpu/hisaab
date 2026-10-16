"""Step 1 check: python -m scripts.test_chain"""
import os
os.environ["HISAAB_DB"] = "test_chain.db"
if os.path.exists("test_chain.db"):
    os.remove("test_chain.db")

from app import chain, db

db.init()
con = db.connect()
for day, paid in [("2026-10-01", 450), ("2026-10-02", 450), ("2026-10-03", 400)]:
    chain.seal(con, {"worker_id": 1, "work_date": day, "start_time": "08:00", "end_time": "18:00",
                     "hours": 10, "site": "Garkheda", "contractor": "Sharma", "amount_paid": paid,
                     "transcript": "test", "audio_sha256": None, "audio_file": None})
rows = lambda: [dict(r) for r in con.execute("SELECT * FROM entries WHERE worker_id=1 ORDER BY id")]
print("honest :", chain.verify(rows()))
con.execute("UPDATE entries SET amount_paid=850 WHERE id=2")
con.commit()
print("tampered:", chain.verify(rows()))
con.close()
os.remove("test_chain.db")