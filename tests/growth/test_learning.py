"""Phase 8: growth learning loop — lesson extraction, persistence,
retrieval, audit and closed-loop integration.

Tests the engine API (fire.growth.learning) and the real CLI surface
(fire.cli.main) with growth state redirected to a temp memory dir; the
repo's own memory/ and registry are never touched.
"""
import json
import re
from pathlib import Path

import pytest

from fire import cli as fire_cli
from fire.growth.learning import (
    GrowthLearningEngine,
    LearningError,
    lesson_id_for,
)
from fire.growth.lifecycle import MissionRuntime
from fire.growth.orchestrator import GrowthOrchestrator
from fire.growth.models import BusinessProfile
from fire.growth.diagnostic import BusinessMetrics


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

BASE_METRICS = dict(
    monthly_leads=0, conversion_rate=0.05,
    average_customer_spend=800, repeat_purchase_rate=0.5,
    customer_retention_rate=0.7, input_cost_ratio=0.3,
)


@pytest.fixture
def env(tmp_path):
    """Isolated memory dir with runtime + engine (same dir, like the CLI)."""
    return tmp_path, MissionRuntime(tmp_path), GrowthLearningEngine(tmp_path)


def _create_mission(rt: MissionRuntime, name: str, **metric_overrides) -> str:
    m = BusinessMetrics(**{**BASE_METRICS, **metric_overrides})
    mission = GrowthOrchestrator().create_mission(
        BusinessProfile(business_name=name, sector="Plumbing",
                        location="Johannesburg"), m)
    return rt.persist(mission)


def _measure_decide(rt: MissionRuntime, mid: str, **overrides) -> str:
    rt.measure(mid, BusinessMetrics(**{**BASE_METRICS, **overrides}))
    return rt.decide(mid)


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fire_cli, "P", {"memory_dir": tmp_path})
    return tmp_path


def _main(capsys, *argv):
    rc = fire_cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _write_metrics(path: Path, **kw) -> str:
    path.write_text(json.dumps(kw), encoding="utf-8")
    return str(path)


def _make_profile(capsys, tmp_path: Path, name: str, **overrides) -> str:
    m0 = _write_metrics(tmp_path / f"{name}.json",
                        **{**BASE_METRICS, **overrides})
    rc, out, err = _main(
        capsys, "growth", "profile", "--name", name, "--sector", "Plumbing",
        "--metrics", m0)
    assert rc == 0, (out, err)
    return fire_cli._re_slug(name)


# ---------------------------------------------------------------------------
# A. lesson creation: completed + measured + decided -> exactly one lesson
# ---------------------------------------------------------------------------

