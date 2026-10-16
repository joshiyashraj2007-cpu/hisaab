const $ = id => document.getElementById(id);
let WID = Number(localStorage.getItem("hisaab_wid")) || null;
let WORKER = null, NOTE = null, rec = null, chunks = [], t0 = 0, tick = null, shiftTick = null;

// Text typed by people (names, sites) is always shown as text, never run as HTML.
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// Hidden phone key: given once when the worker registers (or links this phone), sent with every write.
let KEYS = {};
try { KEYS = JSON.parse(localStorage.getItem("hisaab_keys") || "{}"); } catch (e) { KEYS = {}; }
const saveKeys = () => { try { localStorage.setItem("hisaab_keys", JSON.stringify(KEYS)); } catch (e) {} };
const keyHdr = () => KEYS[WID] ? { "X-Hisaab-Key": KEYS[WID] } : {};
const pairing = location.hash.match(/^#pair=(\d+)\.([\w-]+)$/);
if (pairing) {
  KEYS[pairing[1]] = pairing[2]; saveKeys(); WID = Number(pairing[1]);
  localStorage.setItem("hisaab_wid", WID); history.replaceState(null, "", "/");
}

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof d === "string" ? d : (d ? "please check the values" : r.statusText));
  }
  return r.json();
}
function toast(msg) {
  const d = document.createElement("div"); d.className = "toast"; d.textContent = msg;
  document.body.appendChild(d); setTimeout(() => d.remove(), 3200);
}
const rupees = n => "₹" + Number(n || 0).toLocaleString("en-IN");

// ---------- workers ----------
async function loadWorkers() {
  const ws = await api("/api/workers");
  $("workerSel").innerHTML = ws.map(w => `<option value="${w.id}">${esc(w.name)}</option>`).join("");
  if (!ws.length) { $("register").classList.remove("hidden"); return; }
  if (!ws.find(w => w.id === WID)) WID = ws[0].id;
  $("workerSel").value = WID;
  await selectWorker(WID);
  if (pairing) toast("फ़ोन जुड़ गया · Phone linked to " + WORKER.name);
}
async function selectWorker(id) {
  WID = Number(id); localStorage.setItem("hisaab_wid", WID);
  WORKER = await api(`/api/workers/${WID}`);
  $("who").textContent = `${WORKER.name} · Zone ${WORKER.zone} · ${WORKER.skill.replace("_", "-")}`;
  $("claimLink").href = `claim.html?w=${WID}`;
  $("verifyLink").href = `verify.html?w=${WID}`;
  $("exportLink").href = `/api/workers/${WID}/export`;
  await loadShift(); await loadDiary();
}
$("workerSel").onchange = e => selectWorker(e.target.value);
$("addWorker").onclick = () => $("register").classList.toggle("hidden");
$("rSave").onclick = async () => {
  if (!$("rName").value.trim()) return toast("Name is needed");
  try {
    const w = await api("/api/workers", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("rName").value.trim(), phone: $("rPhone").value || null, lang: $("rLang").value,
        zone: $("rZone").value, skill: $("rSkill").value, agreed_rate: Number($("rRate").value) || null }) });
    KEYS[w.id] = w.device_key; saveKeys();
    $("register").classList.add("hidden"); WID = w.id; await loadWorkers(); toast("Worker saved");
  } catch (err) { toast("Not saved: " + err.message); }
};
$("linkPhone").onclick = async () => {
  if (!WID || !KEYS[WID]) return toast("This device is not linked to this worker");
  try {
    const p = await api(`/api/workers/${WID}/pair`, { headers: keyHdr() });
    $("pairQr").src = "data:image/png;base64," + p.qr_png;
    $("pairUrl").textContent = p.url.split("#")[0];
    $("pairBox").classList.remove("hidden");
  } catch (err) { toast(err.message); }
};
$("pairClose").onclick = () => $("pairBox").classList.add("hidden");

