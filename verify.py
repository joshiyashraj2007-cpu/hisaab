"""Re-check a Hisaab export on any computer, without the app.
Usage:  python verify.py hisaab_worker_1.json"""
import hashlib
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
FIELDS = data["fields"]
NUMS, INTS = set(data.get("nums", ["hours", "amount_paid"])), set(data.get("ints", ["worker_id"]))
prev = "0" * 64
for e in data["entries"]:
    d = {}
    for k in FIELDS:
        v = e.get(k)
        d[k] = float(v) if k in NUMS and v is not None else int(v) if k in INTS and v is not None else v
    h = hashlib.sha256((prev + json.dumps(d, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    if e["prev_hash"] != prev or h != e["entry_hash"]:
        sys.exit(f"ALTERED: entry {e['id']} ({e['work_date']}) does not match its seal")
    prev = h
print(f"OK: {len(data['entries'])} entries intact. Latest seal {prev}")
