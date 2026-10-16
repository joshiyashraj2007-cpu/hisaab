"""Transcript -> structured draft, using Qwen through Ollama with a forced JSON schema."""
import os
from typing import List, Optional

from pydantic import BaseModel

MODEL = os.environ.get("HISAAB_MODEL", "qwen3.5:4b")
KEEP = "60m"   # keep the model in RAM so every note is fast


class Draft(BaseModel):
    work_date: Optional[str] = None      # YYYY-MM-DD
    start_time: Optional[str] = None     # HH:MM, 24-hour
    end_time: Optional[str] = None
    site: Optional[str] = None
    contractor: Optional[str] = None
    amount_paid: Optional[float] = None
    missing: List[str] = []


SYSTEM = SYSTEM_4B = """You convert a construction worker's voice note (Hindi, Marathi or Hinglish, informal, may have
speech-recognition mistakes) into JSON with the fields of the schema.
Today's date is {today}. "aaj" = today. "kal" / "kaal" here means YESTERDAY (he logs past work).
Use 24-hour HH:MM. "subah 8" = 08:00, "dopahar 2" = 14:00, "shaam 7" = 19:00, "raat 9" = 21:00,
"saade aath" = 08:30, "sava nau" = 09:15, "paune chhe" = 05:45, "dedh" = 1:30, "dhai" = 2:30.
Money words: "sau" = 100, "chaar sau pachaas" = 450, "paanch sau" = 500, "hazaar" = 1000.
If the note says nothing was paid ("kuch nahi mila", "paise nahi diye"), amount_paid = 0.
If a field is not said, use null and add the field name to "missing". Never guess a number.

Examples:
Note: "aaj subah aath se shaam chhe baje tak garkheda site pe kaam kiya, chaar sau rupaye mile"
JSON: {{"work_date":"{today}","start_time":"08:00","end_time":"18:00","site":"Garkheda","contractor":null,"amount_paid":400,"missing":["contractor"]}}
Note: "kal saade nau se raat aath baje tak sharma thekedar ke yahan, paise nahi diye"
JSON: {{"work_date":"{yesterday}","start_time":"09:30","end_time":"20:00","site":null,"contractor":"Sharma","amount_paid":0,"missing":["site"]}}
Note: "आज सकाळी आठ ते संध्याकाळी सहा वाजेपर्यंत वाळूज साइटवर काम केलं, पाचशे रुपये मिळाले"
JSON: {{"work_date":"{today}","start_time":"08:00","end_time":"18:00","site":"Waluj","contractor":null,"amount_paid":500,"missing":["contractor"]}}
Note: "today 8 to 6 work kiya Chikalthana site, Patil contractor, 600 diye"
JSON: {{"work_date":"{today}","start_time":"08:00","end_time":"18:00","site":"Chikalthana","contractor":"Patil","amount_paid":600,"missing":[]}}
"""

SYSTEM_9B = """Extract one workday from a construction worker's informal voice note (Hindi, Marathi or Hinglish;
the transcript may contain recognition errors). Today is {today}; "aaj" means today, "kal"/"kaal" means
yesterday ({yesterday}) because workers log past work. Times are 24-hour HH:MM; convert spoken Hindi and
Marathi time and number words (saade = +30 min, sava = +15, paune = -15, sau = 100, hazaar = 1000).
"Nothing paid" means amount_paid = 0. Any field not stated is null and listed in "missing"; never guess.
Example: "kal saade nau se raat aath baje tak sharma thekedar ke yahan, paise nahi diye" ->
{{"work_date":"{yesterday}","start_time":"09:30","end_time":"20:00","site":null,"contractor":"Sharma","amount_paid":0,"missing":["site"]}}
"""

# 9B needs fewer examples, and every prompt token costs it about twice as much time on a CPU.
SYSTEM = SYSTEM_9B if "9b" in MODEL else SYSTEM_4B


def extract(transcript, today, yesterday):
    import ollama
    r = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM.format(today=today, yesterday=yesterday)},
                  {"role": "user", "content": transcript}],
        format=Draft.model_json_schema(),
        options={"temperature": 0, "num_predict": 256},
        think=False,
        keep_alive=KEEP)
    return Draft.model_validate_json(r["message"]["content"])


def safe_extract(transcript, today, yesterday):
    """Never crash the request: one retry, then an empty draft the worker fills by hand."""
    for _ in range(2):
        try:
            return extract(transcript, today, yesterday), None
        except Exception as err:          # model down, bad JSON, timeout
            last = str(err)
    d = Draft(work_date=today, missing=["start_time", "end_time", "site", "contractor", "amount_paid"])
    return d, last


def warmup():
    try:
        import ollama
        ollama.chat(model=MODEL, messages=[{"role": "user", "content": "ok"}],
                    options={"num_predict": 1}, keep_alive=KEEP)
        return True
    except Exception:
        return False