// ---------- check in / check out: photo, GPS, laptop clock ----------
async function snap(facing, label) {
  $("camLabel").textContent = label; $("cam").classList.remove("hidden");
  const v = $("camVideo");
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: facing, width: { ideal: 1280 } }, audio: false });
  try {
    v.srcObject = stream; await v.play();
    await new Promise((ok, no) => { $("camShot").onclick = ok; $("camCancel").onclick = () => no(new Error("cancelled")); });
    const c = document.createElement("canvas"), k = Math.min(1, 800 / v.videoWidth);
    c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    return await new Promise(r => c.toBlob(r, "image/jpeg", 0.8));
  } finally {
    stream.getTracks().forEach(t => t.stop()); v.srcObject = null;
  }
}
// GPS starts searching when the app opens, so a fix is ready by the time the worker taps Start.
let FIX = null, GPS_ERR = "searching";
const gpsText = () => FIX
  ? `📍 जगह मिल गई · Location ready (±${Math.round(FIX.coords.accuracy)} m)`
  : GPS_ERR === "blocked" ? "📍 जगह बंद है · Location blocked: allow it for this site in Chrome"
  : GPS_ERR === "none" ? "📍 This browser has no location"
  : "📍 जगह ढूँढ रहे हैं… · Finding location… (turn Location on, stand near a window)";
function startGps() {
  if (!navigator.geolocation) { GPS_ERR = "none"; return; }
  navigator.geolocation.watchPosition(p => { FIX = p; GPS_ERR = null; $("gps").textContent = gpsText(); },
    e => { if (e.code === 1) GPS_ERR = "blocked"; $("gps").textContent = gpsText(); },
    { enableHighAccuracy: true, maximumAge: 30000, timeout: 60000 });
}
async function where() {
  for (let i = 0; i < 15 && !FIX && GPS_ERR === "searching"; i++) await new Promise(r => setTimeout(r, 1000));
  return FIX && Date.now() - FIX.timestamp < 5 * 60000 ? FIX.coords : null;
}
const place = (lat, lng) => lat == null ? "" : `<a href="geo:${lat},${lng}?q=${lat},${lng}">📍 ${Number(lat).toFixed(4)}, ${Number(lng).toFixed(4)}</a>`;
async function shiftAction(kind) {
  if (!WID) return toast("Add a worker first");
  if (!KEYS[WID]) return toast("This phone is not linked to " + WORKER.name);
  let face = null, site = null;
  try {
    face = await snap("user", "अपना चेहरा · Your face");
    site = await snap("environment", "काम की जगह · The site");
  } catch (err) {
    if (err.message === "cancelled") { $("cam").classList.add("hidden"); return; }
    toast("Camera not available here - saving without photos");
  }
  $("cam").classList.add("hidden");
  $("shiftState").textContent = "सेव हो रहा है… · Saving…";
  const coords = await where();
  const fd = new FormData(); fd.append("worker_id", WID);
  if (coords) { fd.append("lat", coords.latitude); fd.append("lng", coords.longitude); fd.append("acc", coords.accuracy); }
  if (face) fd.append("face", face, "face.jpg");
  if (site) fd.append("site", site, "site.jpg");
  try {
    const r = await api(`/api/${kind}`, { method: "POST", headers: keyHdr(), body: fd });
    if (kind === "checkin") toast(`काम शुरू · Checked in at ${r.at_time.slice(11, 16)}` +
      (coords ? ` · 📍 ${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}` : " (no location)"));
    else {
      toast(`काम खत्म · ${r.start}–${r.end}, ${r.hours} h`);
      $("status").textContent = "अब बोलें: क्या काम किया, कितने पैसे मिले · Now say what you did and what you were paid";
      $("record").scrollIntoView({ behavior: "smooth" });
    }
  } catch (err) { toast("Not saved: " + err.message); }
  await loadShift();
}
$("shiftBtn").onclick = () => shiftAction($("shiftBtn").dataset.next || "checkin");

async function loadShift() {
  clearInterval(shiftTick); $("shiftTimer").textContent = "";
  const s = await api(`/api/workers/${WID}/shift`);
  const btn = $("shiftBtn");
  if (s.open) {
    btn.dataset.next = "checkout"; btn.className = "bigbtn end"; btn.innerHTML = "काम खत्म करें<small>End work</small>";
    $("shiftState").innerHTML = `काम चालू है · Working since ${esc(s.open.start)} ${place(s.open.lat, s.open.lng) || "· no location"}`;
    const begun = Date.now() - (Date.parse(s.server_time) - Date.parse(s.open.start_at));
    const show = () => {
      const sec = Math.max(0, Math.floor((Date.now() - begun) / 1000)), p = n => String(n).padStart(2, "0");
      $("shiftTimer").textContent = `${p(Math.floor(sec / 3600))}:${p(Math.floor(sec / 60) % 60)}:${p(sec % 60)}`;
    };
    show(); shiftTick = setInterval(show, 1000);
  } else {
    btn.dataset.next = "checkin"; btn.className = "bigbtn start"; btn.innerHTML = "काम शुरू करें<small>Start work</small>";
    $("shiftState").innerHTML = s.done
      ? `हाज़िरी ${esc(s.done.start)}–${esc(s.done.end)} सील हुई ${place(s.done.lat, s.done.lng)} · Shift sealed. Now record your voice note ↓`
      : "साइट पर पहुँचकर दबाएँ · Tap when you reach the site";
  }
  $("gps").textContent = gpsText();
}

