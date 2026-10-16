import os
import sqlite3

DB_PATH = os.environ.get("HISAAB_DB", "hisaab.db")

# entries.kind: 'checkin' / 'checkout' (photo + GPS + laptop clock) or 'day' (the voice note).
SCHEMA = """
CREATE TABLE IF NOT EXISTS workers(
  id INTEGER PRIMARY KEY,
  name TEXT, phone TEXT, lang TEXT,
  zone TEXT, skill TEXT, agreed_rate REAL,
  created_at TEXT, key_hash TEXT);

CREATE TABLE IF NOT EXISTS entries(
  id INTEGER PRIMARY KEY,
  worker_id INTEGER, kind TEXT, work_date TEXT,
  start_time TEXT, end_time TEXT, hours REAL,
  site TEXT, contractor TEXT, amount_paid REAL,
  transcript TEXT, audio_file TEXT, audio_sha256 TEXT,
  at_time TEXT, lat REAL, lng REAL, gps_acc REAL,
  face_photo TEXT, face_sha256 TEXT, site_photo TEXT, site_sha256 TEXT,
  checkin_id INTEGER, checkout_id INTEGER,
  said_start TEXT, said_end TEXT, time_check TEXT,
  created_at TEXT, prev_hash TEXT, entry_hash TEXT);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row      # rows behave like dicts
    return con


def init():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()
