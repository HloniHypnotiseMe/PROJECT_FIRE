# Experiment A — WhatsApp Voice → Quote (Manual Concierge Validation)

**STATUS: NOT STARTED — no outreach sent, no prospects, no voice notes, no quotes, no payments.**
Everything below the line is a *plan and thresholds*. Nothing in this folder is a result.
Validation becomes real only when `experiment_log.md` and `prospect_tracker.csv` contain
actual, evidenced entries. Until then: verified revenue = R0.

- **Hypothesis (unproven):** Johannesburg tradespeople lose jobs and waste hours because formal
  quotes take too long. If a clean, itemised, branded PDF quote lands on their WhatsApp
  **within 5 minutes** of a voice note, they will pay a recurring price for that service.
- **The price is a hypothesis, not a fact.** R199/month is only the *first price tested* (P1).
  Fallback tiers P2/P3 exist. See *Pricing tests*.
- **Method: 100% manual concierge.** A human listens to the voice note, fills
  `quote_template.md`, and sends the PDF. Deliberately no software, no API, no AI execution
  layer — willingness to pay is being tested *before* anything is built.
- **Duration:** 14 days. Outreach on days 1–7 (10 prospects); trials run in parallel;
  convert/kill/optimize decision at day 14, on measured numbers only.
- **Market scope:** Johannesburg metro first. Trades: plumbers, electricians, solar installers,
  builders, maintenance companies.

## Target customer

One trade business, not a franchise:

- Runs jobs through WhatsApp (voice notes / DMs)
- Produces **5+ quotes per week** (below that, the pain is too small to pay for)
- Currently quotes verbally, by hand, or as messy WhatsApp text
- Owner-operator or ≤5 staff, JHB metro

Exclusions: franchises, businesses already running quoting software smoothly, anyone not
reachable on WhatsApp.

## Offer (to the prospect)

> "Send me a voice note about a job — where it is, what work, what materials. I send you a
> clean, itemised PDF quote within 5 minutes that you can forward to your client as-is.
> Free for 14 days — I'm testing the service and I need real tradespeople to tell me if
> it's worth paying for."

## Workflow (manual, per prospect)

1. Contact using `outreach.md` scripts. Log `contacted` date + script variant in
   `prospect_tracker.csv`.
2. If interested → agree 14-day free trial. Log `trial=started`.
3. Prospect sends a voice note. Save the file to
   `evidence/P<id>_request_<n>.<ext>`. Log `voice_note_received` + timestamp.
4. Listen and extract fields using the checklist in `quote_template.md` (§ Step 1).
5. Fill the template → quote. Save `evidence/P<id>_quote_<n>.pdf`. Log `quote_produced`.
6. Send via WhatsApp. Log `quote_sent` + timestamp.
   `turnaround_min = quote_sent − voice_note_received`. **Target ≤5 min; hard limit 30 min.**
7. Follow up within 24h: was the quote used? Did the client accept? Log `client_outcome`.
8. After 3–5 quotes or at day 14: offer a price (P1 → P2 → P3, see below). Log `price_offered`.
9. Payment received → save the receipt (bank/OTT/PayFast capture with reference) to
   `evidence/P<id>_payment_<timestamp>.<ext>`. Log `payment`, `revenue` (exact ZAR amount),
   `status=paying`.
10. Every event is written to `experiment_log.md` with timestamps — evidence only,
    no interpretation in the log.

## Decision criteria (measured — no judgement calls allowed)

### KILL — any one true → stop, log the reason, do not re-sell the same offer

| # | Measured condition |
|---|---|
| K1 | <5 of 10 first-touch prospects respond at all (note: fix script, run ONE additional 7-day cycle before declaring final kill) |
| K2 | <3 of 10 send at least one voice note |
| K3 | 0 payments by day 14 after trial ends, at any tested price |
| K4 | Median turnaround >30 minutes |
| K5 | Quote rejected by an end-client on quality grounds ≥2 times |

### OPTIMIZE — any one true (and no kill condition true) → one 7-day fix cycle, then re-measure

| # | Measured condition | Fix to test |
|---|---|---|
| O1 | 5–7 of 10 send voice notes but 0–1 pay | Tighten offer/price ladder; shorten trial to 7 days |
| O2 | Turnaround 5–30 min | Rebuild template; pre-fill common trade line items + rates |
| O3 | High response rate but <50% of responders send a voice note | Script/positioning problem, not demand — rewrite S1 |
| O4 | Prospects want to pay but payment fails/is friction | Fix payment rail (EFT details, PayFast link) |

### SCALE — ALL true → proceed to build (voice→quote execution layer), then next trade/city

| # | Measured condition |
|---|---|
| S1 | ≥3 paying customers by day 14 at any tested price |
| S2 | ≥60% of trialists send a 2nd voice note during trial (repeat use) |
| S3 | ≥50% of sent quotes were actually used with an end-client |
| S4 | Median turnaround ≤10 minutes |

## Pricing tests (no price is assumed correct)

| Tier | Price | Offered |
|---|---|---|
| P1 | R199/month | First offer, at trial end |
| P2 | R99/month for first 3 months | If P1 declined |
| P3 | R49 per quote (pay-as-you-go, no subscription) | If P2 declined |

Record tier + outcome per prospect in the tracker. Analysis questions: which tier converts,
effective monthly revenue per customer, and whether margin survives ~10 min manual labour
per quote at concierge scale.

## Required evidence (nothing counts without it)

Per prospect: DM conversation export (screenshots), voice note file, quote PDF,
send timestamps, client-outcome note, payment receipt with reference number.

- Location: `experiments/voice_quote/evidence/`, names `P<id>_<type>_<n>.<ext>`.
- **A revenue claim is only valid with a payment receipt in `evidence/`. No receipt = no revenue.**
- "They said they'd pay" is not revenue. "They sent a voice note" is not a customer.

## Reality gate integration

- Every produced quote (as text) and the final experiment report must be run through the
  existing Reality Engine: `python -m fire evaluate <file>` — **NO-GO means rewrite**
  (REVISE items, e.g. missing citations, are judged manually).
- The final experiment report is structured with the engine's required section names
  (opportunity ranking, evidence, economics, customer, problem, proposed solution,
  validation experiment, required agent team, execution workflow, success criteria,
  kill criteria, scale criteria) so it can be gated with the full section check.
- All results are logged to memory (`memory/events.jsonl`) as `experiment` events.