// ---------- recording ----------
$("micBtn").onclick = async () => {
  if (!WID) return toast("Add a worker first");
  if (rec && rec.state === "recording") { rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    rec = new MediaRecorder(stream); chunks = [];
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      clearInterval(tick); $("micBtn").classList.remove("rec"); $("timer").textContent = "";
      sendAudio(new Blob(chunks, { type: rec.mimeType || "audio/webm" }), "note.webm");
    };
    rec.start(); t0 = Date.now(); $("micBtn").classList.add("rec");
    tick = setInterval(() => $("timer").textContent = ((Date.now() - t0) / 1000).toFixed(0) + " s", 250);
  } catch (err) {
    toast("Mic blocked here. Use 'Upload a recording' or 'Type instead'.");
  }
};
$("fileIn").onchange = e => e.target.files[0] && sendAudio(e.target.files[0], e.target.files[0].name);

async function sendAudio(blob, name) {
  const fd = new FormData();
  fd.append("audio", blob, name); fd.append("lang", WORKER ? WORKER.lang : "hi"); fd.append("worker_id", WID);
  $("status").textContent = "Listening and writing… / सुन रहे हैं…";
  try { showDraft(await api("/api/notes", { method: "POST", body: fd })); }
  catch (err) { toast("Could not process audio: " + err.message); }
  finally { $("status").textContent = ""; }
}
$("typedBtn").onclick = async () => {
  if (!$("typed").value.trim()) return;
  $("status").textContent = "Writing… / लिख रहे हैं…";
  try {
    showDraft(await api("/api/notes/text", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("typed").value, lang: WORKER ? WORKER.lang : "hi", worker_id: WID }) }));
  } catch (err) { toast("Could not make a draft: " + err.message); }
  finally { $("status").textContent = ""; }
};

// ---------- draft -> seal ----------
const FIELD = { work_date: "fDate", start_time: "fStart", end_time: "fEnd", site: "fSite", contractor: "fContractor", amount_paid: "fPaid" };
function showDraft(n) {
  NOTE = n; const d = n.draft;
  $("transcript").textContent = "“" + n.transcript + "”";
  for (const [k, id] of Object.entries(FIELD)) {
    $(id).value = d[k] ?? "";
    $(id).parentElement.classList.toggle("need", d[k] === null || d[k] === undefined || d.missing.includes(k));
  }
  const dur = sec => sec < 90 ? `${Math.round(sec)} sec` : sec < 5400 ? `${Math.round(sec / 60)} min` : `${(sec / 3600).toFixed(1)} h`;
  const chk = $("check");
  const said = [d.start_time || d.end_time ? `${d.start_time || "?"}–${d.end_time || "?"}` : "",
                d.duration_hours != null ? dur(d.duration_hours * 3600) : ""].filter(Boolean).join(", ") || "?";
  if (n.shift) {
    const clock = `${n.shift.start}–${n.shift.end} (${dur(n.shift.seconds)})`;
    chk.className = "check " + (n.time_check === "match" ? "ok" : n.time_check === "mismatch" ? "warn" : "");
    chk.textContent = n.time_check === "match"
      ? `✓ हाज़िरी से मेल खाता है · Matches your check-in ${clock}`
      : n.time_check === "mismatch"
        ? `⚠ हाज़िरी ${clock}, आपने कहा ${said}. कृपया जाँच लें · Your check-in says ${clock}, you said ${said}. The claim will use the check-in times.`
        : `हाज़िरी ${clock} · The check-in times ${clock} will be used.`;
  } else {
    chk.className = "check";
    chk.textContent = "आज की हाज़िरी नहीं · No check-in for this day: it will be saved as voice only.";
  }
  const heard = n.heard ? ` · heard ${n.heard === "en" ? "English" : n.heard === "mr" ? "Marathi" : "Hindi"}` : "";
  $("timing").textContent = `Speech ${n.timing.speech_s}s · Qwen ${n.timing.qwen_s}s${heard}` + (n.warning ? " · AI unavailable, please fill by hand" : "");
  $("draft").classList.remove("hidden"); $("sealed").classList.add("hidden");
  $("draft").scrollIntoView({ behavior: "smooth" });
}
$("cancelBtn").onclick = () => { $("draft").classList.add("hidden"); NOTE = null; };
$("sealBtn").onclick = async () => {
  if (!$("fDate").value) return toast("Date is needed");
  const body = { worker_id: WID, work_date: $("fDate").value, start_time: $("fStart").value || null,
    end_time: $("fEnd").value || null, site: $("fSite").value || null, contractor: $("fContractor").value || null,
    amount_paid: $("fPaid").value === "" ? null : Number($("fPaid").value),
    transcript: NOTE.transcript, audio_file: NOTE.audio_file, audio_sha256: NOTE.audio_sha256,
    checkin_id: NOTE.shift ? NOTE.shift.checkin_id : null, said_hours: NOTE.draft.duration_hours ?? null };
  try {
    const e = await api("/api/entries", { method: "POST", headers: { "Content-Type": "application/json", ...keyHdr() }, body: JSON.stringify(body) });
    showSealed(e); await loadShift(); await loadDiary();
  } catch (err) { toast("Not sealed: " + err.message); }
};
function sentence(e) {
  return `${e.work_date}: ${e.start_time || "?"} se ${e.end_time || "?"}, ${e.hours ?? "?"} ghante, ${e.site || ""}. ` +
         `Mile ${e.amount_paid ?? "?"} rupaye.`;
}
function showSealed(e) {
  $("draft").classList.add("hidden"); $("sealed").classList.remove("hidden");
  $("sealedText").textContent = sentence(e) + (e.checkin_id ? " ✓ हाज़िरी · check-in" : "");
  $("sealedHash").textContent = "Seal: " + e.entry_hash;
  const msg = `Hisaab seal ${e.work_date} (${WORKER.name}): ${e.entry_hash}`;
  $("waLink").href = "https://wa.me/?text=" + encodeURIComponent(msg);
  $("smsLink").href = "sms:?body=" + encodeURIComponent(msg);
  $("speakBtn").onclick = () => speak(sentence(e));
}

