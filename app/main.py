import base64
import hashlib
import hmac
import io
import os
import secrets
import socket
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Literal, Optional

import qrcode
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import asr, chain, db, extract, letter, wages

AUDIO_DIR, PHOTO_DIR = "audio", "photos"
for _d in (AUDIO_DIR, PHOTO_DIR):
    os.makedirs(_d, exist_ok=True)
MAX_AUDIO, MAX_PHOTO = 10_000_000, 3_000_000        # bytes
AUDIO_EXT = {".webm", ".m4a", ".mp4", ".mp3", ".wav", ".ogg", ".aac", ".3gp", ".amr"}
DATE, HHMM = r"^\d{4}-\d{2}-\d{2}$", r"^([01]\d|2[0-3]):[0-5]\d$"
app = FastAPI(title="Hisaab")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    r = await call_next(request)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "no-referrer"
    r.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    if not request.url.path.startswith(("/docs", "/openapi.json")):     # Swagger UI loads its own CDN files
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
    return r


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


def public(w):
    return {k: v for k, v in w.items() if k != "key_hash"}      # the key's hash never leaves the laptop


def check_key(w, key):
    """Hidden phone key: only a phone registered or linked to this worker can write for them."""
    if not w.get("key_hash"):
        return
    if not key or not hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(), w["key_hash"]):
        raise HTTPException(403, "this phone is not linked to this worker")


def worker_entries(wid):
    return rows("SELECT * FROM entries WHERE worker_id=? ORDER BY id", wid)


def day_entries(es):
    return [e for e in es if (e["kind"] or "day") == "day"]


def shifts(es):
    """(the open check-in, the latest finished shift still waiting for its voice note)."""
    used = {e["checkin_id"] for e in es if e["kind"] == "day" and e["checkin_id"]}
    open_in, done = None, None
    for e in es:
        if e["kind"] == "checkin":
            open_in = e
        elif e["kind"] == "checkout" and open_in and e["checkin_id"] == open_in["id"]:
            if open_in["id"] not in used:
                done = (open_in, e)
            open_in = None
    return open_in, done


def shift_info(cin, cout=None):
    s = {"checkin_id": cin["id"], "date": cin["work_date"], "start": cin["at_time"][11:16], "start_at": cin["at_time"],
         "lat": cin["lat"], "lng": cin["lng"], "photos": bool(cin["face_sha256"])}
    if cout:
        s.update(checkout_id=cout["id"], end=cout["at_time"][11:16], end_at=cout["at_time"],
                 hours=wages.hours_between(s["start"], cout["at_time"][11:16]),
                 seconds=int((datetime.fromisoformat(cout["at_time"]) - datetime.fromisoformat(cin["at_time"])).total_seconds()))
    return s


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


