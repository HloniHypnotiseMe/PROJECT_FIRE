"""FIRE Revenue Validation Engine.

Phase 9 closes the commercial loop:

    PROSPECT -> QUALIFY -> OFFER -> TRIAL -> DELIVER -> PRICE
        -> PAYMENT -> VERIFIED REVENUE -> EXPERIMENT DECISION -> LESSON

Existing owners reused (no duplicate concepts introduced):

- fire.memory.EventLog            — the single audit event stream (cv_* events)
- memory/commercial/...           — same one-JSON-per-object + atomic-write
  convention as memory/growth_missions/
- fire.opportunity.Opportunity    — offer definitions are REFERENCED by id,
  never re-modelled; hypothetical economics stay hypothesis-labelled
- fire.growth.learning            — commercial experiment decisions become
  GrowthLessons (lever="revenue") through the existing lesson store/events

The revenue rule (the invariant of this phase):

    VERIFIED REVENUE = collected AND receipt exists AND simulated == false

Everything else is labelled MODEL (hypotheses), SIMULATED, QUOTED, INVOICED
or COLLECTED-unverified — never silently treated as revenue.

    No receipt = no revenue.  Simulated != real.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fire.config import load_config, paths
from fire.growth.learning import GrowthLesson, lesson_id_for
from fire.memory import EventLog

# ---------------------------------------------------------------------------
# enums-as-constants (kept as plain strings: JSON-friendly, CLI-friendly)
# ---------------------------------------------------------------------------

PROSPECT_STATUSES = [
    "IDENTIFIED", "CONTACTED", "RESPONDED", "TRIAL", "OFFERED", "PAYING",
    "NO_RESPONSE", "REJECTED", "CHURNED",
]
_TRIAL_OR_LATER = {"TRIAL", "OFFERED", "PAYING"}

TRANSACTION_STAGES = ["QUOTED", "INVOICED", "COLLECTED"]
TRANSACTION_KINDS = ["SUBSCRIPTION", "ONE_OFF", "REFUND"]

DECISION_KILL = "KILL"
DECISION_OPTIMIZE = "OPTIMIZE"
DECISION_SCALE = "SCALE"
DECISION_INCONCLUSIVE = "INCONCLUSIVE"

_PERIOD_SUFFIXES = {"mo": "month", "month": "month", "quote": "one-off",
                    "one-off": "one-off", "year": "year", "once": "one-off"}


class CommercialError(Exception):
    """Raised when a commercial action violates the evidence rules."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _det_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

@dataclass
class Prospect:
    """One real (or explicitly simulated) prospect business.

    No customer data is invented: every field is operator-supplied.
    """

    prospect_id: str
    business: str
    trade: str
    location: str = ""
    notes: str = ""
    qualification: dict = field(default_factory=dict)
    simulated: bool = False
    status: str = "IDENTIFIED"
    created_at: str = ""
    updated_at: str = ""
    # Phase 10 (client-ready): operator-supplied contact channel and the
    # optional cross-reference to the growth profile for the same business.
    contact: str = ""
    profile_slug: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Prospect":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def prospect_id_for(business: str, trade: str, location: str) -> str:
    return _det_id("pr", {"business": business.strip().lower(),
                          "trade": trade.strip().lower(),
                          "location": location.strip().lower()})


@dataclass
class PriceTier:
    """A price tier is a HYPOTHESIS until it is actually paid."""

    tier: str
    price: float
    period: str            # month / one-off / year
    terms: str = ""


