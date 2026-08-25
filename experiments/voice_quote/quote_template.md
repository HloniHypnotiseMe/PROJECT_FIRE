# Quote Template — Voice→Quote Concierge

Usage: copy into a plain document (Google Docs is fine), fill from the voice note,
export as PDF, name it `P<id>_quote_<n>.pdf`, send on WhatsApp.
**Target: filled and sent ≤5 minutes after receiving the voice note.**

## Step 1 — Extract from the voice note

Write down what was actually said. If a field is missing, write `TBC`.
Ask ONE short follow-up only for essentials: what the work is, where, materials.
Do not ask more than that.

| Field | Heard |
|---|---|
| End-client name / how to address | |
| Job location / suburb | |
| Job type (e.g. install geyser, rewire kitchen, leak repair) | |
| Scope — what is included | |
| What is NOT included (if mentioned) | |
| Materials: item, qty, brand (if named) | |
| Labour: expected duration (hours / days) | |
| Urgency / desired start date | |
| Access constraints (gates, parking, hours) | |
| Pre-existing damage or conditions mentioned | |

## Step 2 — The quote

```
QUOTE No. [Q-YYYY-NNN]          Date: [DD MMM YYYY]

FROM
[Trade business name]
[Phone / WhatsApp] · [City, suburb]

TO
[Client name]
[Job address]

RE: [Job type] — [Location]

#  DESCRIPTION                                   QTY   RATE (R)   TOTAL (R)
1  Labour: [e.g. supply & install 50L geyser]        1         —          —
2  Material: [e.g. 50L geyser, brand if named]       1              —
3  Material: [e.g. new element, isolation valve]     1              —
4  Call-out / travel ([suburb])                       1              —
5  Labour: [second day / follow-up visit, if any]     —              —

TOTAL (R)                                              [amount]
VAT: [0% — not VAT registered]   (or state "Prices exclude VAT" / include it if registered)

TERMS
- Quote valid for 14 days from date above.
- [50% deposit on acceptance; balance on completion]  (adjust to the trade's norm)
- Workmanship guaranteed for [trade's standard: 30 / 90 / 365 days].
- Excludes: [anything TBC or out of scope].

ACCEPTANCE
Reply "ACCEPT" on WhatsApp, or sign below.
Client: ____________________  Date: ________
```

## Step 3 — Before sending (reality check, 60 seconds)

1. **Every number has a source** — the voice note, an agreed rate, or it is marked `TBC`.
   No invented prices, no invented materials.
2. **No guarantee claims** — never "guaranteed price", "100%", "no risk". Run
   `python -m fire evaluate <quote-as-text.txt>`; **NO-GO = rewrite before sending.**
3. Save the PDF to `evidence/` **before** sending.
4. Log in the tracker: `quote_produced`, `quote_sent`, `turnaround_min`.

## Defaults (only when the voice note is silent AND no follow-up was possible)

- Call-out line: include only if the trade business normally charges one — never invent it.
- Rates: use the business's own standard if stated in the conversation. Otherwise quote
  materials + `Labour: TBC` and ask one follow-up. **A quote with one TBC line beats a
  quote with invented numbers.**
- Warranty: use the trade's stated norm; if unknown, write "guarantee as per trade standard".