// ---------- hear it back (browser voice, no server work) ----------
function hindiVoice() { return speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith("hi")); }
function speak(text) {
  const u = new SpeechSynthesisUtterance(text); const v = hindiVoice();
  if (v) u.voice = v; u.lang = "hi-IN"; u.rate = 0.9; speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function toggleSpeak() { $("speakBtn").style.display = ("speechSynthesis" in window && hindiVoice()) ? "" : "none"; }
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = toggleSpeak;

// ---------- diary ----------
async function loadDiary() {
  const d = await api(`/api/workers/${WID}/entries`);
  const days = d.entries.filter(e => (e.kind || "day") === "day");
  const byId = Object.fromEntries(d.entries.map(e => [e.id, e]));
  const items = days.map(e => ({ date: e.work_date, e })).concat(d.missing_dates.map(m => ({ date: m })));
  items.sort((a, b) => b.date.localeCompare(a.date) || (b.e ? b.e.id : 0) - (a.e ? a.e.id : 0));
  if (!items.length) { $("diaryList").textContent = "No entries yet."; return; }
  $("diaryList").innerHTML = items.map(({ date, e }) => {
    const day = new Date(date + "T00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    if (!e) return `<div class="day gap"><span class="d">${day}</span><span class="m">No entry · कोई रिकॉर्ड नहीं</span></div>`;
    const audio = e.audio_file ? ` · <a href="/audio/${esc(e.audio_file)}" target="_blank">▶ audio</a>` : "";
    const cin = byId[e.checkin_id] || {};
    const proof = e.checkin_id ? (e.time_check === "mismatch" ? " · <b class='warnt'>⚠ check-in</b>" : " · <b class='okt'>✓ check-in</b>")
      + (cin.lat != null ? " · " + place(cin.lat, cin.lng) : "") : "";
    return `<div class="day"><span class="d">${day}</span>
      <span class="m">${esc(e.start_time) || "?"}–${esc(e.end_time) || "?"} · ${e.hours ?? "?"} h · ${esc(e.site)} · paid ${rupees(e.amount_paid)}${proof}${audio}</span>
      <span class="h" title="${esc(e.entry_hash)}">🔒 ${esc(e.entry_hash.slice(0, 8))}</span></div>`;
  }).join("");
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
startGps();
loadWorkers().catch(err => toast("Server not reachable: " + err.message));
toggleSpeak();