def test_learn_creates_exactly_one_lesson(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "LearnCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)  # overall 1.0 -> SCALE
    lesson = engine.learn(mid)
    files = list((tmp / "lessons").glob("ln-*.json"))
    assert len(files) == 1
    assert files[0].name == f"{lesson.lesson_id}.json"
    assert lesson.decision == "SCALE"
    # persisted content round-trips
    assert engine.load(lesson.lesson_id).mission_id == mid


# ---------------------------------------------------------------------------
# B. determinism: same mission cannot create duplicate lessons
# ---------------------------------------------------------------------------

def test_learn_idempotent_no_duplicates(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "IdemCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)
    l1 = engine.learn(mid)
    l2 = engine.learn(mid)
    assert l1.lesson_id == l2.lesson_id == lesson_id_for(mid)
    assert l1.lesson_id.startswith("ln-") and len(l1.lesson_id) == 15
    assert len(list((tmp / "lessons").glob("ln-*.json"))) == 1
    # re-learn preserves created_at, updates the record
    assert l2.created_at == l1.created_at


# ---------------------------------------------------------------------------
# C. traceability: lesson references its originating mission
# ---------------------------------------------------------------------------

def test_lesson_traceable_to_mission(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "TraceCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)
    lesson = engine.learn(mid)
    state = rt.state(mid)
    assert lesson.mission_id == mid
    assert lesson.business == state["mission"]["business_name"]
    assert lesson.lever == state["mission"]["lever"]
    assert lesson.objective == state["mission"]["objective"]
    # evidence carries mission-recorded facts (facts, not claims)
    assert any(e.startswith("recorded decision: SCALE") for e in lesson.evidence)
    assert any(e.startswith("progress:") for e in lesson.evidence)
    # the mission remains authoritative: lesson stores only facts + its id
    data = json.loads(engine.path_for(lesson.lesson_id).read_text(encoding="utf-8"))
    assert data["mission_id"] == mid
    assert "workflow" not in data and "agent_team" not in data


# ---------------------------------------------------------------------------
# D. decision handling: SCALE / OPTIMIZE / KILL
# ---------------------------------------------------------------------------

def test_learn_scale_wording(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "ScaleWCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)  # 1.0 -> SCALE
    lesson = engine.learn(mid)
    assert lesson.decision == "SCALE"
    assert "achieved its recorded target" in lesson.lesson
    assert "not a guarantee" in lesson.recommendation
    assert lesson.confidence == 0.75  # one measurement cycle


def test_learn_optimize_wording(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "OptWCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.05)  # 0.5 -> OPTIMIZE
    lesson = engine.learn(mid)
    assert lesson.decision == "OPTIMIZE"
    assert "partial measured progress" in lesson.lesson
    assert "iteration" in lesson.lesson
    # mission status untouched by OPTIMIZE
    assert rt.state(mid)["mission"]["status"] == "DRAFT"


def test_learn_kill_wording(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "KillWCo")
    _measure_decide(rt, mid, monthly_leads=5, conversion_rate=0.05)  # 0.25 -> KILL
    lesson = engine.learn(mid)
    assert lesson.decision == "KILL"
    assert "failed to achieve sufficient measured progress" in lesson.lesson
    assert "Do not re-run the same intervention unchanged" in lesson.recommendation


def test_confidence_grows_with_measurement_cycles(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "CyclesCo")
    rt.measure(mid, BusinessMetrics(**{**BASE_METRICS, "monthly_leads": 4}))
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)  # second cycle -> overall 1.0
    lesson = engine.learn(mid)
    assert lesson.confidence == 1.0  # two cycles: base 0.5 + 2x0.25


# ---------------------------------------------------------------------------
# E. evidence requirement: unmeasured / undecided / missing -> rejected
# ---------------------------------------------------------------------------

def test_learn_rejects_unmeasured(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "NoMeasCo")
    with pytest.raises(LearningError, match="no measurement"):
        engine.learn(mid)
    assert not (tmp / "lessons").exists() or not list((tmp / "lessons").glob("*.json"))


def test_learn_rejects_undecided(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "NoDecCo")
    rt.measure(mid, BusinessMetrics(**{**BASE_METRICS, "monthly_leads": 5}))
    with pytest.raises(LearningError, match="no decision"):
        engine.learn(mid)


def test_learn_rejects_unknown_mission(env):
    tmp, rt, engine = env
    with pytest.raises(LearningError, match="unknown mission"):
        engine.learn("gm-doesnotexist00")


# ---------------------------------------------------------------------------
# F. retrieval by business / lever / decision
# ---------------------------------------------------------------------------

def _seed_three_lessons(env):
    tmp, rt, engine = env
    ma = _create_mission(rt, "AlphaCo")            # acquisition, SCALE
    _measure_decide(rt, ma, monthly_leads=10, conversion_rate=0.10)
    mb = _create_mission(rt, "BetaCo")             # acquisition, KILL
    _measure_decide(rt, mb, monthly_leads=2, conversion_rate=0.05)
    # strong acquisition (leads>0, conv>=0.10) but high input cost ->
    # SUPPLY is the diagnosed primary lever; cost 0.57 vs target 0.54
    # from baseline 0.6 -> progress 0.5 -> OPTIMIZE
    mc = _create_mission(rt, "GammaCo", monthly_leads=50,
                         conversion_rate=0.12, input_cost_ratio=0.6)
    _measure_decide(rt, mc, input_cost_ratio=0.57)
    return [engine.learn(mid) for mid in (ma, mb, mc)]


def test_retrieve_by_dimensions(env):
    _seed_three_lessons(env)
    tmp, rt, engine = env
    assert [l.business for l in engine.retrieve(business="AlphaCo")] == ["AlphaCo"]
    assert [l.mission_id for l in engine.retrieve(decision="KILL")] == \
        [l.mission_id for l in engine.list_lessons() if l.decision == "KILL"]
    supplies = engine.retrieve(lever="supply")
    assert len(supplies) == 1 and supplies[0].business == "GammaCo"
    # combined dimensions
    both = engine.retrieve(business="BetaCo", decision="KILL", lever="acquisition")
    assert len(both) == 1
    # objective substring dimension
    assert len(engine.retrieve(objective="customer acquisition engine")) == 2
    # no match
    assert engine.retrieve(business="NobodyCo") == []


# ---------------------------------------------------------------------------
# G. deterministic ordering
# ---------------------------------------------------------------------------

def test_retrieve_deterministic_order(env):
    _seed_three_lessons(env)
    tmp, rt, engine = env
    a = engine.list_lessons()
    b = engine.list_lessons()
    assert [l.lesson_id for l in a] == [l.lesson_id for l in b]
    keys = [(l.business, l.lever, l.decision, l.lesson_id) for l in a]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# H. audit: existing-style events through the single EventLog
# ---------------------------------------------------------------------------

def test_learn_emits_audit_events(env):
    tmp, rt, engine = env
    mid = _create_mission(rt, "AuditCo")
    _measure_decide(rt, mid, monthly_leads=10, conversion_rate=0.10)
    lesson = engine.learn(mid)
    engine.learn(mid)  # re-learn
    created = engine.events.list("gm_lesson_created")
    updated = engine.events.list("gm_lesson_updated")
    assert len(created) == 1 and len(updated) == 1
    assert created[0]["lesson_id"] == lesson.lesson_id
    assert created[0]["mission_id"] == mid
    assert created[0]["decision"] == "SCALE"
    # same events.jsonl as the mission lifecycle events (one audit system)
    ev_lines = (tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"gm_mission_created"' in line for line in ev_lines)
    assert any('"gm_lesson_created"' in line for line in ev_lines)


# ---------------------------------------------------------------------------
# I. closed loop: a later diagnostic/mission sees the prior lesson
# ---------------------------------------------------------------------------

def test_closed_loop_next_mission_sees_prior_lesson(cli_env, capsys):
    slug = _make_profile(capsys, cli_env, "LoopCo")
    # mission A: baseline leads=0 -> ACQUISITION; measure to target -> SCALE
    rc, out, err = _main(capsys, "growth", "mission", "--profile", slug)
    assert rc == 0
    mid_a = re.findall(r"gm-[0-9a-f]{12}", out)[0]
    m1 = _write_metrics(cli_env / "m1.json", **{**BASE_METRICS,
                                                "monthly_leads": 12,
                                                "conversion_rate": 0.11})
    rc, out, err = _main(capsys, "growth", "measure", mid_a, "--metrics", m1)
    assert rc == 0
    rc, out, err = _main(capsys, "growth", "decide", mid_a)
    assert rc == 0 and out.splitlines()[0] == "SCALE"
    rc, out, err = _main(capsys, "growth", "learn", "--mission", mid_a)
    assert rc == 0 and "LESSON ln-" in out

    # operator re-measures the business (new baseline, still ACQUISITION
    # primary: conversion 0.08 < 0.10) -> next mission is a new record
    m2 = _write_metrics(cli_env / "m2.json", **{**BASE_METRICS,
                                                "monthly_leads": 20,
                                                "conversion_rate": 0.08})
    rc, out, err = _main(
        capsys, "growth", "profile", "--name", "LoopCo", "--sector", "Plumbing",
        "--metrics", m2)
    assert rc == 0

    # diagnostic now surfaces the prior lesson
    rc, out, err = _main(capsys, "growth", "diagnose", "--profile", slug)
    assert rc == 0
    assert "PRIOR LESSONS" in out and mid_a in out and "SCALE" in out

    # next mission carries the prior lesson into its recorded evidence
    rc, out, err = _main(capsys, "growth", "mission", "--profile", slug)
    assert rc == 0
    mid_b = re.findall(r"gm-[0-9a-f]{12}", out)
    assert mid_b and mid_b[0] != mid_a
    state_b = json.loads(
        (cli_env / "growth_missions" / f"{mid_b[0]}.json").read_text())
    assert any(e.startswith("prior lesson ln-") and mid_a in e
               for e in state_b["mission"]["evidence"])
    assert "PRIOR LESSONS" in out


# ---------------------------------------------------------------------------
# J. CLI: fire growth learn / lessons (+ filters)
# ---------------------------------------------------------------------------

def test_cli_learn_and_lessons_with_filters(cli_env, capsys):
    # learn without measurement -> clear operator error
    slug = _make_profile(capsys, cli_env, "CliCo")
    rc, out, err = _main(capsys, "growth", "mission", "--profile", slug)
    assert rc == 0
    mid = re.findall(r"gm-[0-9a-f]{12}", out)[0]
    rc, out, err = _main(capsys, "growth", "learn", "--mission", mid)
    assert rc == 1 and "no measurement" in err

    # measure + decide + learn
    m1 = _write_metrics(cli_env / "m1.json", **{**BASE_METRICS,
                                                "monthly_leads": 10,
                                                "conversion_rate": 0.10})
    _main(capsys, "growth", "measure", mid, "--metrics", m1)
    _main(capsys, "growth", "decide", mid)
    rc, out, err = _main(capsys, "growth", "learn", "--mission", mid)
    assert rc == 0
    assert f"LESSON ln-" in out and f"mission    : {mid}" in out
    assert "SCALE" in out and "confidence" in out
    lesson_id = re.findall(r"ln-[0-9a-f]{12}", out)[0]

    # second business + KILL mission for filter tests
    slug2 = _make_profile(capsys, cli_env, "CliKCo")
    rc, out, err = _main(capsys, "growth", "mission", "--profile", slug2)
    mid2 = re.findall(r"gm-[0-9a-f]{12}", out)[0]
    m3 = _write_metrics(cli_env / "m3.json", **{**BASE_METRICS, "monthly_leads": 1})
    _main(capsys, "growth", "measure", mid2, "--metrics", m3)
    _main(capsys, "growth", "decide", mid2)
    rc, out, err = _main(capsys, "growth", "learn", "--mission", mid2)
    assert rc == 0

    # list all
    rc, out, err = _main(capsys, "growth", "lessons")
    assert rc == 0 and "LESSONS (2):" in out and lesson_id in out

    # filters
    rc, out, err = _main(capsys, "growth", "lessons", "--business", "CliCo")
    assert rc == 0 and "LESSONS (1):" in out and lesson_id in out and mid2 not in out
    rc, out, err = _main(capsys, "growth", "lessons", "--decision", "KILL")
    assert rc == 0 and "LESSONS (1):" in out and mid2 in out and lesson_id not in out
    rc, out, err = _main(capsys, "growth", "lessons", "--lever", "acquisition")
    assert rc == 0 and "LESSONS (2):" in out
    # invalid filter value rejected by argparse
    with pytest.raises(SystemExit):
        _main(capsys, "growth", "lessons", "--lever", "not-a-lever")
    # unknown mission for learn
    rc, out, err = _main(capsys, "growth", "learn", "--mission", "gm-nope00000000")
    assert rc == 1 and "unknown mission" in err
