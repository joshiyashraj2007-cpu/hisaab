"""Claim letter: a fixed template filled in by code. No AI writes any part of it, so every word
and every rupee can be traced to a line of Python."""


def template(worker, claim):
    photos = f", {claim['photo_days']} of them with photos" if claim.get("photo_days") else ""
    proof = (f" {claim['verified_days']} of these days are confirmed by check-in and check-out records "
             f"timed by the Hisaab device clock{photos}." if claim.get("verified_days") else "")
    return (f"To the Authority appointed under Section 45 of the Code on Wages, 2019. "
            f"I, {worker['name']}, worked for {claim['contractor'] or 'the contractor named in the attached record'} "
            f"at {claim['site'] or 'the site in the attached record'} from {claim['period_from']} to {claim['period_to']}, "
            f"for {claim['days']} recorded days. I was paid Rs {claim['paid']:,}, while Rs {claim['due']:,} was due "
            f"at the notified minimum rate including overtime. I request recovery of the shortfall of "
            f"Rs {claim['shortfall']:,}.{proof} My day-by-day record, sealed with SHA-256 hashes, is attached.")