def save_photo(up):
    data = up.file.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "photo too large")
    if data[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    else:
        raise HTTPException(400, "photo must be a JPEG or PNG")
    name = uuid.uuid4().hex + ext
    with open(os.path.join(PHOTO_DIR, name), "wb") as f:
        f.write(data)
    return name, hashlib.sha256(data).hexdigest()


def seal_event(kind, wid, lat, lng, acc, face, site, checkin_id=None):
    at = datetime.now().isoformat(timespec="seconds")      # the laptop's clock, never the phone's
    if lat is not None and lng is not None:
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise HTTPException(400, "bad location")
        lat, lng = round(lat, 6), round(lng, 6)
        acc = round(acc, 1) if acc is not None else None
    else:
        lat = lng = acc = None
    e = {"worker_id": wid, "kind": kind, "work_date": at[:10], "at_time": at,
         "lat": lat, "lng": lng, "gps_acc": acc, "checkin_id": checkin_id}
    if face is not None:
        e["face_photo"], e["face_sha256"] = save_photo(face)
    if site is not None:
        e["site_photo"], e["site_sha256"] = save_photo(site)
    con = db.connect()
    sealed = chain.seal(con, e)
    con.close()
    return sealed


# ---------- workers ----------
class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: Optional[str] = Field(None, max_length=15)
    lang: Literal["hi", "mr", "en"] = "hi"
    zone: Literal["I", "II", "III"] = "I"
    skill: Literal["unskilled", "semi_skilled", "skilled"] = "unskilled"
    agreed_rate: Optional[float] = Field(None, ge=0, le=10000)


@app.post("/api/workers")
def create_worker(w: WorkerIn):
    key = secrets.token_urlsafe(18)                         # shown once, kept only on the phone
    con = db.connect()
    cur = con.execute(
        "INSERT INTO workers(name, phone, lang, zone, skill, agreed_rate, created_at, key_hash) "
        "VALUES(?,?,?,?,?,?,date('now'),?)",
        (w.name, w.phone, w.lang, w.zone, w.skill, w.agreed_rate, hashlib.sha256(key.encode()).hexdigest()))
    con.commit()
    wid = cur.lastrowid
    con.close()
    return {**public(get_worker(wid)), "device_key": key}


@app.get("/api/workers")
def list_workers():
    return [public(w) for w in rows("SELECT * FROM workers ORDER BY id")]


@app.get("/api/workers/{wid}")
def read_worker(wid: int):
    return public(get_worker(wid))


@app.get("/api/workers/{wid}/pair")
def pair(wid: int, request: Request, x_hisaab_key: Optional[str] = Header(None)):
    """Link a second phone: a QR that carries this worker's key, like WhatsApp Web."""
    w = get_worker(wid)
    if not w.get("key_hash") or not x_hisaab_key:
        raise HTTPException(403, "this phone is not linked to this worker")
    check_key(w, x_hisaab_key)
    url = f"http://{lan_ip()}:{request.url.port or 8000}/#pair={wid}.{x_hisaab_key}"
    return {"url": url, "qr_png": qr_png_b64(url)}


# ---------- check in / check out (photo + GPS + laptop clock, sealed at once) ----------
@app.get("/api/workers/{wid}/shift")
def shift_state(wid: int):
    get_worker(wid)
    open_in, done = shifts(worker_entries(wid))
    return {"open": shift_info(open_in) if open_in else None, "done": shift_info(*done) if done else None,
            "server_time": datetime.now().isoformat(timespec="seconds")}


@app.post("/api/checkin")
def checkin(worker_id: int = Form(...), lat: Optional[float] = Form(None), lng: Optional[float] = Form(None),
            acc: Optional[float] = Form(None), face: Optional[UploadFile] = File(None),
            site: Optional[UploadFile] = File(None), x_hisaab_key: Optional[str] = Header(None)):
    check_key(get_worker(worker_id), x_hisaab_key)
    if shifts(worker_entries(worker_id))[0]:
        raise HTTPException(409, "already checked in")
    return seal_event("checkin", worker_id, lat, lng, acc, face, site)


@app.post("/api/checkout")
def checkout(worker_id: int = Form(...), lat: Optional[float] = Form(None), lng: Optional[float] = Form(None),
             acc: Optional[float] = Form(None), face: Optional[UploadFile] = File(None),
             site: Optional[UploadFile] = File(None), x_hisaab_key: Optional[str] = Header(None)):
    check_key(get_worker(worker_id), x_hisaab_key)
    open_in, _ = shifts(worker_entries(worker_id))
    if not open_in:
        raise HTTPException(409, "not checked in")
    out = seal_event("checkout", worker_id, lat, lng, acc, face, site, checkin_id=open_in["id"])
    return shift_info(open_in, out)


# ---------- voice note -> draft (nothing saved to the chain yet) ----------
def make_draft(text, lang, worker_id=None, audio_file=None, audio_sha=None, t_asr=0.0, heard=None):
    today = date.today()
    t = time.time()
    draft, err = extract.safe_extract(text, today.isoformat(), (today - timedelta(days=1)).isoformat())
    out = {
        "transcript": text,
        "heard": heard,
        "draft": draft.model_dump(),
        "audio_file": audio_file,
        "audio_sha256": audio_sha,
        "timing": {"speech_s": round(t_asr, 1), "qwen_s": round(time.time() - t, 1)},
        "warning": err,
        "shift": None,
        "time_check": "no-checkin",
    }
    if worker_id:
        _, done = shifts(worker_entries(worker_id))
        if done:
            out["shift"] = shift_info(*done)
            sh = out["shift"]
            out["time_check"] = wages.check_said(draft.start_time, draft.end_time, draft.duration_hours,
                                                 sh["start"], sh["end"], sh["seconds"])
    return out


@app.post("/api/notes")
def voice_note(audio: UploadFile = File(...), lang: Literal["hi", "mr", "en"] = Form("hi"),
               worker_id: Optional[int] = Form(None)):
    ext = os.path.splitext(audio.filename or "")[1].lower()
    ext = ext if ext in AUDIO_EXT else ".webm"
    data = audio.file.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "recording too large")
    name = uuid.uuid4().hex
    src = os.path.join(AUDIO_DIR, name + ext)
    with open(src, "wb") as f:
        f.write(data)
    sha = asr.file_sha256(src)                  # fingerprint the ORIGINAL recording
    wav = os.path.join(AUDIO_DIR, name + ".wav")
    t = time.time()
    asr.to_wav(src, wav)
    text, heard = asr.transcribe(wav, lang)
    return make_draft(text, lang, worker_id, name + ext, sha, time.time() - t, heard)


