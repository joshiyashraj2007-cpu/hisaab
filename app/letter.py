"""Claim letter: Qwen writes the words, code owns the numbers."""
import os
import re

from .extract import KEEP, MODEL

# Optional: use a bigger model only for the once-a-month letter (needs 16 GB RAM).
LETTER_MODEL = os.environ.get("HISAAB_LETTER_MODEL", MODEL)
LETTER_TIMEOUT = float(os.environ.get("HISAAB_LETTER_TIMEOUT", "120"))   # seconds

LETTER_4B = ("Write a short, formal wage claim letter (under 140 words) in plain English, first person, "
             "addressed to 'The Authority appointed under Section 45 of the Code on Wages, 2019'. "
             "Use ONLY the facts given. Copy every number exactly as written. Do not add any other number, "
             "date, law or promise. No placeholders, no signature block.")
LETTER_9B = (LETTER_4B + " Write exactly four sentences and do not number them: who I am, where and for whom "
             "I worked, and the period; how many days I worked, what I was paid and what was due at the "
             "notified minimum rate; a request to recover the shortfall under Section 45; that my day-by-day "
             "record, sealed with SHA-256 hashes, is attached. Respectful and firm, no emotional language.")


def letter_prompt():
    return LETTER_9B if "9b" in LETTER_MODEL.lower() else LETTER_4B


NUM = re.compile(r"\d[\d,]*\.?\d*")


def numbers_in(text):
    out = set()
    for raw in NUM.findall(text):
        try:
            out.add(float(raw.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def numbers_ok(letter, facts):
    # Every number in the letter must already appear in the facts we computed.
    allowed = numbers_in(facts) | {45.0, 2019.0}
    return numbers_in(letter) <= allowed


def facts_text(worker, claim, rates_source):
    return (f"Worker: {worker['name']}. Phone: {worker['phone'] or 'not given'}. "
            f"Employer/contractor: {claim['contractor'] or 'as recorded'}. Site: {claim['site'] or 'as recorded'}. "
            f"Period: {claim['period_from']} to {claim['period_to']}. Days recorded: {claim['days']}. "
            f"Minimum daily rate applied: Rs {claim['day_rate']:,.2f} ({rates_source}). "
            f"Total due: Rs {claim['due']:,}. Total paid: Rs {claim['paid']:,}. "
            f"Overtime due included: Rs {claim['overtime_due']:,}. Shortfall claimed: Rs {claim['shortfall']:,}. "
            f"Records sealed with SHA-256; latest seal {claim['head'][:16]}.")


def template(worker, claim):
    return (f"To the Authority appointed under Section 45 of the Code on Wages, 2019. "
            f"I, {worker['name']}, worked for {claim['contractor'] or 'the contractor named in the attached record'} "
            f"at {claim['site'] or 'the site in the attached record'} from {claim['period_from']} to {claim['period_to']}, "
            f"for {claim['days']} recorded days. I was paid Rs {claim['paid']:,}, while Rs {claim['due']:,} was due "
            f"at the notified minimum rate including overtime. I request recovery of the shortfall of "
            f"Rs {claim['shortfall']:,}. My day-by-day record, sealed with SHA-256 hashes, is attached.")


def write_letter(worker, claim, rates_source):
    facts = facts_text(worker, claim, rates_source)
    try:
        import ollama
        # think=False: Qwen3.5 otherwise "thinks" for 1,500+ tokens first (10+ minutes on CPU).
        # timeout: if Qwen is still slow, fall back to the template instead of hanging the claim page.
        r = ollama.Client(timeout=LETTER_TIMEOUT).chat(
            model=LETTER_MODEL,
            messages=[{"role": "system", "content": letter_prompt()},
                      {"role": "user", "content": facts}],
            options={"temperature": 0.2, "num_predict": 400},
            think=False,
            keep_alive=KEEP)
        text = r["message"]["content"].strip()
        if text and numbers_ok(text, facts):
            return text, "ai"
    except Exception:
        pass
    return template(worker, claim), "template"