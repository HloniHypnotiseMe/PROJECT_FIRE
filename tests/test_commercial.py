"""Phase 9: revenue validation engine — evidence-bounded commercial records,
staged/verified revenue, experiment decisions and the commercial->learning
bridge. All state is redirected to a temp memory dir; the repo's own
memory/ and registry are never touched. No test fabricates a real customer:
simulated records are excluded from verified revenue by construction.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from fire import cli as fire_cli
from fire.commercial import (
    CommercialEngine,
    CommercialError,
    PriceTier,
    prospect_id_for,
)
from fire.growth.learning import GrowthLearningEngine, lesson_id_for


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(tmp_path):
    return tmp_path, CommercialEngine(tmp_path)


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fire_cli, "P", {"memory_dir": tmp_path})
    return tmp_path


def _main(capsys, *argv):
    rc = fire_cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _tiers():
    return [PriceTier("P1", 199.0, "month"),
            PriceTier("P2", 99.0, "month"),
            PriceTier("P3", 49.0, "one-off")]


def _full_engine_setup(tmp_path, simulated=False, delivery_cost=0.0):
    """prospect -> offer -> trial; returns (eng, prospect_id, offer_id,
    engagement_id, evidence_dir, receipt_path)."""
    eng = CommercialEngine(tmp_path)
    p = eng.add_prospect("TestTrade (Pty) Ltd", "Plumber", "Johannesburg",
                         simulated=simulated)
    offer = eng.create_offer("opp-wa-voice-quote", _tiers(),
                             unit_of_delivery="1 itemised PDF quote (concierge)",
                             promised_outcome="quote delivered within 5 minutes")
    trial = eng.start_trial(p.prospect_id, offer.offer_id,
                            mission_id="gm-mission123abc")
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir(exist_ok=True)
    receipt = ev_dir / f"receipt_{p.prospect_id}.png"
    return eng, p.prospect_id, offer.offer_id, trial.engagement_id, ev_dir, receipt, p, offer, trial


def _record_delivery(eng, engagement_id, ev_dir, quote_n=1,
                     req="2026-08-28T09:00:00", deli="2026-08-28T09:04:00",
                     used=True):
    ev = ev_dir / f"P{quote_n}_quote_{quote_n}.pdf"
    ev.write_text(f"quote {quote_n}", encoding="utf-8")
    return eng.record_delivery(engagement_id, quote_n, req, deli,
                               str(ev), used_by_client=used)


# ---------------------------------------------------------------------------
# A. prospect deterministic add / list / show
# ---------------------------------------------------------------------------

def test_prospect_deterministic_add_list_show(engine):
    tmp, eng = engine
    p1 = eng.add_prospect("Thabo Plumbing", "Plumber", "Johannesburg")
    p2 = eng.add_prospect("thabo plumbing", "plumber", "johannesburg")
    assert p1.prospect_id == p2.prospect_id == prospect_id_for(
        "Thabo Plumbing", "Plumber", "Johannesburg")
    assert p1.prospect_id.startswith("pr-")
    # idempotent: same business -> same record, no duplicate file
    assert len(list((tmp / "commercial" / "prospects").glob("*.json"))) == 1
    assert eng.list_prospects()[0].business == "Thabo Plumbing"
    assert eng.get_prospect(p1.prospect_id).status == "IDENTIFIED"
    with pytest.raises(CommercialError, match="unknown prospect"):
        eng.get_prospect("pr-doesnotexist00")


# ---------------------------------------------------------------------------
# B. offer created from an EXISTING Opportunity
# ---------------------------------------------------------------------------

def test_offer_from_existing_opportunity(engine):
    tmp, eng = engine
    offer = eng.create_offer("opp-wa-voice-quote", _tiers(),
                             unit_of_delivery="1 quote",
                             promised_outcome="<=5 min turnaround")
    assert offer.opportunity_id == "opp-wa-voice-quote"
    assert offer.opportunity_name == "WhatsApp Voice-Note -> Quote for Tradespeople"
    assert [t.tier for t in offer.price_tiers] == ["P1", "P2", "P3"]
    # idempotent
    again = eng.create_offer("opp-wa-voice-quote", _tiers(),
                             unit_of_delivery="1 quote",
                             promised_outcome="<=5 min turnaround")
    assert again.offer_id == offer.offer_id
    assert len(list((tmp / "commercial" / "offers").glob("*.json"))) == 1
    # unknown opportunity rejected — offers never re-model
    with pytest.raises(CommercialError, match="unknown opportunity"):
        eng.create_offer("opp-does-not-exist", _tiers())
    # no tiers rejected
    with pytest.raises(CommercialError, match="at least one price tier"):
        eng.create_offer("opp-wa-voice-quote", [])


# ---------------------------------------------------------------------------
# C. trial state guards
# ---------------------------------------------------------------------------

def test_trial_state_guards(engine):
    tmp, eng = engine
    with pytest.raises(CommercialError, match="unknown prospect"):
        eng.start_trial("pr-doesnotexist00")
    p = eng.add_prospect("GuardCo", "Electrician", "Johannesburg")
    offer = eng.create_offer("opp-wa-voice-quote", _tiers())
    # no delivery before a valid trial (no engagement exists yet)
    ev = tmp / "ev.pdf"
    ev.write_text("x", encoding="utf-8")
    with pytest.raises(CommercialError, match="unknown engagement"):
        eng.record_delivery("en-doesnotexist00", 1, "2026-08-28T09:00:00",
                            "2026-08-28T09:04:00", str(ev))
    # pricing before a trial rejected
    with pytest.raises(CommercialError, match="unknown engagement"):
        eng.offer_price("en-doesnotexist00", "P1")
    # trial starts; idempotent
    e1 = eng.start_trial(p.prospect_id, offer.offer_id)
    e2 = eng.start_trial(p.prospect_id, offer.offer_id)
    assert e1.engagement_id == e2.engagement_id
    assert eng.get_prospect(p.prospect_id).status == "TRIAL"
    assert len(list((tmp / "commercial" / "engagements").glob("*.json"))) == 1
    # ambiguous offer resolution
    eng.create_offer("opp-cv-ats", [PriceTier("A", 99.0, "one-off")])
    p2 = eng.add_prospect("AmbigCo", "Carpenter", "Pretoria")
    with pytest.raises(CommercialError, match="specify the offer explicitly"):
        eng.start_trial(p2.prospect_id)


# ---------------------------------------------------------------------------
# D. delivery records: turnaround computed; missing evidence rejected
# ---------------------------------------------------------------------------

def test_delivery_turnaround_and_evidence(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    d = _record_delivery(eng, eid, ev_dir, req="2026-08-28T09:00:00",
                         deli="2026-08-28T09:04:00")
    assert d.turnaround_min == 4.0          # computed, not asserted by hand
    d2 = _record_delivery(eng, eid, ev_dir, quote_n=2,
                          req="2026-08-28T10:00:00", deli="2026-08-28T10:35:00",
                          used=False)
    assert d2.turnaround_min == 35.0
    # missing evidence file rejected
    with pytest.raises(CommercialError, match="evidence file does not exist"):
        eng.record_delivery(eid, 3, "2026-08-28T11:00:00", "2026-08-28T11:01:00",
                            str(tmp / "no_such_evidence.pdf"))
    # negative turnaround rejected
    with pytest.raises(CommercialError, match="cannot be negative"):
        eng.record_delivery(eid, 4, "2026-08-28T11:05:00", "2026-08-28T11:01:00",
                            str(ev_dir / "P1_quote_1.pdf"))
    # invalid timestamp rejected
    with pytest.raises(CommercialError, match="invalid ISO timestamp"):
        eng.record_delivery(eid, 5, "yesterday", "2026-08-28T11:01:00",
                            str(ev_dir / "P1_quote_1.pdf"))
    # only the two valid deliveries persisted
    assert len(eng.get_engagement(eid).deliveries) == 2


# ---------------------------------------------------------------------------
# E. unknown pricing tier rejected
# ---------------------------------------------------------------------------

def test_unknown_price_tier_rejected(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    with pytest.raises(CommercialError, match="unknown tier"):
        eng.offer_price(eid, "P9")
    _, tier = eng.offer_price(eid, "P1")
    assert tier.tier == "P1" and tier.price == 199.0
    assert eng.get_prospect(pid).status == "OFFERED"


# ---------------------------------------------------------------------------
# F. payment: no receipt rejected; nonexistent receipt rejected; real receipt
# ---------------------------------------------------------------------------

def test_payment_requires_real_receipt(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    with pytest.raises(CommercialError, match="no receipt = no revenue"):
        eng.record_payment(pid, 199.0, str(tmp / "ghost_receipt.png"))
    receipt.write_bytes(b"\x89PNG fake receipt bytes")
    tx = eng.record_payment(pid, 199.0, str(receipt), period="month",
                            delivery_cost=50.0)
    assert tx.stage == "COLLECTED" and tx.receipt_path == str(receipt)
    assert tx.verified is True
    assert eng.get_prospect(pid).status == "PAYING"
    # idempotent: same payment again -> same transaction, no duplicate
    tx2 = eng.record_payment(pid, 199.0, str(receipt), period="month",
                             delivery_cost=50.0)
    assert tx2.transaction_id == tx.transaction_id
    assert len(eng.list_transactions()) == 1
    # stage order cannot be violated
    with pytest.raises(CommercialError, match="stages only advance"):
        eng.advance_transaction(tx.transaction_id, "INVOICED")


# ---------------------------------------------------------------------------
# G. staged revenue: MODEL labelled; stages; simulated excluded from verified
# ---------------------------------------------------------------------------

def test_staged_revenue_and_verified_invariant(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    receipt.write_bytes(b"real receipt")
    eng.record_payment(pid, 199.0, str(receipt), delivery_cost=50.0)

    # a SIMULATED prospect pays the same price — must NOT enter verified
    sp = eng.add_prospect("DemoTrades", "Plumber", "Sandbox", simulated=True)
    soffer = eng.create_offer("opp-wa-voice-quote", _tiers(), simulated=True)
    setrial = eng.start_trial(sp.prospect_id, soffer.offer_id)
    srec = ev_dir / "sim_receipt.png"
    srec.write_bytes(b"simulated receipt")
    stx = eng.record_payment(sp.prospect_id, 199.0, str(srec))
    assert stx.simulated is True and stx.verified is False

    s = eng.revenue_summary()
    assert s["verified_revenue"] == 199.0        # only the real one
    assert s["collected_all"] == 398.0           # both collected
    assert s["collected_simulated"] == 199.0
    assert any("HYPOTHESIS" in row["label"] for row in s["model"])
    assert "opp-wa-voice-quote" in str(s["model"])
    assert "verified" in s["invariant"]

    # quoted stage: a price offered, not yet paid
    p3 = eng.add_prospect("QuoteCo", "Solar", "Johannesburg")
    e3 = eng.start_trial(p3.prospect_id, offer.offer_id)
    _record_delivery(eng, e3.engagement_id, ev_dir)
    eng.offer_price(e3.engagement_id, "P1")
    tx3 = eng.create_transaction(p3.prospect_id, e3.engagement_id, oid, 199.0)
    assert tx3.stage == "QUOTED"
    s = eng.revenue_summary()
    assert s["quoted"] == 199.0
    assert s["verified_revenue"] == 199.0        # unchanged by quoting


# ---------------------------------------------------------------------------
# H. gross margin = amount - delivery_cost
# ---------------------------------------------------------------------------

def test_gross_margin(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    receipt.write_bytes(b"receipt")
    eng.record_payment(pid, 199.0, str(receipt), delivery_cost=50.0)
    s = eng.revenue_summary()
    assert s["verified_delivery_cost"] == 50.0
    assert s["verified_gross_margin"] == 149.0
    assert s["verified_recurring_monthly"] == 199.0


# ---------------------------------------------------------------------------
# I. attribution: transaction -> engagement -> offer -> prospect (+mission)
# ---------------------------------------------------------------------------

def test_attribution_chain(engine):
    tmp, _ = engine
    eng, pid, oid, eid, ev_dir, receipt, p, offer, trial = _full_engine_setup(tmp)
    assert trial.mission_id == "gm-mission123abc"
    receipt.write_bytes(b"r")
    tx = eng.record_payment(pid, 199.0, str(receipt))
    assert tx.prospect_id == pid
    assert tx.engagement_id == eid
    assert tx.offer_id == oid
    assert eng.get_prospect(tx.prospect_id).business == "TestTrade (Pty) Ltd"
    assert eng.get_offer(tx.offer_id).opportunity_id == "opp-wa-voice-quote"
    assert eng.get_engagement(tx.engagement_id).mission_id == "gm-mission123abc"


# ---------------------------------------------------------------------------
# J. experiment K/O/S decision computed from numbers
# ---------------------------------------------------------------------------

def _seed_experiment(tmp_path, *, responded, notes, paying, med_turn,
                     second_ratio=1.0, used_ratio=1.0):
    """Seed deterministic non-simulated records producing the given numbers."""
    eng = CommercialEngine(tmp_path)
    offer = eng.create_offer("opp-wa-voice-quote", _tiers())
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir(exist_ok=True)
    for i in range(10):
        pid = eng.add_prospect(f"Propect{i} Trade", "Plumber", "Johannesburg"
                               ).prospect_id
        if i < responded:
            eng.set_prospect_status(pid, "RESPONDED")
        if i < notes:
            e = eng.start_trial(pid, offer.offer_id)
            for q in range(2 if (i < notes * second_ratio) else 1):
                _record_delivery(eng, e.engagement_id, ev_dir, quote_n=q + 1,
                                 req="2026-08-28T09:00:00",
                                 deli=f"2026-08-28T09:0{med_turn % 10}:00"
                                 if med_turn < 10 else "2026-08-28T09:30:00",
                                 used=(q == 0 and used_ratio >= 0.5))
    paid = 0
    for i in range(paying):
        pid = eng.add_prospect(f"Propect{i} Trade", "Plumber", "Johannesburg").prospect_id
        e = eng.start_trial(pid, offer.offer_id)
        _record_delivery(eng, e.engagement_id, ev_dir)
        r = ev_dir / f"pay_{i}.png"
        r.write_bytes(b"r")
        eng.record_payment(pid, 199.0, str(r))
        paid += 1
    return eng


def test_decision_scale(engine):
    tmp, _ = engine
    # 10 prospects, 5 responded, 5 with voice notes (3 of them repeat),
    # 3 paying, median turnaround 4 min, 50%+ quotes used -> ALL S met, no K/O
    eng = _seed_experiment(tmp, responded=5, notes=5, paying=3, med_turn=4,
                           second_ratio=0.6, used_ratio=0.5)
    dec = eng.decide_experiment("voice-quote-scale-case")
    assert dec.decision == "SCALE"
    assert all(dec.conditions[k]["met"] is True
               for k in ("S1", "S2", "S3", "S4"))
    # decision persisted deterministically
    assert (tmp / "commercial" / "decisions" / f"{dec.decision_id}.json").exists()
    again = eng.decide_experiment("voice-quote-scale-case")
    assert again.decision_id == dec.decision_id


def test_decision_kill(engine):
    tmp, _ = engine
    # 2 prospects, 1 responded, 0 voice notes, 0 payments -> K1, K2, K3 met
    eng = _seed_experiment(tmp, responded=1, notes=0, paying=0, med_turn=4)
    dec = eng.decide_experiment("voice-quote-kill-case")
    assert dec.decision == "KILL"
    for k in ("K1", "K2", "K3"):
        assert dec.conditions[k]["met"] is True
    # untracked criteria are reported as such, never assumed
    assert dec.conditions["K5"]["met"] is None
    assert dec.conditions["O4"]["met"] is None


def test_decision_requires_real_records(engine):
    tmp, eng = engine
    eng.add_prospect("OnlySim", "Plumber", "JHB", simulated=True)
    with pytest.raises(CommercialError, match="no recorded non-simulated prospects"):
        eng.decide_experiment("sim-only")


# ---------------------------------------------------------------------------
# K. commercial lesson persists through the EXISTING Phase 8 lesson store
# ---------------------------------------------------------------------------

def test_commercial_lesson_via_existing_store(engine):
    tmp, _ = engine
    eng = _seed_experiment(tmp, responded=1, notes=0, paying=0, med_turn=4)
    dec = eng.decide_experiment("voice-quote-lesson-case")
    lid = lesson_id_for(dec.decision_id)
    # same store as growth lessons
    assert (tmp / "lessons" / f"{lid}.json").exists()
    learner = GrowthLearningEngine(tmp)
    lessons = learner.retrieve(lever="revenue")
    assert len(lessons) == 1
    l = lessons[0]
    assert l.decision == "KILL"
    assert l.mission_id == dec.decision_id      # source record id
    assert "kill condition" in l.lesson
    # audit events went through the existing single EventLog
    assert learner.events.list("gm_lesson_created"), "gm_lesson_created missing"
    # re-decide with identical numbers -> lesson updated, not duplicated
    eng.decide_experiment("voice-quote-lesson-case")
    assert len(learner.list_lessons()) == 1


# ---------------------------------------------------------------------------
# L. CLI: full flow in isolated temp memory; simulated demo shows R0 verified
# ---------------------------------------------------------------------------

def test_cli_commercial_full_flow(cli_env, capsys, tmp_path):
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir()
    quote = ev_dir / "P1_quote_1.pdf"
    quote.write_text("simulated quote", encoding="utf-8")
    receipt = ev_dir / "P1_payment_2026-08-28.png"
    receipt.write_bytes(b"simulated receipt")

    rc, out, err = _main(
        capsys, "commercial", "prospect", "add", "--business", "Demo Plumb",
        "--trade", "Plumber", "--location", "Sim City", "--simulated")
    assert rc == 0, (out, err)
    pid = out.split()[1]

    rc, out, err = _main(
        capsys, "commercial", "offer", "create", "--opportunity", "opp-wa-voice-quote",
        "--tiers", "P1=199/mo,P2=99/mo,P3=49/quote",
        "--unit", "1 quote", "--outcome", "<=5 min turnaround", "--simulated")
    assert rc == 0, (out, err)
    oid = out.split()[1]

    rc, out, err = _main(capsys, "commercial", "trial", "start",
                         "--prospect", pid, "--offer", oid)
    assert rc == 0, (out, err)
    assert "[SIMULATED" in out
    eid = out.split()[1]

    rc, out, err = _main(
        capsys, "commercial", "delivery", "record", "--engagement", eid,
        "--quote-n", "1", "--requested-at", "2026-08-28T09:00:00",
        "--delivered-at", "2026-08-28T09:03:30", "--evidence", str(quote), "--used")
    assert rc == 0, (out, err)
    assert "3.5 min" in out

    # missing evidence -> operator error
    rc, out, err = _main(
        capsys, "commercial", "delivery", "record", "--engagement", eid,
        "--quote-n", "2", "--requested-at", "2026-08-28T10:00:00",
        "--delivered-at", "2026-08-28T10:01:00",
        "--evidence", str(tmp_path / "missing.pdf"))
    assert rc == 1 and "evidence file does not exist" in err

    rc, out, err = _main(capsys, "commercial", "price", "offer",
                         "--engagement", eid, "--tier", "P1")
    assert rc == 0, (out, err)
    # unknown tier
    rc, out, err = _main(capsys, "commercial", "price", "offer",
                         "--engagement", eid, "--tier", "P9")
    assert rc == 1 and "unknown tier" in err

    # payment WITHOUT receipt -> rejected, nothing recorded
    rc, out, err = _main(
        capsys, "commercial", "payment", "record", "--prospect", pid,
        "--amount", "199", "--receipt", str(tmp_path / "ghost.png"))
    assert rc == 1 and "no receipt = no revenue" in err

    # payment WITH the (simulated) receipt -> collected, but NOT verified
    rc, out, err = _main(
        capsys, "commercial", "payment", "record", "--prospect", pid,
        "--amount", "199", "--period", "month", "--receipt", str(receipt))
    assert rc == 0, (out, err)
    assert "simulated: True" in out and "verified: False" in out

    # revenue: the demo MUST show VERIFIED = R0 while simulated collected = 199
    rc, out, err = _main(capsys, "commercial", "revenue")
    assert rc == 0, (out, err)
    assert "VERIFIED REVENUE (collected+receipt+real):  R0.00" in out
    assert "R199.00" in out                        # simulated collected shown
    assert "SIMULATED" in out
    assert "HYPOTHESIS" in out                     # MODEL labelled

    # prospects + decisions listing
    rc, out, err = _main(capsys, "commercial", "prospects")
    assert rc == 0 and pid in out and "[SIMULATED]" in out
    rc, out, err = _main(capsys, "commercial", "decisions")
    assert rc == 0 and "no experiment decisions recorded" in out

    # decide on a sim-only engine -> clear operator error
    rc, out, err = _main(capsys, "commercial", "decide",
                         "--experiment", "demo-only-sim")
    assert rc == 1 and "no recorded non-simulated prospects" in err


def test_cli_lessons_shows_commercial_lesson(cli_env, capsys, tmp_path):
    # non-simulated records -> KILL decision -> lesson visible in growth lessons
    eng = _seed_experiment(tmp_path, responded=1, notes=0, paying=0, med_turn=4)
    eng.decide_experiment("voice-quote-cli-case")
    rc, out, err = _main(capsys, "growth", "lessons", "--lever", "revenue")
    assert rc == 0
    assert "KILL" in out and "voice-quote-cli-case" in out
    assert "lever=revenue" in out


# ---------------------------------------------------------------------------
# M. regression: existing growth + full-suite commands remain green
# ---------------------------------------------------------------------------

def test_existing_cli_still_green(capsys):
    rc, out, err = _main(capsys, "status")
    assert rc == 0 and "agents indexed" in out
    rc, out, err = _main(capsys, "revenue")
    assert rc == 0 and "MODEL hypotheses" in out
    rc, out, err = _main(capsys, "growth", "missions")
    assert rc == 0
