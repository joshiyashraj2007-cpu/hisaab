import base64
import io
import os
import socket
import time
import uuid
from collections import Counter
from datetime import date, timedelta
from typing import Optional

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import asr, chain, db, extract, wages
from .letter import write_letter

AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
app = FastAPI(title="Hisaab")


@app.on_event("startup")
def startup():
    db.init()
    t = time.time()
    asr.load()
    warm = extract.warmup()
    print(f"[hisaab] speech={asr.ENGINE} qwen={extract.MODEL} warm={warm} ready in {time.time() - t:.1f}s")


# ---------- helpers ----------
def rows(sql, *args):
    con = db.connect()
    out = [dict(r) for r in con.execute(sql, args).fetchall()]
    con.close()
    return out


def get_worker(wid):
    w = rows("SELECT * FROM workers WHERE id=?", wid)
    if not w:
        raise HTTPException(404, "worker not found")
    return w[0]


def worker_entries(wid):
    return rows("SELECT * FROM entries WHERE worker_id=? ORDER BY id", wid)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))      # no packet is sent; just picks the LAN interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def qr_png_b64(text):
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------- workers ----------
class WorkerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    lang: str = "hi"
    zone: str = "I"
    skill: str = "unskilled"
    agreed_rate: Optional[float] = None


@app.post("/api/workers")
def create_worker(w: WorkerIn):
    con = db.connect()
    cur = con.execute(
        "INSERT INTO workers(name, phone, lang, zone, skill, agreed_rate, created_at) VALUES(?,?,?,?,?,?,date('now'))",
        (w.name, w.phone, w.lang, w.zone, w.skill, w.agreed_rate))
    con.commit()
    wid = cur.lastrowid
    con.close()
    return get_worker(wid)


@app.get("/api/workers")
def list_workers():
    return rows("SELECT * FROM workers ORDER BY id")


@app.get("/api/workers/{wid}")
def read_worker(wid: int):
    return get_worker(wid)


# ---------- voice note -> draft (nothing saved to the chain yet) ----------
def make_draft(text, lang, audio_file=None, audio_sha=None, t_asr=0.0):
    today = date.today()
    t = time.time()
    draft, err = extract.safe_extract(text, today.isoformat(), (today - timedelta(days=1)).isoformat())
    return {
        "transcript": text,
        "draft": draft.model_dump(),
        "audio_file": audio_file,
        "audio_sha256": audio_sha,
        "timing": {"speech_s": round(t_asr, 1), "qwen_s": round(time.time() - t, 1)},
        "warning": err,
    }


@app.post("/api/notes")
def voice_note(audio: UploadFile = File(...), lang: str = Form("hi")):
    ext = os.path.splitext(audio.filename or "")[1] or ".webm"
    name = uuid.uuid4().hex
    src = os.path.join(AUDIO_DIR, name + ext)
    with open(src, "wb") as f:
        f.write(audio.file.read())
    sha = asr.file_sha256(src)                  # fingerprint the ORIGINAL recording
    wav = os.path.join(AUDIO_DIR, name + ".wav")
    t = time.time()
    asr.to_wav(src, wav)
    text = asr.transcribe(wav, lang)
    return make_draft(text, lang, name + ext, sha, time.time() - t)


class TextNote(BaseModel):
    text: str
    lang: str = "hi"


@app.post("/api/notes/text")
def typed_note(n: TextNote):
    # Fallback when the mic or speech model fails: same Qwen step, no audio.
    return make_draft(n.text, n.lang)


# ---------- confirm -> seal ----------
class EntryIn(BaseModel):
    worker_id: int
    work_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    site: Optional[str] = None
    contractor: Optional[str] = None
    amount_paid: Optional[float] = None
    transcript: Optional[str] = None
    audio_file: Optional[str] = None
    audio_sha256: Optional[str] = None


@app.post("/api/entries")
def seal_entry(e: EntryIn):
    get_worker(e.worker_id)
    data = e.model_dump()
    if e.audio_file:                            # the audio must be the file we fingerprinted
        path = os.path.join(AUDIO_DIR, os.path.basename(e.audio_file))
        if not os.path.exists(path) or asr.file_sha256(path) != e.audio_sha256:
            raise HTTPException(400, "audio fingerprint does not match")
    data["hours"] = wages.hours_between(e.start_time, e.end_time)
    con = db.connect()
    sealed = chain.seal(con, data)
    con.close()
    return sealed


@app.get("/api/workers/{wid}/entries")
def diary(wid: int):
    es = worker_entries(wid)
    have = {e["work_date"] for e in es}
    missing = []
    if es:
        d0 = min(date.fromisoformat(d) for d in have)
        d1 = max(date.fromisoformat(d) for d in have)
        d = d0
        while d <= d1:
            if d.isoformat() not in have:
                missing.append(d.isoformat())
            d += timedelta(days=1)
    return {"entries": es, "missing_dates": missing,
            "head": es[-1]["entry_hash"] if es else chain.GENESIS}


@app.get("/api/workers/{wid}/verify")
def verify(wid: int):
    get_worker(wid)
    es = worker_entries(wid)
    result = chain.verify(es)
    audio_bad = []
    for e in es:                                # the recordings are checked too
        if e["audio_file"]:
            p = os.path.join(AUDIO_DIR, e["audio_file"])
            if not os.path.exists(p) or asr.file_sha256(p) != e["audio_sha256"]:
                audio_bad.append(e["id"])
    result["audio_altered"] = audio_bad
    result["ok"] = result["ok"] and not audio_bad
    return result

_letters = {}   # (worker id, latest seal) -> letter, so Qwen writes it only once


@app.get("/api/workers/{wid}/claim")
def claim(wid: int, request: Request):
    w = get_worker(wid)
    es = worker_entries(wid)
    if not es:
        raise HTTPException(400, "no entries yet")
    rate = wages.day_rate(w["zone"], w["skill"], w["agreed_rate"])
    c = wages.compute(es, rate)
    c["contractor"] = Counter(e["contractor"] for e in es if e["contractor"]).most_common(1)[0][0] \
        if any(e["contractor"] for e in es) else None
    c["site"] = Counter(e["site"] for e in es if e["site"]).most_common(1)[0][0] \
        if any(e["site"] for e in es) else None
    dates = sorted(e["work_date"] for e in es)
    c["period_from"], c["period_to"] = dates[0], dates[-1]
    c["head"] = es[-1]["entry_hash"]
    c["chain"] = chain.verify(es)

    # Qwen writes the letter once per (worker, latest seal); reloads are instant.
    key = (wid, c["head"])
    if key not in _letters:
        _letters[key] = write_letter(w, c, wages.RATES["source"])
    c["letter"], c["letter_by"] = _letters[key]

    port = request.url.port or 8000
    c["verify_url"] = f"http://{lan_ip()}:{port}/verify.html?w={wid}"
    c["qr_png"] = qr_png_b64(c["verify_url"])
    c["rates_source"] = wages.RATES["source"]
    c["rates_url"] = wages.RATES["source_url"]
    c["rates_meta"] = {k: wages.RATES.get(k) for k in
                       ("notification", "effective_from", "effective_to", "verified_for_period")}
    c["worker"] = w
    return c

app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
app.mount("/", StaticFiles(directory="static", html=True), name="static")