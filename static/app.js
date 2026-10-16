const $ = id => document.getElementById(id);
let WID = Number(localStorage.getItem("hisaab_wid")) || null;
let WORKER = null, NOTE = null, rec = null, chunks = [], t0 = 0, tick = null;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
function toast(msg) {
  const d = document.createElement("div"); d.className = "toast"; d.textContent = msg;
  document.body.appendChild(d); setTimeout(() => d.remove(), 2600);
}
const rupees = n => "₹" + Number(n || 0).toLocaleString("en-IN");

// ---------- workers ----------
async function loadWorkers() {
  const ws = await api("/api/workers");
  $("workerSel").innerHTML = ws.map(w => `<option value="${w.id}">${w.name}</option>`).join("");
  if (!ws.length) { $("register").classList.remove("hidden"); return; }
  if (!ws.find(w => w.id === WID)) WID = ws[0].id;
  $("workerSel").value = WID;
  await selectWorker(WID);
}
async function selectWorker(id) {
  WID = Number(id); localStorage.setItem("hisaab_wid", WID);
  WORKER = await api(`/api/workers/${WID}`);
  $("who").textContent = `${WORKER.name} · Zone ${WORKER.zone} · ${WORKER.skill.replace("_", "-")}`;
  $("claimLink").href = `claim.html?w=${WID}`;
  $("verifyLink").href = `verify.html?w=${WID}`;
  $("exportLink").href = `/api/workers/${WID}/export`;
  await loadDiary();
}
$("workerSel").onchange = e => selectWorker(e.target.value);
$("addWorker").onclick = () => $("register").classList.toggle("hidden");
$("rSave").onclick = async () => {
  if (!$("rName").value.trim()) return toast("Name is needed");
  const w = await api("/api/workers", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: $("rName").value.trim(), phone: $("rPhone").value || null, lang: $("rLang").value,
      zone: $("rZone").value, skill: $("rSkill").value, agreed_rate: Number($("rRate").value) || null }) });
  $("register").classList.add("hidden"); WID = w.id; await loadWorkers(); toast("Worker saved");
};

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
  fd.append("audio", blob, name); fd.append("lang", WORKER ? WORKER.lang : "hi");
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
      body: JSON.stringify({ text: $("typed").value, lang: WORKER ? WORKER.lang : "hi" }) }));
  } finally { $("status").textContent = ""; }
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
  $("timing").textContent = `Speech ${n.timing.speech_s}s · Qwen ${n.timing.qwen_s}s` + (n.warning ? " · AI unavailable, please fill by hand" : "");
  $("draft").classList.remove("hidden"); $("sealed").classList.add("hidden");
  $("draft").scrollIntoView({ behavior: "smooth" });
}
$("cancelBtn").onclick = () => { $("draft").classList.add("hidden"); NOTE = null; };
$("sealBtn").onclick = async () => {
  if (!$("fDate").value) return toast("Date is needed");
  const body = { worker_id: WID, work_date: $("fDate").value, start_time: $("fStart").value || null,
    end_time: $("fEnd").value || null, site: $("fSite").value || null, contractor: $("fContractor").value || null,
    amount_paid: $("fPaid").value === "" ? null : Number($("fPaid").value),
    transcript: NOTE.transcript, audio_file: NOTE.audio_file, audio_sha256: NOTE.audio_sha256 };
  try {
    const e = await api("/api/entries", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    showSealed(e); await loadDiary();
  } catch (err) { toast("Not sealed: " + err.message); }
};
function sentence(e) {
  return `${e.work_date}: ${e.start_time || "?"} se ${e.end_time || "?"}, ${e.hours ?? "?"} ghante, ${e.site || ""}. ` +
         `Mile ${e.amount_paid ?? "?"} rupaye.`;
}
function showSealed(e) {
  $("draft").classList.add("hidden"); $("sealed").classList.remove("hidden");
  $("sealedText").textContent = sentence(e);
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
  const items = d.entries.map(e => ({ date: e.work_date, e })).concat(d.missing_dates.map(m => ({ date: m })));
  items.sort((a, b) => b.date.localeCompare(a.date) || (b.e ? b.e.id : 0) - (a.e ? a.e.id : 0));
  if (!items.length) { $("diaryList").textContent = "No entries yet."; return; }
  $("diaryList").innerHTML = items.map(({ date, e }) => {
    const day = new Date(date + "T00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    if (!e) return `<div class="day gap"><span class="d">${day}</span><span class="m">No entry · कोई रिकॉर्ड नहीं</span></div>`;
    const audio = e.audio_file ? ` · <a href="/audio/${e.audio_file}" target="_blank">▶ audio</a>` : "";
    return `<div class="day"><span class="d">${day}</span>
      <span class="m">${e.start_time || "?"}–${e.end_time || "?"} · ${e.hours ?? "?"} h · ${e.site || ""} · paid ${rupees(e.amount_paid)}${audio}</span>
      <span class="h" title="${e.entry_hash}">🔒 ${e.entry_hash.slice(0, 8)}</span></div>`;
  }).join("");
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
loadWorkers().catch(err => toast("Server not reachable: " + err.message));
toggleSpeak();