@dataclass
class Offer:
    """What FIRE sells: a reference to an EXISTING Opportunity plus the
    unit of delivery, promised measurable outcome and price tiers."""

    offer_id: str
    opportunity_id: str
    opportunity_name: str
    unit_of_delivery: str
    promised_outcome: str
    price_tiers: list[PriceTier] = field(default_factory=list)
    terms: str = ""
    simulated: bool = False
    created_at: str = ""

    def tier(self, name: str) -> PriceTier | None:
        return next((t for t in self.price_tiers if t.tier == name), None)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Offer":
        data = dict(data)
        data["price_tiers"] = [PriceTier(**t) for t in data.get("price_tiers", [])]
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class Delivery:
    """One delivered unit (e.g. one concierge quote). Turnaround is
    COMPUTED from recorded timestamps; the evidence file must exist."""

    quote_n: int
    requested_at: str
    delivered_at: str
    turnaround_min: float
    used_by_client: bool
    evidence_path: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Engagement:
    """A trial/service engagement for one prospect under one offer."""

    engagement_id: str
    prospect_id: str
    offer_id: str
    mission_id: str | None = None          # optional attribution to a growth mission
    deliveries: list[Delivery] = field(default_factory=list)
    simulated: bool = False
    started_at: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Engagement":
        data = dict(data)
        data["deliveries"] = [Delivery(**d) for d in data.get("deliveries", [])]
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class Transaction:
    """A commercial transaction with explicit stages.

    INVARIANT: a transaction counts as VERIFIED REVENUE only when
    stage == COLLECTED AND the receipt file exists AND simulated is False.
    """

    transaction_id: str
    prospect_id: str
    engagement_id: str
    offer_id: str
    amount: float
    currency: str = "ZAR"
    period: str = "month"                   # month / one-off / year
    kind: str = "SUBSCRIPTION"              # SUBSCRIPTION / ONE_OFF / REFUND
    stage: str = "QUOTED"                   # QUOTED / INVOICED / COLLECTED
    receipt_path: str = ""
    payment_ref: str = ""
    delivery_cost: float = 0.0
    simulated: bool = False
    created_at: str = ""
    updated_at: str = ""
    collected_at: str | None = None

    @property
    def verified(self) -> bool:
        """The revenue rule: collected AND receipt exists AND not simulated."""
        if self.stage != "COLLECTED" or self.simulated:
            return False
        return bool(self.receipt_path) and Path(self.receipt_path).exists()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class ExperimentDecision:
    """A KILL/OPTIMIZE/SCALE decision COMPUTED from recorded numbers.
    No LLM, no subjective interpretation; untracked criteria are reported
    as such, never assumed."""

    decision_id: str
    experiment: str
    decision: str
    numbers: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    decided_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentDecision":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


# ---------------------------------------------------------------------------
# Experiment A criteria (experiments/voice_quote/README.md) — measured only.
# Each check returns (met | None=not tracked in engine, detail).
# K5 (quality rejections) and O4 (payment friction) are manual-log criteria
# and are reported as not tracked, never assumed.
# ---------------------------------------------------------------------------

def _experiment_conditions(n: dict) -> dict:
    med = n.get("median_turnaround_min")
    responded, notes = n["responded"], n["voice_notes"]
    second, paying = n["second_voice_notes"], n["paying_customers"]
    payments, used_pct = n["payments"], n["quotes_used_pct"]

    def ratio(a, b):
        return (a / b) if b else 0.0

    k1 = responded < 5
    k2 = notes < 3
    k3 = payments == 0
    k4 = med is not None and med > 30
    o1 = 5 <= notes <= 7 and payments <= 1
    o2 = med is not None and 5 <= med <= 30
    o3 = responded > 0 and ratio(notes, responded) < 0.50
    s1 = paying >= 3
    s2 = notes > 0 and ratio(second, notes) >= 0.60
    s3 = n["deliveries"] > 0 and used_pct is not None and used_pct >= 0.50
    s4 = med is not None and med <= 10

    def c(met: bool | None, detail: str):
        return {"met": met, "detail": detail}

    return {
        "K1": c(k1, f"responded {responded} (<5 -> kill)"),
        "K2": c(k2, f"voice notes (>=1 delivery) {notes} (<3 -> kill)"),
        "K3": c(k3, f"payments {payments} (0 -> kill)"),
        "K4": c(k4, f"median turnaround {med} min (>30 -> kill)" if med is not None
                else "no deliveries recorded"),
        "K5": c(None, "not tracked in engine — quality rejections are manual-log "
                      "criteria (experiment_log.md)"),
        "O1": c(o1, f"voice notes {notes}, payments {payments}"),
        "O2": c(o2, f"median turnaround {med} min" if med is not None else
                "no deliveries recorded"),
        "O3": c(o3, f"voice-note rate of responders {ratio(notes, responded):.0%}"),
        "O4": c(None, "not tracked in engine — payment friction is a manual-log "
                      "criterion (experiment_log.md)"),
        "S1": c(s1, f"paying customers {paying} (>=3 required)"),
        "S2": c(s2, f"repeat voice-note rate {ratio(second, notes):.0%} (>=60% required)"),
        "S3": c(s3, f"quotes used by end-client {used_pct:.0%} (>=50% required)"
                    if used_pct is not None else "no deliveries recorded"),
        "S4": c(s4, f"median turnaround {med} min (<=10 required)" if med is not None
                else "no deliveries recorded"),
    }


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

