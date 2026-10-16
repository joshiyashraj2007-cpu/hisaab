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
| Qwen3.5-4B (via Ollama, `qwen3.5:4b`) | 4B (Hugging Face lists 5B in total) | Transcript → structured record, claim letter | Apache-2.0, https://huggingface.co/Qwen/Qwen3.5-4B |
| OpenAI Whisper small (via faster-whisper) | 244M | Hindi / Marathi speech-to-text (default, `ASR_ENGINE=whisper`) | MIT, https://huggingface.co/openai/whisper-small |
| AI4Bharat IndicConformer-600M-Multi | 600M | Hindi / Marathi speech-to-text (alternative, `ASR_ENGINE=indic`) | MIT, https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual |

No closed or proprietary AI API is used by the app. AI coding assistants were used to help write parts of this code.

## How it works
1. **Voice → draft.** Speech-to-text gives a transcript; Qwen fills a fixed JSON shape (date, start, end, site, contractor, amount paid).
   The worker checks the draft card and corrects anything before sealing.
2. **Seal.** Each entry's SHA-256 hash includes the previous entry's hash, and the original recording is fingerprinted too.
   Changing any saved row or recording breaks the chain from that entry onward, and the Verify page shows where.
3. **Claim.** Python computes every rupee from `data/rates.json` (monthly minimum ÷ 26 per day, hours above 8 at 2×).
   Qwen only writes the words of the letter; if the letter contains any number the code did not compute, a fixed template is used instead.

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
