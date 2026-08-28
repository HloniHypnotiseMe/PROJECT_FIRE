"""FIRE mission lifecycle: execution control, measurement, decision,
reporting and event recording for growth missions.

Phase 6 closes the loop:

    DIAGNOSE -> PLAN (Phase 5) -> EXECUTION CONTROL -> MEASURE -> DECIDE
        -> MEMORY / LEARNING -> NEXT MISSION

Existing owners reused (no duplicate concepts introduced):

- fire.onboarding.consent.ConsentManager  — consent truth (AND semantics)
- fire.growth.missions.*                  — mission model, gates, status
- fire.growth.diagnostic.BusinessMetrics  — measurement input
- fire.memory.EventLog                    — append-only audit event stream
- fire.quality.evaluate_artifact          — execution report quality gate

New in this module (minimal):

- MissionRuntime: deterministic mission ids, JSON persistence under
  memory/growth_missions/, ordered step execution with per-step consent
  enforcement, direction-aware measurement against baseline/target,
  deterministic SCALE/OPTIMIZE/KILL decision, execution report.

External actions (customer/supplier contact, purchasing) remain gated:
a step carrying requires_permission is refused until its ApprovalGate is
granted through the existing ConsentManager checks.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from fire.config import load_config, paths
from fire.growth.diagnostic import BusinessMetrics
from fire.growth.missions import (
    ApprovalGate,
    GrowthMission,
    MissionStatus,
    MissionStep,
    StepKind,
)
from fire.growth.models import GrowthLever
from fire.memory import EventLog
from fire.models import TeamMember
from fire.onboarding.consent import ConsentProfile
from fire.quality import evaluate_artifact

LOWER_BETTER_LEVERS = {GrowthLever.SUPPLY}
DECISION_SCALE = "SCALE"
DECISION_OPTIMIZE = "OPTIMIZE"
DECISION_KILL = "KILL"
DECISION_OPTIMIZE_THRESHOLD = 0.50


class MissionExecutionError(Exception):
    """Raised when an execution action violates the lifecycle rules."""


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepExecution:
    """Outcome of one execute/fail/skip attempt."""

    step: int
    status: StepStatus
    blocked: bool = False
    reason: str = ""
    attempts: int = 0


@dataclass
class Measurement:
    mission_id: str
    ts: str
    metrics: dict
    progress: dict           # metric -> 0..1
    overall: float


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mission_id_for(mission: GrowthMission) -> str:
    """Deterministic id: same business + same defining content => same id.

    The id deliberately excludes volatile content (team, evidence text,
    status) so a re-generated mission from the same evidence resumes the
    existing record instead of duplicating it.
    """
    payload = json.dumps(
        {
            "business": mission.business_name,
            "lever": getattr(mission.lever, "value", mission.lever),
            "objective": mission.objective,
            "baseline": mission.baseline,
            "target": mission.target,
        },
        sort_keys=True,
    )
    return "gm-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _rebuild_mission(data: dict) -> GrowthMission:
    return GrowthMission(
        business_name=data["business_name"],
        lever=GrowthLever(data["lever"]),
        objective=data["objective"],
        problem=data["problem"],
        evidence=list(data.get("evidence", [])),
        baseline=dict(data.get("baseline", {})),
        target=dict(data.get("target", {})),
        agent_team=[TeamMember(**t) for t in data.get("agent_team", [])],
        workflow=[
            MissionStep(
                step=s["step"], name=s["name"],
                kind=StepKind(s["kind"]),
                agent_id=s.get("agent_id"),
                requires_permission=s.get("requires_permission"),
            )
            for s in data.get("workflow", [])
        ],
        required_permissions=list(data.get("required_permissions", [])),
        approval_gates=[
            ApprovalGate(
                permission=g["permission"],
                step_numbers=list(g.get("step_numbers", [])),
                description=g.get("description", ""),
                granted=g.get("granted"),
            )
            for g in data.get("approval_gates", [])
        ],
        success_criteria=list(data.get("success_criteria", [])),
        kill_criteria=list(data.get("kill_criteria", [])),
        scale_criteria=list(data.get("scale_criteria", [])),
        status=MissionStatus(data["status"]),
    )


class MissionRuntime:
    """Persistence + execution control for growth missions."""

    def __init__(self, memory_dir: str | Path | None = None):
        cfg = load_config()
        P = paths(cfg)
        if memory_dir is not None:
            mem = Path(memory_dir)
        else:
            mem = P["memory_dir"]
        self.state_dir = mem / "growth_missions"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.events = EventLog(mem)

    # -- persistence ---------------------------------------------------------
    def path_for(self, mission_id: str) -> Path:
        return self.state_dir / f"{mission_id}.json"

    def persist(self, mission: GrowthMission) -> str:
        """Store a mission under its deterministic id (idempotent)."""
        mid = mission_id_for(mission)
        path = self.path_for(mid)
        if path.exists():
            self.events.append("gm_mission_loaded", {"mission_id": mid})
            return mid
        state = {
            "mission_id": mid,
            "mission": mission.to_dict(),
            "steps": {},
            "measurements": [],
            "decision": None,
            "completed_at": None,
            "report": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._save(mid, state)
        self.events.append(
            "gm_mission_created",
            {"mission_id": mid, "lever": mission.lever.value,
             "business": mission.business_name},
        )
        return mid

    def load(self, mission_id: str) -> GrowthMission:
        state = self.state(mission_id)
        return _rebuild_mission(state["mission"])

    def state(self, mission_id: str) -> dict:
        path = self.path_for(mission_id)
        if not path.exists():
            raise MissionExecutionError(f"unknown mission: {mission_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, mission_id: str, state: dict) -> None:
        state["updated_at"] = _now()
        path = self.path_for(mission_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def list_missions(self) -> list[str]:
        return sorted(p.stem for p in self.state_dir.glob("gm-*.json"))

    # -- consent -------------------------------------------------------------
    def apply_consent(self, mission_id: str, consent: ConsentProfile):
        state = self.state(mission_id)
        mission = _rebuild_mission(state["mission"])
        gates = mission.apply_consent(consent)
        state["mission"] = mission.to_dict()
        self._save(mission_id, state)
        self.events.append(
            "gm_consent_applied",
            {"mission_id": mission_id,
             "gates": {g.permission: g.granted for g in gates}},
        )
        return gates

    # -- execution control -----------------------------------------------------
    def _step_obj(self, mission: GrowthMission, step: int) -> MissionStep:
        found = next((s for s in mission.workflow if s.step == step), None)
        if found is None:
            raise MissionExecutionError(f"unknown step {step}")
        return found

    def next_actionable(self, mission_id: str) -> int | None:
        """First step (in numeric order) that is pending or failed."""
        state = self.state(mission_id)
        steps = state["steps"]
        for s in _rebuild_mission(state["mission"]).workflow:
            st = steps.get(str(s.step), {}).get("status", StepStatus.PENDING.value)
            if st in (StepStatus.PENDING.value, StepStatus.FAILED.value):
                return s.step
        return None

    def _check_order(self, state: dict, step: int) -> None:
        expected = self.next_actionable(state["mission_id"])
        cur = state["steps"].get(str(step), {}).get("status")
        if cur == StepStatus.COMPLETED.value:
            return  # idempotent re-execution
        if cur == StepStatus.SKIPPED.value:
            raise MissionExecutionError(f"step {step} was skipped")
        if step != expected:
            raise MissionExecutionError(
                f"out-of-order execution: step {step} requested, "
                f"step {expected} is next actionable"
            )

    def execute_step(
        self,
        mission_id: str,
        step: int,
        result: str = "",
        evidence: str = "",
        consent: ConsentProfile | None = None,
    ) -> StepExecution:
        state = self.state(mission_id)
        mission = _rebuild_mission(state["mission"])
        step_obj = self._step_obj(mission, step)
        self._check_order(state, step)

        cur = state["steps"].get(str(step), {})
        if cur.get("status") == StepStatus.COMPLETED.value:
            return StepExecution(step, StepStatus.COMPLETED,
                                 reason="already completed",
                                 attempts=cur.get("attempts", 1))

        # per-step consent enforcement (existing ConsentManager semantics)
        if step_obj.requires_permission is not None:
            if consent is not None:
                self.apply_consent(mission_id, consent)
                state = self.state(mission_id)
                mission = _rebuild_mission(state["mission"])
            gate = mission.gate_for(step_obj.requires_permission)
            if gate is None or gate.granted is not True:
                self.events.append(
                    "gm_step_blocked",
                    {"mission_id": mission_id, "step": step,
                     "permission": step_obj.requires_permission},
                )
                return StepExecution(
                    step, StepStatus.PENDING, blocked=True,
                    reason=f"consent gate not granted: {step_obj.requires_permission}",
                )

        attempts = cur.get("attempts", 0) + 1
        state["steps"][str(step)] = {
            "status": StepStatus.COMPLETED.value,
            "attempts": attempts,
            "result": result,
            "evidence": evidence,
            "completed_at": _now(),
        }
        if mission.status in (MissionStatus.DRAFT, MissionStatus.READY,
                              MissionStatus.BLOCKED):
            mission.status = MissionStatus.IN_PROGRESS
            state["mission"] = mission.to_dict()

        self._save(mission_id, state)
        if self.next_actionable(mission_id) is None:
            state = self.state(mission_id)
            state["completed_at"] = _now()
            self._save(mission_id, state)
            self.events.append("gm_mission_completed", {"mission_id": mission_id})
            return StepExecution(step, StepStatus.COMPLETED, attempts=attempts)

        self.events.append(
            "gm_step_completed",
            {"mission_id": mission_id, "step": step,
             "kind": step_obj.kind.value, "attempts": attempts},
        )
        return StepExecution(step, StepStatus.COMPLETED, attempts=attempts)

    def fail_step(self, mission_id: str, step: int, reason: str = "") -> StepExecution:
        state = self.state(mission_id)
        mission = _rebuild_mission(state["mission"])
        self._step_obj(mission, step)
        self._check_order(state, step)
        cur = state["steps"].get(str(step), {})
        attempts = cur.get("attempts", 0) + 1
        state["steps"][str(step)] = {
            "status": StepStatus.FAILED.value,
            "attempts": attempts,
            "reason": reason,
            "failed_at": _now(),
        }
        self._save(mission_id, state)
        self.events.append(
            "gm_step_failed",
            {"mission_id": mission_id, "step": step,
             "attempts": attempts, "reason": reason},
        )
        return StepExecution(step, StepStatus.FAILED, reason=reason,
                             attempts=attempts)

    def skip_step(self, mission_id: str, step: int, reason: str = "") -> StepExecution:
        state = self.state(mission_id)
        mission = _rebuild_mission(state["mission"])
        self._step_obj(mission, step)
        self._check_order(state, step)
        cur = state["steps"].get(str(step), {})
        state["steps"][str(step)] = {
            "status": StepStatus.SKIPPED.value,
            "attempts": cur.get("attempts", 0),
            "reason": reason,
            "skipped_at": _now(),
        }
        self._save(mission_id, state)
        self.events.append(
            "gm_step_skipped",
            {"mission_id": mission_id, "step": step, "reason": reason},
        )
        return StepExecution(step, StepStatus.SKIPPED, reason=reason)

    # -- measurement -----------------------------------------------------------
    def measure(self, mission_id: str, current: BusinessMetrics) -> Measurement:
        state = self.state(mission_id)
        mission = _rebuild_mission(state["mission"])
        lever = mission.lever
        lower_better = lever in LOWER_BETTER_LEVERS

        progress: dict[str, float] = {}
        for key, target in mission.target.items():
            base = float(mission.baseline.get(key, 0.0))
            cur = float(getattr(current, key, base))
            progress[key] = self._progress(base, float(target), cur, lower_better)
        overall = round(sum(progress.values()) / len(progress), 4) if progress else 0.0

        meas = Measurement(mission_id, _now(), {k: getattr(current, k) for k in
                       type(current).__dataclass_fields__}, progress, overall)
        state["measurements"].append({
            "ts": meas.ts, "metrics": meas.metrics,
            "progress": meas.progress, "overall": overall,
        })
        self._save(mission_id, state)
        self.events.append(
            "gm_measured",
            {"mission_id": mission_id, "overall": overall,
             "progress": progress},
        )
        return meas

    @staticmethod
    def _progress(base: float, target: float, cur: float,
                  lower_better: bool) -> float:
        if lower_better:
            num, den = base - cur, base - target
        else:
            num, den = cur - base, target - base
        if den == 0:
            return 1.0 if (cur <= target if lower_better else cur >= target) else 0.0
        return max(0.0, min(1.0, num / den))

    # -- decision ----------------------------------------------------------------
    def decide(self, mission_id: str) -> str:
        state = self.state(mission_id)
        if not state["measurements"]:
            raise MissionExecutionError(
                "cannot decide: no measurement recorded yet"
            )
        overall = state["measurements"][-1]["overall"]
        if overall >= 1.0:
            decision = DECISION_SCALE
        elif overall >= DECISION_OPTIMIZE_THRESHOLD:
            decision = DECISION_OPTIMIZE
        else:
            decision = DECISION_KILL

        if decision == DECISION_SCALE:
            m = _rebuild_mission(state["mission"])
            m.status = MissionStatus.SCALED
            state["mission"] = m.to_dict()
        elif decision == DECISION_KILL:
            m = _rebuild_mission(state["mission"])
            m.status = MissionStatus.KILLED
            state["mission"] = m.to_dict()
        # OPTIMIZE: status unchanged; the next mission iteration acts on it.

        state["decision"] = decision
        self._save(mission_id, state)
        self.events.append(
            "gm_decision_made",
            {"mission_id": mission_id, "decision": decision,
             "overall": overall},
        )
        return decision

    # -- execution report + quality gate ------------------------------------------
    def write_execution_report(self, mission_id: str,
                               out_path: str | Path | None = None) -> Path:
        state = self.state(mission_id)
        m = _rebuild_mission(state["mission"])
        steps = state["steps"]
        latest = state["measurements"][-1] if state["measurements"] else None

        lines = [
            f"# Growth Mission Report — {mission_id}",
            "",
            f"- Business: {m.business_name}",
            f"- Lever: {m.lever.value}",
            f"- Status: {m.status.value}",
            f"- Decision: {state['decision'] or 'pending'}",
            f"- Objective: {m.objective}",
            f"- Problem: {m.problem}",
            "",
            "## Evidence",
        ]
        lines += [f"- {e}" for e in m.evidence]
        lines += ["", "## Baseline -> Target"]
        for key in m.target:
            lines.append(f"- {key}: baseline={m.baseline.get(key)} -> "
                         f"target={m.target[key]}")
        lines += ["", "## Step log"]
        for s in m.workflow:
            st = steps.get(str(s.step), {})
            lines.append(
                f"- step {s.step} [{s.kind.value}] {s.name} — "
                f"status={st.get('status', 'pending')}, "
                f"attempts={st.get('attempts', 0)}, "
                f"agent={s.agent_id or '-'}"
                + (f", result={st['result']}" if st.get("result") else "")
                + (f", evidence={st['evidence']}" if st.get("evidence") else "")
            )
        lines += ["", "## Consent gates"]
        for g in m.approval_gates:
            lines.append(f"- {g.permission} (steps {g.step_numbers}): "
                         f"granted={g.granted}")
        if latest:
            lines += ["", "## Latest measurement"]
            lines.append(f"- overall progress: {latest['overall']:.2f}")
            lines += [f"- {k}: {v:.2f}" for k, v in latest["progress"].items()]
        lines += [
            "",
            "## Decision criteria",
            "Success:", *[f"- {c}" for c in m.success_criteria],
            "Kill:", *[f"- {c}" for c in m.kill_criteria],
            "Scale:", *[f"- {c}" for c in m.scale_criteria],
            "",
            "All figures above are measured evidence recorded in the "
            "mission state; nothing is claimed beyond it.",
        ]

        path = Path(out_path) if out_path else self.state_dir / f"{mission_id}_report.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        verdict = evaluate_artifact(path)
        state["report"] = {"path": str(path), "verdict": verdict.verdict,
                           "summary": verdict.summary}
        self._save(mission_id, state)
        self.events.append(
            "gm_report_gated",
            {"mission_id": mission_id, "path": str(path),
             "verdict": verdict.verdict},
        )
        return path