class CommercialEngine:
    """Evidence-bounded recording of commercial activity + verified revenue."""

    def __init__(self, memory_dir: str | Path | None = None):
        if memory_dir is not None:
            mem = Path(memory_dir)
        else:
            mem = paths(load_config())["memory_dir"]
        self.memory_dir = mem
        self.base = mem / "commercial"
        for sub in ("prospects", "offers", "engagements", "transactions",
                    "decisions"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)
        self.events = EventLog(mem)
        # learning bridge (existing Phase 8 store + events, no second system)
        from fire.growth.learning import GrowthLearningEngine
        self.learner = GrowthLearningEngine(mem)

    # -- persistence ---------------------------------------------------------
    def _path(self, sub: str, obj_id: str) -> Path:
        return self.base / sub / f"{obj_id}.json"

    @staticmethod
    def _save(path: Path, data: dict) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _load(path: Path, cls, obj_name: str):
        if not path.exists():
            raise CommercialError(f"unknown {obj_name}")
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # -- prospects -------------------------------------------------------------
    def add_prospect(self, business: str, trade: str, location: str = "",
                     notes: str = "", qualification: dict | None = None,
                     simulated: bool = False, contact: str = "",
                     profile_slug: str = "") -> Prospect:
        if not business or not trade:
            raise CommercialError("business and trade are required")
        pid = prospect_id_for(business, trade, location)
        path = self._path("prospects", pid)
        if path.exists():
            p = self._load(path, Prospect, "prospect")
            p.updated_at = _now()
            if notes:
                p.notes = notes
            if qualification:
                p.qualification.update(qualification)
            if contact:
                p.contact = contact
            if profile_slug:
                p.profile_slug = profile_slug
            self._save(path, p.to_dict())
            return p
        p = Prospect(
            prospect_id=pid, business=business, trade=trade, location=location,
            notes=notes, qualification=dict(qualification or {}),
            simulated=simulated, status="IDENTIFIED",
            created_at=_now(), updated_at=_now(),
            contact=contact, profile_slug=profile_slug,
        )
        self._save(path, p.to_dict())
        self.events.append(
            "cv_prospect_created",
            {"prospect_id": pid, "business": business,
             "simulated": simulated, "status": p.status},
        )
        return p

    def get_prospect(self, pid: str) -> Prospect:
        return self._load(self._path("prospects", pid), Prospect,
                          f"prospect {pid}")

    def list_prospects(self) -> list[Prospect]:
        out = [self._load(p, Prospect, "prospect")
               for p in sorted((self.base / "prospects").glob("*.json"))]
        return sorted(out, key=lambda p: (p.business, p.prospect_id))

    def set_prospect_status(self, pid: str, status: str) -> Prospect:
        if status not in PROSPECT_STATUSES:
            raise CommercialError(
                f"invalid status {status!r} (allowed: {', '.join(PROSPECT_STATUSES)})")
        p = self.get_prospect(pid)
        old = p.status
        p.status = status
        p.updated_at = _now()
        self._save(self._path("prospects", pid), p.to_dict())
        self.events.append("cv_prospect_status_changed",
                           {"prospect_id": pid, "from": old, "to": status})
        return p

    # -- offers ----------------------------------------------------------------
    def create_offer(self, opportunity_id: str, tiers: list[PriceTier],
                     unit_of_delivery: str = "", promised_outcome: str = "",
                     terms: str = "", simulated: bool = False) -> Offer:
        from fire.opportunity import run_hunt
        opp = next((o for o in run_hunt() if o.id == opportunity_id), None)
        if opp is None:
            raise CommercialError(
                f"unknown opportunity {opportunity_id!r} — offers reference "
                f"existing opportunities and are never re-modelled")
        if not tiers:
            raise CommercialError("at least one price tier is required")
        oid = _det_id("of", {
            "opportunity": opportunity_id, "unit": unit_of_delivery,
            "outcome": promised_outcome,
            "tiers": sorted((t.tier, t.price, t.period, t.terms)
                            for t in tiers),
        })
        path = self._path("offers", oid)
        if path.exists():
            return self._load(path, Offer, "offer")
        offer = Offer(
            offer_id=oid, opportunity_id=opportunity_id,
            opportunity_name=opp.name, unit_of_delivery=unit_of_delivery,
            promised_outcome=promised_outcome, price_tiers=list(tiers),
            terms=terms, simulated=simulated, created_at=_now(),
        )
        self._save(path, offer.to_dict())
        self.events.append(
            "cv_offer_created",
            {"offer_id": oid, "opportunity_id": opportunity_id,
             "tiers": [t.tier for t in tiers], "simulated": simulated,
             "note": "price tiers are hypotheses until actually paid"},
        )
        return offer

    def get_offer(self, oid: str) -> Offer:
        return self._load(self._path("offers", oid), Offer, f"offer {oid}")

    def list_offers(self) -> list[Offer]:
        return [self._load(p, Offer, "offer")
                for p in sorted((self.base / "offers").glob("*.json"))]

    # -- engagements (trials) ------------------------------------------------------
    def start_trial(self, prospect_id: str, offer_id: str | None = None,
                    mission_id: str | None = None) -> Engagement:
        p = self.get_prospect(prospect_id)
        if offer_id is None:
            offers = self.list_offers()
            if len(offers) != 1:
                raise CommercialError(
                    "no --offer given and more than one offer exists; "
                    "specify the offer explicitly")
            offer_id = offers[0].offer_id
        offer = self.get_offer(offer_id)
        eid = _det_id("en", {"prospect": prospect_id, "offer": offer_id})
        path = self._path("engagements", eid)
        if path.exists():
            return self._load(path, Engagement, "engagement")
        if p.status == "IDENTIFIED":
            p = self.set_prospect_status(prospect_id, "CONTACTED")
        p = self.set_prospect_status(prospect_id, "TRIAL")
        eng = Engagement(
            engagement_id=eid, prospect_id=prospect_id, offer_id=offer_id,
            mission_id=mission_id,
            simulated=bool(p.simulated or offer.simulated),
            started_at=_now(),
        )
        self._save(path, eng.to_dict())
        self.events.append(
            "cv_engagement_started",
            {"engagement_id": eid, "prospect_id": prospect_id,
             "offer_id": offer_id, "mission_id": mission_id,
             "simulated": eng.simulated},
        )
        return eng

    def get_engagement(self, eid: str) -> Engagement:
        return self._load(self._path("engagements", eid), Engagement,
                          f"engagement {eid}")

    def list_engagements(self) -> list[Engagement]:
        return [self._load(p, Engagement, "engagement")
                for p in sorted((self.base / "engagements").glob("*.json"))]

    def _engagements_for(self, prospect_id: str) -> list[Engagement]:
        return [e for e in self.list_engagements() if e.prospect_id == prospect_id]

    # -- deliveries ------------------------------------------------------------------
    @staticmethod
    def _parse_ts(value: str, what: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise CommercialError(
                f"invalid ISO timestamp for {what}: {value!r}") from exc

    def record_delivery(self, engagement_id: str, quote_n: int,
                        requested_at: str, delivered_at: str,
                        evidence_path: str,
                        used_by_client: bool = False) -> Delivery:
        eng = self.get_engagement(engagement_id)   # no engagement -> no delivery
        p = self.get_prospect(eng.prospect_id)
        if p.status not in _TRIAL_OR_LATER:
            raise CommercialError(
                f"prospect {p.prospect_id} is {p.status}; a delivery requires "
                f"a started trial (TRIAL/OFFERED/PAYING)")
        if not evidence_path or not Path(evidence_path).exists():
            raise CommercialError(
                f"evidence file does not exist: {evidence_path!r} — "
                f"no evidence, no delivery record")
        req = self._parse_ts(requested_at, "requested_at")
        deli = self._parse_ts(delivered_at, "delivered_at")
        turnaround = (deli - req).total_seconds() / 60.0
        if turnaround < 0:
            raise CommercialError(
                "delivered_at is before requested_at — turnaround cannot be negative")
        d = Delivery(
            quote_n=quote_n, requested_at=requested_at, delivered_at=delivered_at,
            turnaround_min=round(turnaround, 2), used_by_client=used_by_client,
            evidence_path=str(evidence_path),
        )
        eng.deliveries.append(d)
        self._save(self._path("engagements", engagement_id), eng.to_dict())
        self.events.append(
            "cv_delivery_recorded",
            {"engagement_id": engagement_id, "quote_n": quote_n,
             "turnaround_min": d.turnaround_min, "used_by_client": used_by_client,
             "evidence": d.evidence_path},
        )
        return d

    # -- pricing -----------------------------------------------------------------------
    def offer_price(self, engagement_id: str, tier_name: str) -> tuple[Engagement, PriceTier]:
        eng = self.get_engagement(engagement_id)
        offer = self.get_offer(eng.offer_id)
        tier = offer.tier(tier_name)
        if tier is None:
            known = ", ".join(t.tier for t in offer.price_tiers)
            raise CommercialError(
                f"unknown tier {tier_name!r} for offer {offer.offer_id} "
                f"(known: {known})")
        p = self.get_prospect(eng.prospect_id)
        if p.status not in _TRIAL_OR_LATER:
            raise CommercialError(
                f"prospect {p.prospect_id} is {p.status}; pricing requires a trial")
        self.set_prospect_status(eng.prospect_id, "OFFERED")
        self.events.append(
            "cv_price_offered",
            {"engagement_id": engagement_id, "prospect_id": eng.prospect_id,
             "tier": tier.tier, "price": tier.price, "period": tier.period,
             "note": "price is a hypothesis until paid"},
        )
        return eng, tier

    # -- transactions / revenue ------------------------------------------------------------
    def create_transaction(self, prospect_id: str, engagement_id: str,
                           offer_id: str, amount: float, currency: str = "ZAR",
                           period: str = "month", kind: str = "SUBSCRIPTION",
                           stage: str = "QUOTED", delivery_cost: float = 0.0,
                           simulated: bool | None = None,
                           payment_ref: str = "") -> Transaction:
        if kind not in TRANSACTION_KINDS:
            raise CommercialError(f"invalid kind {kind!r} (allowed: {TRANSACTION_KINDS})")
        if stage not in TRANSACTION_STAGES:
            raise CommercialError(
                f"invalid stage {stage!r} (allowed: {TRANSACTION_STAGES})")
        if amount <= 0:
            raise CommercialError("amount must be > 0 (use kind=REFUND for refunds)")
        p = self.get_prospect(prospect_id)
        eng = self.get_engagement(engagement_id)
        self.get_offer(offer_id)
        if simulated is None:
            simulated = bool(p.simulated or eng.simulated)
        txid = _det_id("tx", {
            "prospect": prospect_id, "engagement": engagement_id,
            "offer": offer_id, "amount": amount, "period": period, "kind": kind,
        })
        path = self._path("transactions", txid)
        if path.exists():
            tx = self._load(path, Transaction, "transaction")
            if payment_ref and not tx.payment_ref:
                # idempotent back-fill: same payment, reference added later
                tx.payment_ref = payment_ref
                tx.updated_at = _now()
                self._save(path, tx.to_dict())
            return tx
        tx = Transaction(
            transaction_id=txid, prospect_id=prospect_id,
            engagement_id=engagement_id, offer_id=offer_id, amount=amount,
            currency=currency, period=period, kind=kind, stage=stage,
            delivery_cost=delivery_cost, simulated=simulated,
            payment_ref=payment_ref,
            created_at=_now(), updated_at=_now(),
        )
        self._save(path, tx.to_dict())
        self.events.append(
            "cv_transaction_created",
            {"transaction_id": txid, "prospect_id": prospect_id,
             "amount": amount, "currency": currency, "period": period,
             "kind": kind, "stage": stage, "simulated": simulated},
        )
        return tx

    def advance_transaction(self, tx_id: str, stage: str) -> Transaction:
        if stage not in TRANSACTION_STAGES:
            raise CommercialError(f"invalid stage {stage!r}")
        tx = self._load(self._path("transactions", tx_id), Transaction,
                        f"transaction {tx_id}")
        cur = TRANSACTION_STAGES.index(tx.stage)
        new = TRANSACTION_STAGES.index(stage)
        if new <= cur:
            raise CommercialError(
                f"cannot move {tx.stage} -> {stage} (stages only advance "
                f"QUOTED -> INVOICED -> COLLECTED)")
        if stage == "COLLECTED" and not (tx.receipt_path
                                         and Path(tx.receipt_path).exists()):
            raise CommercialError(
                "cannot mark COLLECTED without an existing receipt file — "
                "no receipt = no revenue")
        tx.stage = stage
        tx.updated_at = _now()
        if stage == "COLLECTED":
            tx.collected_at = _now()
        self._save(self._path("transactions", tx_id), tx.to_dict())
        self.events.append("cv_transaction_created",
                           {"transaction_id": tx_id, "stage": stage})
        return tx

    def record_payment(self, prospect_id: str, amount: float,
                       receipt_path: str, period: str = "month",
                       kind: str = "SUBSCRIPTION", delivery_cost: float = 0.0,
                       engagement_id: str | None = None,
                       payment_ref: str = "") -> Transaction:
        """The only path to COLLECTED: a real receipt file must exist."""
        if not receipt_path or not Path(receipt_path).exists():
            raise CommercialError(
                f"receipt file does not exist: {receipt_path!r} — "
                f"no receipt = no revenue (nothing recorded)")
        p = self.get_prospect(prospect_id)
        if engagement_id is None:
            engs = self._engagements_for(prospect_id)
            if len(engs) != 1:
                raise CommercialError(
                    "multiple (or zero) engagements for this prospect; "
                    "specify --engagement")
            engagement_id = engs[0].engagement_id
        eng = self.get_engagement(engagement_id)
        tx = self.create_transaction(
            prospect_id, engagement_id, eng.offer_id, amount,
            period=period, kind=kind, stage="QUOTED",
            delivery_cost=delivery_cost, payment_ref=payment_ref,
        )
        if tx.stage == "COLLECTED":
            return tx  # idempotent: this payment was already recorded
        # receipt already verified above: attach it, then advance
        # QUOTED -> INVOICED -> COLLECTED (COLLECTED re-checks the receipt)
        path = self._path("transactions", tx.transaction_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["receipt_path"] = str(receipt_path)
        self._save(path, data)
        tx = self.advance_transaction(tx.transaction_id, "INVOICED")
        tx = self.advance_transaction(tx.transaction_id, "COLLECTED")
        if not p.simulated:
            self.set_prospect_status(prospect_id, "PAYING")
        self.events.append(
            "cv_payment_collected",
            {"transaction_id": tx.transaction_id, "prospect_id": prospect_id,
             "amount": amount, "period": period, "kind": kind,
             "receipt": str(receipt_path), "simulated": tx.simulated,
             "payment_ref": payment_ref, "verified": tx.verified},
        )
        return tx

    def list_transactions(self) -> list[Transaction]:
        return [self._load(p, Transaction, "transaction")
                for p in sorted((self.base / "transactions").glob("*.json"))]

    # -- staged revenue (derived, never stored as competing truths) ----------------------
    def revenue_summary(self) -> dict:
        txs = self.list_transactions()

        def total(pred):
            return round(sum(t.amount for t in txs if pred(t)), 2)

        non_sim = [t for t in txs if not t.simulated]
        collected_ns = [t for t in non_sim if t.stage == "COLLECTED"]
        verified = [t for t in collected_ns if t.verified]
        refunds = [t for t in verified if t.kind == "REFUND"]
        gross = total(lambda t: t in verified and t.kind != "REFUND")
        net = round(gross - total(lambda t: t in refunds), 2)
        recurring = round(sum(t.amount for t in verified
                              if t.period == "month" and t.kind != "REFUND"), 2)
        cost = round(sum(t.delivery_cost for t in verified
                         if t.kind != "REFUND"), 2)

        model_rows = []
        from fire.opportunity import run_hunt
        opps = {o.id: o for o in run_hunt()}
        for offer in self.list_offers():
            opp = opps.get(offer.opportunity_id)
            model_rows.append({
                "opportunity_id": offer.opportunity_id,
                "opportunity": offer.opportunity_name,
                "economics": opp.economics if opp else {},
                "label": "HYPOTHESIS — not revenue",
            })

        return {
            "model": model_rows,
            "quoted": total(lambda t: t.stage == "QUOTED" and t.kind != "REFUND"),
            "invoiced": total(lambda t: t.stage == "INVOICED" and t.kind != "REFUND"),
            "collected_all": total(lambda t: t.stage == "COLLECTED"
                                   and t.kind != "REFUND"),
            "collected_simulated": total(lambda t: t.stage == "COLLECTED"
                                         and t.simulated and t.kind != "REFUND"),
            "verified_revenue": net,
            "verified_recurring_monthly": recurring,
            "verified_delivery_cost": cost,
            "verified_gross_margin": round(net - cost, 2),
            "simulated_note": "simulated activity is never counted as verified revenue",
            "invariant": "verified = collected AND receipt exists AND simulated == false",
        }

    # -- experiment decision + learning bridge ----------------------------------------------
    def _experiment_numbers(self) -> dict:
        prospects = [p for p in self.list_prospects() if not p.simulated]
        engaged: dict[str, list[Delivery]] = {}
        for e in self.list_engagements():
            if not e.simulated:
                engaged[e.prospect_id] = e.deliveries
        responded = [p for p in prospects
                     if p.status in ("RESPONDED", "TRIAL", "OFFERED", "PAYING")]
        with_notes = [pid for pid, ds in engaged.items() if ds]
        second = [pid for pid, ds in engaged.items() if len(ds) >= 2]
        txs = [t for t in self.list_transactions() if not t.simulated]
        paying = {t.prospect_id for t in txs
                  if t.stage == "COLLECTED" and t.kind != "REFUND"}
        deliveries = [d for ds in engaged.values() for d in ds]
        turnarounds = [d.turnaround_min for d in deliveries]
        used = sum(1 for d in deliveries if d.used_by_client)
        return {
            "prospects": len(prospects),
            "responded": len(responded),
            "voice_notes": len(with_notes),
            "second_voice_notes": len(second),
            "paying_customers": len(paying),
            "payments": sum(1 for t in txs
                            if t.stage == "COLLECTED" and t.kind != "REFUND"),
            "deliveries": len(deliveries),
            "median_turnaround_min": (round(statistics.median(turnarounds), 2)
                                      if turnarounds else None),
            "quotes_used_pct": (used / len(deliveries)) if deliveries else None,
        }

    def decide_experiment(self, name: str, record_lesson: bool = True) -> ExperimentDecision:
        if not [p for p in self.list_prospects() if not p.simulated]:
            raise CommercialError(
                "no recorded non-simulated prospects — nothing to decide "
                "(decisions are computed from real recorded numbers only)")
        n = self._experiment_numbers()
        conditions = _experiment_conditions(n)
        k_met = [k for k in ("K1", "K2", "K3", "K4", "K5")
                 if conditions[k]["met"] is True]
        o_met = [k for k in ("O1", "O2", "O3", "O4") if conditions[k]["met"] is True]
        s_all = all(conditions[k]["met"] is True
                    for k in ("S1", "S2", "S3", "S4"))
        if k_met:
            decision = DECISION_KILL
        elif o_met:
            decision = DECISION_OPTIMIZE
        elif s_all:
            decision = DECISION_SCALE
        else:
            decision = DECISION_INCONCLUSIVE
        dec_id = _det_id("cv", {"experiment": name, "numbers": n})
        dec = ExperimentDecision(
            decision_id=dec_id, experiment=name, decision=decision,
            numbers=n, conditions=conditions, decided_at=_now(),
        )
        self._save(self._path("decisions", dec_id), dec.to_dict())
        self.events.append(
            "cv_decision_made",
            {"decision_id": dec_id, "experiment": name, "decision": decision,
             "killed_by": k_met, "optimize_by": o_met,
             "scale_all_met": decision == DECISION_SCALE,
             "verified_revenue": self.revenue_summary()["verified_revenue"]},
        )
        if record_lesson:
            self.record_lesson_from_decision(dec)
        return dec

    def list_decisions(self) -> list[ExperimentDecision]:
        return [self._load(p, ExperimentDecision, "decision")
                for p in sorted((self.base / "decisions").glob("*.json"))]

    def record_lesson_from_decision(self, dec: ExperimentDecision) -> GrowthLesson:
        """Bridge into the EXISTING Phase 8 learning loop: one GrowthLesson
        per experiment decision, lever='revenue', stored in the same lesson
        store with the same gm_lesson_* audit events. No second database."""
        n = dec.numbers
        verified = self.revenue_summary()["verified_revenue"]
        src = dec.decision_id
        if dec.decision == DECISION_KILL:
            lesson = (
                f"Commercial experiment '{dec.experiment}' met kill condition(s) "
                f"{', '.join(k for k in ('K1','K2','K3','K4','K5') if dec.conditions[k]['met'])} "
                f"on measured numbers (responded {n['responded']}/{n['prospects']}, "
                f"voice notes {n['voice_notes']}, payments {n['payments']}); "
                f"the tested offer did not produce the required verified revenue "
                f"(verified R{verified:.0f}).")
            rec = ("Do not re-sell the same offer unchanged; fix the recorded "
                   "constraint and run one additional measured cycle before "
                   "re-attempting.")
        elif dec.decision == DECISION_SCALE:
            lesson = (
                f"Commercial experiment '{dec.experiment}' met ALL scale conditions "
                f"on measured numbers (paying {n['paying_customers']}, repeat use "
                f"{n['second_voice_notes']}/{n['voice_notes']}, verified R{verified:.0f}); "
                f"the tested offer achieved its recorded commercial criteria in this "
                f"experiment's cycle.")
            rec = ("Confirm in a fresh cycle before scaling spend; a single cycle "
                   "is evidence for this experiment, not a guarantee.")
        elif dec.decision == DECISION_OPTIMIZE:
            lesson = (
                f"Commercial experiment '{dec.experiment}' produced partial measured "
                f"progress (optimize condition(s) "
                f"{', '.join(k for k in ('O1','O2','O3','O4') if dec.conditions[k]['met'])}, "
                f"verified R{verified:.0f}); iteration is required before any scale "
                f"claim.")
            rec = ("Run one fix cycle on the recorded constraint, then re-measure "
                   "against the same criteria.")
        else:
            lesson = (
                f"Commercial experiment '{dec.experiment}' met no full K/O/S "
                f"condition set on current measured numbers (responded "
                f"{n['responded']}/{n['prospects']}, voice notes {n['voice_notes']}, "
                f"payments {n['payments']}, verified R{verified:.0f}); the outcome "
                f"is inconclusive and requires more recorded evidence.")
            rec = ("Continue the experiment, record every event with evidence, "
                   "and re-decide on measured numbers.")
        evidence = [
            f"experiment: {dec.experiment}",
            "measured: " + ", ".join(f"{k}={v}" for k, v in n.items()),
            f"decision: {dec.decision} (decision_id {src})",
            f"verified revenue: R{verified:.2f} "
            f"(collected AND receipt AND not simulated)",
        ]
        lesson_obj = GrowthLesson(
            lesson_id=lesson_id_for(src),
            mission_id=src,  # source record id (commercial decision), documented
            business=f"FIRE commercial experiment: {dec.experiment}",
            lever="revenue",
            objective=f"Validate willingness to pay for the {dec.experiment} offer",
            outcome=(f"decision {dec.decision}; verified revenue R{verified:.2f}; "
                     f"paying customers {n['paying_customers']}"),
            decision=dec.decision,
            evidence=evidence,
            observation=("; ".join(f"{k}={v}" for k, v in n.items())
                         + f"; verified revenue R{verified:.2f}"),
            lesson=lesson,
            recommendation=rec,
            confidence=round(0.5 + 0.25 * min(n["payments"], 2), 4),
            created_at=dec.decided_at,
            updated_at=_now(),
        )
        return self.learner.save_lesson(lesson_obj)
