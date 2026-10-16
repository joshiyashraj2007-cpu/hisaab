"""Speech to text. Set ASR_ENGINE=indic (default), whisper, or stub."""
import hashlib
import os
import subprocess
import wave

import numpy as np

ENGINE = os.environ.get("ASR_ENGINE", "whisper")
_model = None

WHISPER_HINTS = {
    "hi": "मजदूरी, ठेकेदार, साइट, घंटे, रुपये, सुबह, शाम, आज, कल",
    "mr": "मजुरी, ठेकेदार, साइट, तास, रुपये, सकाळी, संध्याकाळी, आज, काल",
    "hi": "मजदूरी, ठेकेदार, साइट, घंटे, रुपये, सुबह, शाम, आज, कल, आठ बजे, सात बजे, नौ बजे, छह बजे, दस बजे",
}


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
    if ENGINE == "stub":
        return os.environ.get("STUB_TEXT",
                              "aaj subah aath baje se shaam saat baje tak garkheda site pe kaam kiya, "
                              "sharma thekedar ne chaar sau pachaas rupaye diye")
    if ENGINE == "indic":
        import torch
        wav = torch.from_numpy(read_wav(wav_path)).unsqueeze(0)
        with torch.no_grad():
            return str(_model(wav, lang, "ctc")).strip()
    segs, _ = _model.transcribe(read_wav(wav_path), language=lang, initial_prompt=WHISPER_HINTS.get(lang),
                                vad_filter=True)
    return " ".join(s.text.strip() for s in segs)