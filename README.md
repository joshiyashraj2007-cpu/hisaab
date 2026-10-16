# Hisaab (हिसाब): a worker's voice, sealed into wage evidence

OpenForge 2026 · Track 1: Open Weight AI & Open Source Tools · PS07 Migrant Worker Wage-Theft Evidence Builder
Team [name]: Simran Singh Bagga, [member 2]

## What it does
A construction worker records a short voice note in Hindi or Marathi after each shift. Open-weight models running offline
turn it into a daily record, each record is sealed with a SHA-256 hash chain, and at month end the app compares pay with
Maharashtra's notified minimum wage and prints a claim under Section 45 of the Code on Wages, 2019.

## Open-weight models used
| Model | Parameters | Job | Licence |
| --- | --- | --- | --- |
| Qwen3.5-4B (via Ollama, `qwen3.5:4b`) | 4B (Hugging Face lists 5B in total) | Transcript → structured record | Apache-2.0, https://huggingface.co/Qwen/Qwen3.5-4B |
| OpenAI Whisper small (via faster-whisper) | 244M | Hindi / Marathi / English speech-to-text (default, `ASR_ENGINE=whisper`) | MIT, https://huggingface.co/openai/whisper-small |
| AI4Bharat IndicConformer-600M-Multi | 600M | Hindi / Marathi speech-to-text (alternative, `ASR_ENGINE=indic`) | MIT, https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual |

No closed or proprietary AI API is used by the app. AI coding assistants were used to help write parts of this code.

## How it works
1. **Check in, check out.** At the site the worker taps one big button (काम शुरू करें · Start work). The phone takes a
   selfie and a site photo with the live camera and reads GPS; the laptop stamps the time from its own clock. The
   check-in is sealed at once. Check-out works the same way, and Python computes the hours.
2. **Voice → draft.** Speech-to-text (Hindi, Marathi or English, detected automatically) gives a transcript; Qwen fills a
   fixed JSON shape (date, start, end, site, contractor, amount paid). Plain Python compares the spoken times with the
   check-in clock: within 30 minutes shows "matches", otherwise a gentle warning, never a block. The worker checks the
   card before sealing. The claim uses the clock times; the spoken times are kept beside them.
3. **Seal.** Each entry's SHA-256 hash includes the previous entry's hash. Recordings and photos are fingerprinted too.
   Changing any saved row, recording or photo breaks the chain from that entry onward, and the Verify page shows where.
4. **Claim.** Python computes every rupee from `data/rates.json` (monthly minimum ÷ 26 per day, hours above 8 at 2×) and
   fills a fixed letter template. No AI writes any part of the claim.

## Security
- All AI runs offline on the laptop; no data leaves it and no cloud AI or API key is used. AI only turns speech into a
  form; every decision (hours, rupees, the time check, the seal) is plain, testable Python.
- Hidden phone key: registering a worker gives that phone a secret key (only its SHA-256 is stored). Check-ins and
  entries are refused without it. A second phone is linked by scanning a QR on the first, like WhatsApp Web.
- Check-in time comes from the laptop clock, not the phone. Photos come from the live camera, are checked to be real
  JPEG/PNG files, size-limited, and fingerprinted into the seal.
- Every input is validated (dates, times, amounts, lengths, file types and sizes). Everything people type is shown as
  text, never as HTML, and pages send a Content-Security-Policy and anti-framing headers.
- Known limits: GPS can be faked on a rooted phone; whoever controls the laptop could rebuild the whole chain, which is
  why the worker can send each seal off the device by WhatsApp or SMS.

## Run it
1. Install Python 3.11, FFmpeg and Ollama; `ollama pull qwen3.5:4b`
2. `python -m venv .venv` and activate it; `pip install -r requirements.txt`
3. `python -m scripts.make_icons` and, for demo data, `python -m scripts.seed demo/ramesh.csv`
4. `uvicorn app.main:app --host 0.0.0.0 --port 8000`, then open http://localhost:8000
5. Re-check any export: `python verify.py hisaab_worker_1.json`

## Wage data
Maharashtra construction minimum wages, Jan–Jun 2026, from
https://wageindicator.org/en-in/ai/work-in-india/minimum-wage/18640-maharashtra/18719-construction-of-roads-and-buildings/
Edit `data/rates.json` each half-year.

## Licence
MIT
