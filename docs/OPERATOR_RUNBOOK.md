# FIRE OPERATOR RUNBOOK — Client-Ready Workflow (Phase 10)

This is the operator's operating procedure for taking a real client from first
contact to verified revenue, using only the tested FIRE CLI. No step requires
reading source code. Every command runs on the operator's machine; all client
data stays there (see Data boundary below).

**Non-negotiable invariants (enforced in code, repeated here for the operator):**

1. **No receipt = no revenue.** A payment is only recorded when the receipt
   file exists on this machine.
2. **Simulated ≠ real.** Anything recorded with `--simulated` can never enter
   verified revenue. Real client work is never marked simulated.
3. **No evidence, no delivery.** A delivery is only recorded when the evidence
   file (the produced quote) exists on this machine.
4. **Consent is never bypassed.** External steps of a growth mission refuse to
   run without the matching consent applied.
5. **Untracked stays untracked.** Criteria FIRE cannot measure are reported as
   "not tracked — manual log" — never assumed.

---

## 1. Data boundary (POPIA) — read this first

- **Versioned in the repository (public):** code, configuration, kit
  documentation, synthetic test fixtures (generated in temp dirs).
- **Never versioned (git-ignored, operator machine only):**
  - `experiments/*/evidence/` — real voice notes, quotes, client documents
  - `memory/commercial/` — real prospects, offers, transactions
  - `memory/business_profiles/` — real client business profiles
- **Experiment kit records (tracker + log) — templates vs production copies:**
  the repository keeps the header-only **templates**
  (`experiments/voice_quote/prospect_tracker.csv`,
  `experiments/voice_quote/experiment_log.md`) — **never edit them with real
  data**. On Day 0, create the **production copies** on this machine:
  ```
  cd experiments/voice_quote
  cp prospect_tracker.csv prospect_tracker.local.csv
  cp experiment_log.md experiment_log.local.md
  ```
  All real client data (names, contacts, timestamps, revenue) is written
  **only** to the `.local.` copies. They are git-ignored and cannot be
  committed. Every reference to "the tracker" or "the log" in the kit
  documents means the `.local.` production copy. (gitignore cannot protect
  tracked files — which is exactly why production data never goes into the
  tracked templates.)
- **Why:** real prospect names/contacts are personal information (POPIA) and
  payment receipts contain bank references. They must not be committable to a
  public repository.
- **Lawful basis:** contractual (the service engagement) and legitimate
  interest for initial outreach, which always states the opt-out rule.
- **Minimization:** store only what delivery and accounting require —
  business name, trade, location, one contact channel. No ID numbers, no
  unnecessary history.
- **Retention:** voice notes may be deleted after the quote is delivered and
  used, unless a payment dispute is open; receipts are kept for the tax
  period; profiles are kept while the business is a client or an active
  prospect, then archived or deleted on request.
- **Access requests / deletion:** single-operator business — the operator
  handles data-subject requests directly and records the outcome in the
  prospect notes.

**Backup procedure (weekly, ~2 minutes):** copy the two data directories to an
off-machine location (USB drive or personal private storage — never the public
repo):

```
memory/commercial/
memory/business_profiles/
experiments/voice_quote/evidence/
```

---

## 2. Consent boundary statement

The FIRE consent system (`fire growth consent`) governs **client-side mission
steps** — anything where FIRE acts on the client's behalf touching their
customers, suppliers, or money. It is the single source of truth for those
gates and nothing else may bypass it.

**Prospect outreach** (the operator contacting a potential client about FIRE's
own service) is the owner's own commercial activity: it is **operator-
attested**, not consent-gated. The operator is responsible for the opt-out
rule in `experiments/voice_quote/outreach.md` (max 2 follow-ups, stop
immediately on opt-out) and for the POPIA rules above.

---

## 3. Identity verification rule (manual, before money moves)

Before the first delivery to a new business, and before recording the first
payment, the operator verifies in person or over the phone that:

- the person they are dealing with actually runs/controls that business, and
- the payment reference comes from that business (EFT originator / PayFast
  payer matches the client).

Record the verification in the prospect `--notes` (e.g.
`"identity verified by phone 2026-09-03, owner Mokoena"`).

---

## 4. Journey 1 — first paid engagement (FIRE sells its service)

The 14-day voice→quote trial for a tradesperson. All [CLI] commands use the
real business details; never `--simulated` for real clients.

1. **Intake.** Qualify per `experiments/voice_quote/outreach.md`. Then:
   ```
   fire commercial prospect add --business "Mokoena Plumbing" \
     --trade Plumber --location Johannesburg \
     --contact "+27 82 000 0000" --notes "qualified 2026-09-01, 2 follow-ups OK"
   ```
