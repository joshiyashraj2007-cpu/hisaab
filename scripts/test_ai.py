"""Step 2 check: python -m scripts.test_ai  [optional path to a voice clip]"""
import sys
import time
from datetime import date, timedelta

from app import asr, extract

today = date.today()
yday = today - timedelta(days=1)

t = time.time()
print("warm-up:", extract.warmup(), f"{time.time() - t:.1f}s")

text = "kal subah saade aath baje se shaam saat baje tak garkheda site pe kaam kiya, sharma thekedar ne chaar sau pachaas rupaye diye"
if len(sys.argv) > 1:                        # also test speech on a real clip
    t = time.time()
    asr.load()
    asr.to_wav(sys.argv[1], "audio/test.wav")
    text = asr.transcribe("audio/test.wav", "hi")
    print(f"speech ({asr.ENGINE}) {time.time() - t:.1f}s ->", text)

t = time.time()
draft, err = extract.safe_extract(text, today.isoformat(), yday.isoformat())
print(f"qwen {time.time() - t:.1f}s ->", draft.model_dump(), "error:", err)