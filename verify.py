"""Re-check a Hisaab export on any computer, without the app.
Usage:  python verify.py hisaab_worker_1.json"""
import hashlib
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
FIELDS, NUMS = data["fields"], {"hours", "amount_paid"}
prev = "0" * 64
for e in data["entries"]:
    d = {k: (float(e[k]) if k in NUMS and e[k] is not None else e[k]) for k in FIELDS}
    d["worker_id"] = int(d["worker_id"])
    h = hashlib.sha256((prev + json.dumps(d, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    if e["prev_hash"] != prev or h != e["entry_hash"]:
        sys.exit(f"ALTERED: entry {e['id']} ({e['work_date']}) does not match its seal")
    prev = h
print(f"OK: {len(data['entries'])} entries intact. Latest seal {prev}")
