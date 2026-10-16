"""Speech to text. Set ASR_ENGINE=indic (default), whisper, or stub."""
import hashlib
import os
import subprocess
import wave

import numpy as np

ENGINE = os.environ.get("ASR_ENGINE", "whisper")
_model = None

WHISPER_HINTS = {
    "hi": "मजदूरी, ठेकेदार, साइट, घंटे, रुपये, सुबह, शाम, आज, कल, आठ बजे, सात बजे, नौ बजे, छह बजे, दस बजे",
    "mr": "मजुरी, ठेकेदार, साइट, तास, रुपये, सकाळी, संध्याकाळी, आज, काल",
    "en": "Today I worked at the site from 8 am to 6 pm, the contractor paid me 450 rupees.",
}


def pick_language(audio, lang):
    """Whisper guesses the language; we only choose between the worker's language and English.
    Whisper often hears Hindi as Urdu, so all Indic guesses count for the worker's language."""
    try:
        _, _, probs = _model.detect_language(audio)
    except Exception:
        return lang
    p = dict(probs)
    native = sum(p.get(c, 0) for c in ("hi", "mr", "ur", "ne", "pa", "gu"))
    return "en" if p.get("en", 0) > native else lang


def load():
    """Call once at server start. Loading takes 10-30 s; never do it per request."""
    global _model
    if ENGINE == "indic":
        from transformers import AutoModel
        _model = AutoModel.from_pretrained("models/indic",trust_remote_code=True)
    elif ENGINE == "whisper":
        from faster_whisper import WhisperModel
        _model = WhisperModel(os.environ.get("WHISPER_SIZE", "small"), device="cpu", compute_type="int8")


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def to_wav(src, dst):
    """Browser webm / phone m4a -> 16 kHz mono 16-bit WAV."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def read_wav(path):
    # Plain wave + numpy, so we do not depend on torchaudio's audio backends.
    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav_path, lang="hi"):
    """Returns (text, language heard)."""
    if ENGINE == "stub":
        return os.environ.get("STUB_TEXT",
                              "aaj subah aath baje se shaam saat baje tak garkheda site pe kaam kiya, "
                              "sharma thekedar ne chaar sau pachaas rupaye diye"), lang
    if ENGINE == "indic":
        import torch
        wav = torch.from_numpy(read_wav(wav_path)).unsqueeze(0)
        with torch.no_grad():
            return str(_model(wav, lang, "ctc")).strip(), lang
    audio = read_wav(wav_path)
    heard = pick_language(audio, lang)
    segs, _ = _model.transcribe(audio, language=heard, initial_prompt=WHISPER_HINTS.get(heard),
                                vad_filter=True, beam_size=5)
    return " ".join(s.text.strip() for s in segs), heard