class TextNote(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    lang: Literal["hi", "mr", "en"] = "hi"
    worker_id: Optional[int] = None


@app.post("/api/notes/text")
def typed_note(n: TextNote):
    # Fallback when the mic or speech model fails: same Qwen step, no audio.
    return make_draft(n.text, n.lang, n.worker_id)


# ---------- confirm -> seal ----------
class EntryIn(BaseModel):
    worker_id: int
    work_date: str = Field(pattern=DATE)
    start_time: Optional[str] = Field(None, pattern=HHMM)
    end_time: Optional[str] = Field(None, pattern=HHMM)
    site: Optional[str] = Field(None, max_length=80)
    contractor: Optional[str] = Field(None, max_length=80)
    amount_paid: Optional[float] = Field(None, ge=0, le=100000)
    transcript: Optional[str] = Field(None, max_length=2000)
    audio_file: Optional[str] = Field(None, max_length=64)
    audio_sha256: Optional[str] = Field(None, max_length=64)
    checkin_id: Optional[int] = None
    said_hours: Optional[float] = Field(None, ge=0, le=24)


@app.post("/api/entries")
def seal_entry(e: EntryIn, x_hisaab_key: Optional[str] = Header(None)):
    check_key(get_worker(e.worker_id), x_hisaab_key)
    data = e.model_dump()
    data.pop("said_hours")                      # used for the time check only, not a sealed column
    if e.audio_file:                            # the audio must be the file we fingerprinted
        path = os.path.join(AUDIO_DIR, os.path.basename(e.audio_file))
        if not os.path.exists(path) or asr.file_sha256(path) != e.audio_sha256:
            raise HTTPException(400, "audio fingerprint does not match")
    data.update(kind="day", said_start=e.start_time, said_end=e.end_time, time_check="no-checkin")
    if e.checkin_id:
        _, done = shifts(worker_entries(e.worker_id))
        if not done or done[0]["id"] != e.checkin_id:
            raise HTTPException(409, "that check-in is not waiting for a voice note")
        s = shift_info(*done)
        data["time_check"] = wages.check_said(e.start_time, e.end_time, e.said_hours, s["start"], s["end"], s["seconds"])
        # The claim uses the clock, not the voice; what he said is kept beside it.
        data.update(work_date=s["date"], start_time=s["start"], end_time=s["end"], checkout_id=s["checkout_id"])
    data["hours"] = wages.hours_between(data["start_time"], data["end_time"])
    con = db.connect()
    sealed = chain.seal(con, data)
    con.close()
    return sealed


@app.get("/api/workers/{wid}/entries")
def diary(wid: int):
    es = worker_entries(wid)
    have = {e["work_date"] for e in day_entries(es)}
    missing = []
    if have:
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
    altered = []
    for e in es:                                # the recordings and photos are checked too
        for f, h, folder in (("audio_file", "audio_sha256", AUDIO_DIR), ("face_photo", "face_sha256", PHOTO_DIR),
                             ("site_photo", "site_sha256", PHOTO_DIR)):
            if e[f]:
                p = os.path.join(folder, e[f])
                if not os.path.exists(p) or asr.file_sha256(p) != e[h]:
                    altered.append(e["id"])
                    break
    result["audio_altered"] = altered
    result["ok"] = result["ok"] and not altered
    return result


@app.get("/api/workers/{wid}/claim")
def claim(wid: int, request: Request):
    w = get_worker(wid)
    es = worker_entries(wid)
    days = day_entries(es)
    if not days:
        raise HTTPException(400, "no entries yet")
    rate = wages.day_rate(w["zone"], w["skill"], w["agreed_rate"])
    c = wages.compute(days, rate)
    by_id = {e["id"]: e for e in es}
    for r in c["rows"]:                     # say exactly what proves each day, nothing more
        cin = by_id.get(r["checkin_id"]) or {}
        r["photo"], r["gps"] = bool(cin.get("face_sha256")), cin.get("lat") is not None
    c["verified_days"] = sum(1 for r in c["rows"] if r["checkin_id"])
    c["photo_days"] = sum(1 for r in c["rows"] if r["photo"])
    c["contractor"] = Counter(e["contractor"] for e in days if e["contractor"]).most_common(1)[0][0] \
        if any(e["contractor"] for e in days) else None
    c["site"] = Counter(e["site"] for e in days if e["site"]).most_common(1)[0][0] \
        if any(e["site"] for e in days) else None
    dates = sorted(e["work_date"] for e in days)
    c["period_from"], c["period_to"] = dates[0], dates[-1]
    c["head"] = es[-1]["entry_hash"]
    c["chain"] = chain.verify(es)
    c["letter"], c["letter_by"] = letter.template(w, c), "template"     # no AI in the letter
    port = request.url.port or 8000
    c["verify_url"] = f"http://{lan_ip()}:{port}/verify.html?w={wid}"
    c["qr_png"] = qr_png_b64(c["verify_url"])
    c["rates_source"] = wages.RATES["source"]
    c["rates_url"] = wages.RATES["source_url"]
    c["worker"] = public(w)
    return c


@app.get("/api/workers/{wid}/export")
def export(wid: int):
    w = get_worker(wid)
    body = {"worker": public(w), "entries": worker_entries(wid), "hash": "sha256",
            "fields": chain.FIELDS, "nums": sorted(chain.NUMS), "ints": sorted(chain.INTS)}
    return JSONResponse(body, headers={"Content-Disposition": f'attachment; filename="hisaab_worker_{wid}.json"'})


app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
app.mount("/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
