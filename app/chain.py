"""Tamper-evident log: every entry's hash includes the previous entry's hash."""
import hashlib
import json
from datetime import datetime

GENESIS = "0" * 64
FIELDS = ["worker_id", "work_date", "start_time", "end_time", "hours", "site",
          "contractor", "amount_paid", "transcript", "audio_sha256", "created_at"]
NUMS = {"hours", "amount_paid"}


def canon(e):
    # SQLite gives back 450.0 for a saved 450, so numbers are always hashed as floats.
    d = {}
    for k in FIELDS:
        v = e.get(k)
        if k in NUMS and v is not None:
            v = float(v)
        if k == "worker_id" and v is not None:
            v = int(v)
        d[k] = v
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def entry_hash(e, prev_hash):
    return hashlib.sha256((prev_hash + canon(e)).encode("utf-8")).hexdigest()


def head(con, worker_id):
    row = con.execute("SELECT entry_hash FROM entries WHERE worker_id=? ORDER BY id DESC LIMIT 1",
                      (worker_id,)).fetchone()
    return row["entry_hash"] if row else GENESIS


def seal(con, e):
    """Add one entry to a worker's chain and return it with its hashes."""
    e = dict(e)
    e["created_at"] = datetime.now().isoformat(timespec="seconds")
    prev = head(con, e["worker_id"])
    e["prev_hash"] = prev
    e["entry_hash"] = entry_hash(e, prev)
    cols = FIELDS + ["audio_file", "prev_hash", "entry_hash"]
    cur = con.execute(
        f"INSERT INTO entries({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
        [e.get(c) for c in cols])
    con.commit()
    e["id"] = cur.lastrowid
    return e


def verify(entries):
    """entries = one worker's rows as dicts, ordered by id."""
    prev = GENESIS
    for e in entries:
        if e["prev_hash"] != prev or entry_hash(e, prev) != e["entry_hash"]:
            return {"ok": False, "broken_at": e["id"], "work_date": e["work_date"], "count": len(entries)}
        prev = e["entry_hash"]
    return {"ok": True, "head": prev, "count": len(entries)}