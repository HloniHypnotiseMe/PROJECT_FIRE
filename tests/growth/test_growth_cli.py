"""Phase 7: growth operations CLI.

Tests the actual CLI surface (fire.cli.main) end-to-end: profile ->
diagnose -> mission -> consent -> run -> measure -> decide -> report ->
missions. All growth state is redirected to a temp memory dir; the repo's
own memory/ and registry are never touched.
"""
import json
import re
from pathlib import Path

import pytest

from fire import cli as fire_cli


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Point the CLI memory dir at a temp dir (repo state stays pristine)."""
    monkeypatch.setattr(fire_cli, "P", {"memory_dir": tmp_path})
    return tmp_path


def _main(capsys, *argv):
    rc = fire_cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _write_metrics(path: Path, **kw) -> str:
    path.write_text(json.dumps(kw), encoding="utf-8")
    return str(path)


BASE_METRICS = dict(
    monthly_leads=0, conversion_rate=0.05,
    average_customer_spend=800, repeat_purchase_rate=0.5,
    customer_retention_rate=0.7, input_cost_ratio=0.3,
)


def _make_profile(capsys, tmp_path: Path, name: str) -> str:
    """Persist a profile with the weak-baseline metrics (primary lever:
    ACQUISITION -> 10-step GTM mission, gate customer_contact @ step 5,
    targets monthly_leads=10, conversion_rate=0.10)."""
    m0 = _write_metrics(tmp_path / f"{name}.json", **BASE_METRICS)
    rc, out, err = _main(
        capsys, "growth", "profile", "--name", name, "--sector", "Plumbing",
        "--location", "Johannesburg", "--metrics", m0)
    assert rc == 0, (out, err)
    return fire_cli._re_slug(name)


def _make_mission(capsys, tmp_path: Path, name: str) -> str:
    slug = _make_profile(capsys, tmp_path, name)
    rc, out, err = _main(capsys, "growth", "mission", "--profile", slug)
    assert rc == 0, (out, err)
    mids = re.findall(r"gm-[0-9a-f]{12}", out)
    assert mids, out
    return mids[0]


def _mission_state(tmp_path: Path, mid: str) -> dict:
    p = tmp_path / "growth_missions" / f"{mid}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _measure(capsys, tmp_path: Path, mid: str, **kw):
    m = _write_metrics(tmp_path / f"m_{mid}.json", **kw)
    rc, out, err = _main(capsys, "growth", "measure", mid, "--metrics", m)
    assert rc == 0, (out, err)
    return out


# ---------------------------------------------------------------------------
# A. profile round-trip
# ---------------------------------------------------------------------------

def test_profile_round_trip(cli_env, capsys):
    m0 = _write_metrics(cli_env / "m0.json", **BASE_METRICS)
    rc, out, err = _main(
        capsys, "growth", "profile", "--name", "Thabo Plumbing",
        "--sector", "Plumbing", "--location", "Johannesburg",
        "--services", "Repairs, Maintenance", "--whatsapp", "--metrics", m0)
    assert rc == 0, (out, err)
    p = cli_env / "business_profiles" / "thabo-plumbing.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["business_name"] == "Thabo Plumbing"
    assert data["sector"] == "Plumbing"
    assert data["location"] == "Johannesburg"
    assert data["products_services"] == ["Repairs", "Maintenance"]
    assert data["uses_whatsapp"] is True
    assert data["metrics"]["monthly_leads"] == 0

    # reload: deterministic, same content
    rc, out, err = _main(capsys, "growth", "profile", "--show", "thabo-plumbing")
    assert rc == 0
    shown = json.loads(out)
    assert shown["business"]["business_name"] == "Thabo Plumbing"
    assert shown["metrics"]["conversion_rate"] == 0.05

    # re-save is an update to the same deterministic path (no duplicate)
    rc, out, err = _main(
        capsys, "growth", "profile", "--name", "Thabo Plumbing",
        "--sector", "Plumbing")
    assert rc == 0
    assert p.exists()
    assert len(list((cli_env / "business_profiles").glob("*.json"))) == 1

    # unknown profile -> error
    rc, out, err = _main(capsys, "growth", "profile", "--show", "nope")
    assert rc == 1 and "unknown profile" in err
    # no name, no show -> usage error
    rc, out, err = _main(capsys, "growth", "profile")
    assert rc == 1 and "--name" in err


# ---------------------------------------------------------------------------
# B. diagnose
# ---------------------------------------------------------------------------

def test_diagnose_scores_and_priority(cli_env, capsys):
    _make_profile(capsys, cli_env, "DiagCo")
    rc, out, err = _main(capsys, "growth", "diagnose", "--profile", "diagco")
    assert rc == 0, (out, err)
    assert "LEVER SCORES" in out
    assert "PRIMARY LEVER: acquisition" in out
    assert "REASONING" in out
    assert "OPPORTUNITIES" in out
    for lever in ("acquisition", "customer_spend", "lifetime_value", "supply"):
        assert lever in out
    # missing profile -> operator error, nothing fabricated
    rc, out, err = _main(capsys, "growth", "diagnose")
    assert rc == 1 and "no profile" in err


# ---------------------------------------------------------------------------
# C. mission: deterministic, persisted
# ---------------------------------------------------------------------------

def test_mission_created_persisted_deterministic(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "DetCo")
    state_file = cli_env / "growth_missions" / f"{mid}.json"
    assert state_file.exists()
    state = _mission_state(cli_env, mid)
    assert state["mission"]["business_name"] == "DetCo"
    assert state["mission"]["lever"] == "acquisition"
    assert state["mission"]["status"] == "DRAFT"

    # re-create from the same evidence -> same id, no second file
    rc, out, err = _main(capsys, "growth", "mission", "--profile", "detco")
    assert rc == 0
    assert mid in out and "idempotent" in out
    files = sorted((cli_env / "growth_missions").glob("gm-*.json"))
    assert files == [state_file]


# ---------------------------------------------------------------------------
# D. mission displays workflow and gates
# ---------------------------------------------------------------------------

def test_mission_shows_workflow_gates_team(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "ShowCo")
    # re-run mission to capture its full display
    rc, out, err = _main(capsys, "growth", "mission", "--profile", "showco")
    assert rc == 0, (out, err)
    assert f"MISSION {mid}" in out
    assert "WORKFLOW (ordered, non-skippable):" in out
    assert "01 [" in out and "10 [" in out            # 10 GTM steps
    assert "CONSENT GATES" in out
    assert "customer_contact_authorized (steps [5])" in out
    assert "TEAM (registry-resolved)" in out
    assert "SUCCESS CRITERIA" in out
    assert "KILL CRITERIA" in out
    assert "SCALE CRITERIA" in out
    assert "baseline" in out and "target" in out


# ---------------------------------------------------------------------------
# E. consent flags correctly affect gates
# ---------------------------------------------------------------------------

def test_consent_flags_affect_gates(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "GateCo")

    # fresh: gates unevaluated, status DRAFT
    rc, out, err = _main(capsys, "growth", "consent", mid)
    assert rc == 0
    assert "not yet evaluated" in out and "DRAFT" in out

    # owner alone does NOT grant customer contact (AND rule) -> BLOCKED
    rc, out, err = _main(capsys, "growth", "consent", mid, "--owner")
    assert rc == 0
    assert "denied" in out and "BLOCKED" in out
    assert _mission_state(cli_env, mid)["mission"]["status"] == "BLOCKED"

    # full customer-contact consent -> GRANTED -> READY
    rc, out, err = _main(
        capsys, "growth", "consent", mid, "--owner", "--customer-contact")
    assert rc == 0
    assert "GRANTED" in out and "READY" in out
    assert _mission_state(cli_env, mid)["mission"]["status"] == "READY"

    # unknown mission -> error
    rc, out, err = _main(capsys, "growth", "consent", "gm-doesnotexist00")
    assert rc == 1 and "unknown mission" in err


# ---------------------------------------------------------------------------
# F. run respects step ordering
# ---------------------------------------------------------------------------

def test_run_respects_step_ordering(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "OrderCo")
    # jumping to step 3 before step 1 -> rejected
    rc, out, err = _main(capsys, "growth", "run", mid, "--step", "3")
    assert rc == 1 and "out-of-order" in err
    assert "1" not in _mission_state(cli_env, mid)["steps"]

    # step 1 then step 2 (in order) succeed; default run continues to 3
    rc, out, err = _main(capsys, "growth", "run", mid)
    assert rc == 0 and "STEP 1" in out
    rc, out, err = _main(capsys, "growth", "run", mid, "--step", "2")
    assert rc == 0 and "STEP 2" in out
    rc, out, err = _main(capsys, "growth", "run", mid)
    assert rc == 0 and "STEP 3" in out


# ---------------------------------------------------------------------------
# G. run blocks missing consent (and records nothing external)
# ---------------------------------------------------------------------------

def test_run_blocks_without_consent(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "BlockCo")
    for i in (1, 2, 3, 4):
        rc, out, err = _main(capsys, "growth", "run", mid, "--result", f"step {i} done")
        assert rc == 0, (out, err)

    # step 5 needs customer_contact_authorized: blocked, exit 2, state intact
    rc, out, err = _main(capsys, "growth", "run", mid)
    assert rc == 2
    assert "BLOCKED" in out and "customer_contact_authorized" in out
    assert "fire growth consent" in out          # operator hint
    state = _mission_state(cli_env, mid)
    assert "5" not in state["steps"]             # blocked step stayed pending

    # with consent (applied inline), the same step now completes
    rc, out, err = _main(
        capsys, "growth", "run", mid, "--owner", "--customer-contact",
        "--result", "GTM experiment launched", "--evidence", "campaign log")
    assert rc == 0 and "STEP 5" in out
    assert _mission_state(cli_env, mid)["steps"]["5"]["status"] == "completed"


# ---------------------------------------------------------------------------
# H. run records result/evidence
# ---------------------------------------------------------------------------

def test_run_records_result_and_evidence(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "RecordCo")
    rc, out, err = _main(
        capsys, "growth", "run", mid,
        "--result", "walk-in + referrals audited",
        "--evidence", "notebook counts 2026-08")
    assert rc == 0
    step1 = _mission_state(cli_env, mid)["steps"]["1"]
    assert step1["status"] == "completed"
    assert step1["result"] == "walk-in + referrals audited"
    assert step1["evidence"] == "notebook counts 2026-08"
    assert "result: walk-in + referrals audited" in out
    assert "evidence: notebook counts 2026-08" in out


# ---------------------------------------------------------------------------
# I. measure persists measurement
# ---------------------------------------------------------------------------

def test_measure_persists(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "MeasCo")
    out = _measure(capsys, cli_env, mid,
                   **{**BASE_METRICS, "monthly_leads": 5})
    state = _mission_state(cli_env, mid)
    assert len(state["measurements"]) == 1
    meas = state["measurements"][0]
    # baseline leads 0 -> target 10: 5 is 0.5; conversion 0.05 unchanged: 0.0
    assert meas["progress"]["monthly_leads"] == 0.5
    assert meas["progress"]["conversion_rate"] == 0.0
    assert meas["overall"] == 0.25
    assert "OVERALL PROGRESS: 0.2500" in out
    assert "higher is better" in out
    assert "baseline" in out and "target" in out

    # unknown metric field is rejected, nothing persisted
    bad = _write_metrics(cli_env / "bad.json", **{"nope": 1})
    rc, out, err = _main(capsys, "growth", "measure", mid, "--metrics", bad)
    assert rc == 1 and "unknown metric fields" in err
    assert len(_mission_state(cli_env, mid)["measurements"]) == 1


# ---------------------------------------------------------------------------
# J. decide returns SCALE / OPTIMIZE / KILL appropriately
# ---------------------------------------------------------------------------

def test_decide_scale_optimize_kill(cli_env, capsys):
    ms = _make_mission(capsys, cli_env, "ScaleCo")
    mo = _make_mission(capsys, cli_env, "OptimizeCo")
    mk = _make_mission(capsys, cli_env, "KillCo")

    def decide(mid: str) -> str:
        rc, out, err = _main(capsys, "growth", "decide", mid)
        assert rc == 0, (out, err)
        return out.splitlines()[0]

    # overall 1.0 -> SCALE (status SCALED)
    _measure(capsys, cli_env, ms, **{**BASE_METRICS,
                                     "monthly_leads": 10, "conversion_rate": 0.10})
    assert decide(ms) == "SCALE"
    assert _mission_state(cli_env, ms)["mission"]["status"] == "SCALED"

    # overall 0.5 -> OPTIMIZE (status unchanged: DRAFT)
    _measure(capsys, cli_env, mo, **{**BASE_METRICS, "monthly_leads": 10})
    assert decide(mo) == "OPTIMIZE"
    assert _mission_state(cli_env, mo)["mission"]["status"] == "DRAFT"

    # overall 0.25 -> KILL (status KILLED)
    _measure(capsys, cli_env, mk, **{**BASE_METRICS, "monthly_leads": 5})
    assert decide(mk) == "KILL"
    assert _mission_state(cli_env, mk)["mission"]["status"] == "KILLED"

    # deciding without any measurement is an error
    mn = _make_mission(capsys, cli_env, "NoMeasCo")
    rc, out, err = _main(capsys, "growth", "decide", mn)
    assert rc == 1 and "no measurement" in err


# ---------------------------------------------------------------------------
# K. report invokes the existing quality gate
# ---------------------------------------------------------------------------

def test_report_invokes_quality_gate(cli_env, capsys):
    mid = _make_mission(capsys, cli_env, "ReportCo")
    _measure(capsys, cli_env, mid, **{**BASE_METRICS,
                                      "monthly_leads": 10, "conversion_rate": 0.10})
    rc, out, err = _main(capsys, "growth", "decide", mid)
    assert rc == 0

    rc, out, err = _main(capsys, "growth", "report", mid)
    assert rc == 0, (out, err)
    state = _mission_state(cli_env, mid)
    rep = state["report"]
    assert rep and Path(rep["path"]).exists()
    assert rep["verdict"] in ("GO", "REVISE", "NO-GO")
    assert f"QUALITY GATE: {rep['verdict']}" in out
    assert "REPORT:" in out
    assert "decision: SCALE" in out
    report_text = Path(rep["path"]).read_text(encoding="utf-8")
    assert f"Growth Mission Report — {mid}" in report_text

    # custom output path is honoured
    custom = cli_env / "custom_report.md"
    rc, out, err = _main(capsys, "growth", "report", mid, "--out", str(custom))
    assert rc == 0 and custom.exists()
    assert _mission_state(cli_env, mid)["report"]["verdict"] in ("GO", "REVISE", "NO-GO")


# ---------------------------------------------------------------------------
# L. missions lists persisted missions
# ---------------------------------------------------------------------------

def test_missions_lists_persisted(cli_env, capsys):
    rc, out, err = _main(capsys, "growth", "missions")
    assert rc == 0 and "no growth missions" in out

    ms = _make_mission(capsys, cli_env, "ListScale")
    _measure(capsys, cli_env, ms, **{**BASE_METRICS,
                                     "monthly_leads": 10, "conversion_rate": 0.10})
    _main(capsys, "growth", "decide", ms)
    mo = _make_mission(capsys, cli_env, "ListOpt")
    _measure(capsys, cli_env, mo, **{**BASE_METRICS, "monthly_leads": 10})
    _main(capsys, "growth", "decide", mo)

    rc, out, err = _main(capsys, "growth", "missions")
    assert rc == 0
    assert ms in out and mo in out
    assert "ListScale" in out and "ListOpt" in out
    assert "SCALED" in out and "SCALE" in out
    assert "OPTIMIZE" in out and "DRAFT" in out
    assert "step 1" in out  # next actionable for both fresh missions


# ---------------------------------------------------------------------------
# M. existing CLI commands remain green
# ---------------------------------------------------------------------------

def test_existing_cli_commands_still_green(capsys):
    # unpatched CLI, real repo, read-only commands
    rc, out, err = _main(capsys, "status")
    assert rc == 0 and "agents indexed" in out
    rc, out, err = _main(capsys, "revenue")
    assert rc == 0 and "MODEL hypotheses" in out
    rc, out, err = _main(capsys, "registry", "stats")
    assert rc == 0 and '"agents": 270' in out
    rc, out, err = _main(capsys, "search", "voice quoting", "--top", "2")
    assert rc == 0
    # --version exits via argparse by design (pre-existing behavior)
    with pytest.raises(SystemExit) as excinfo:
        _main(capsys, "--version")
    assert excinfo.value.code == 0