2. **Offer (record the trial terms — always use `--terms` for the trial):**
   ```
   fire commercial offer create --opportunity opp-wa-voice-quote \
     --tiers "P1=199/mo,P2=99/mo,P3=49/quote" \
     --unit "1 itemised PDF quote (concierge)" \
     --outcome "quote within 5 minutes of voice note" \
     --terms "14-day free trial: 2 quotes, 1 follow-up, then P1/P2/P3"
   ```
3. **Trial.** `fire commercial trial start --prospect <pr-…> --offer <of-…>`
4. **Evidence + delivery.** Save the client's voice note to
   `experiments/voice_quote/evidence/`. Produce the quote from
   `quote_template.md`, save the produced file, then:
   ```
   fire commercial delivery record --engagement <en-…> --quote-n 1 \
     --requested-at "<ISO time received>" --delivered-at "<ISO time sent>" \
     --evidence "<path to produced quote file>" --used
   ```
   (omit `--used` until the client actually uses the quote; record usage when
   you learn of it with a second record or follow-up note).
5. **Price.** `fire commercial price offer --engagement <en-…> --tier P1`
6. **Payment (after client pays).** Save the receipt **locally** (in
   `evidence/`), then:
   ```
   fire commercial payment record --prospect <pr-…> --amount 199 \
     --period month --receipt "<local receipt path>" \
     --payment-ref "<reference number on the receipt>"
   ```
   **Acceptance rule:** client acceptance of the offer = the recorded price
   offer **plus** the client-initiated payment with receipt. Both are
   persisted and audited (`cv_price_offered`, `cv_payment_collected`).
7. **Verify.** `fire commercial revenue` — the first real R appears under
   **VERIFIED REVENUE** (never under SIMULATED, never under MODEL).
8. **Decide.** Day 14: `fire commercial decide --experiment voice-quote` →
   KILL / OPTIMIZE / SCALE on recorded numbers; the lesson is recorded
   automatically and feeds the next cycle.

If the same business also runs a growth mission, cross-reference once:
`fire commercial prospect add … --profile-slug <slug>` (re-adding updates the
record) and `fire growth profile --name … --sector … --prospect-id <pr-…>`.

---

## 5. Journey 2 — client business growth engagement

1. **Intake (onboarding conversation):**
   ```
   fire growth profile --name "Mokoena Plumbing" --sector Plumbing \
     --location Johannesburg --services "pipe repairs, geyser installs" \
     --owner-consent --metrics <metrics.json> --prospect-id <pr-…>
   ```
2. **Diagnose:** `fire growth diagnose --profile <slug>` (shows PRIOR LESSONS).
3. **Mission:** `fire growth mission --profile <slug>`.
4. **Authorize (consent — only the gates the mission actually needs):**
   `fire growth consent <gm-…> --owner --customer-contact …`
5. **Execute step by step:** `fire growth run <gm-…> --result "<operator-
   attested outcome>" --evidence "<file>"` — steps that lack consent refuse to
   run; failures are retryable; the mission resumes from persisted state.
6. **Measure:** `fire growth measure <gm-…> --metric monthly_leads --value …`
7. **Decide:** `fire growth decide <gm-…>` → SCALE / OPTIMIZE / KILL.
8. **Report:** `fire growth report <gm-…>` — quality-gated; share with the
   client. For Client #1 the full report is shareable as-is.
9. **Learn:** `fire growth learn <gm-…>` → the lesson is retrieved into the
   next `diagnose`/`mission` for this business automatically.

---

## 6. Launch checklist (run before taking any real client)

- [ ] Repository at the approved commit; `python -m pytest -q` green
- [ ] `git check-ignore experiments/voice_quote/evidence/test.png` → exit 0
      (and same for `memory/commercial/`, `memory/business_profiles/`)
- [ ] Production copies created: `prospect_tracker.local.csv` +
      `experiment_log.local.md` (git-ignored; the tracked templates stay
      pristine — real data only ever goes into the `.local.` copies)
- [ ] Weekly backup of the data directories set up (calendar reminder)
- [ ] Receipt storage location agreed (`experiments/voice_quote/evidence/`)
- [ ] EFT/PayFast destination account ready; reference-number convention agreed
- [ ] Outreach script reviewed (opt-out rule present)
- [ ] This runbook read

---

## 7. What stays manual (by design, pre-scale)

All external contact, voice-note→quote production, follow-ups, payment
collection, metric entry, and backups are **operator work**. FIRE records,
validates, measures and learns; the operator acts in the world. Nothing on
this list is a defect — it is the concierge business model until a measured
SCALE decision says otherwise.
