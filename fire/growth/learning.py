"""FIRE growth learning: evidence-bounded lessons from recorded outcomes.

Phase 8 closes the loop:

    MISSION -> EXECUTION -> MEASURE -> DECIDE -> OUTCOME
        -> LESSON EXTRACTION -> LESSON PERSISTENCE -> LESSON RETRIEVAL
        -> NEXT MISSION / DIAGNOSTIC CONTEXT

Existing owners reused (no duplicate concepts introduced):

- fire.growth.lifecycle.MissionRuntime — authoritative mission state (read-only here)
- fire.memory.EventLog                 — the single audit event stream (gm_lesson_*)
- memory/lessons/<id>.json             — same one-JSON-per-object + atomic-write
  convention as memory/growth_missions/

Rules enforced here:

- A lesson is extractable ONLY from recorded mission state: at least one
  measurement AND a recorded decision. Unmeasured, undecided or missing
  mission state is rejected with LearningError.
- Lessons are mission-scoped: they state what this mission measured against
  its recorded target. They never claim that "a strategy works" in general.
- One lesson per mission: deterministic id ln-<sha256(mission_id)[:12]>;
  re-learning updates the record (idempotent, no duplicates) and the
  originating mission remains authoritative (only its id + recorded facts
  are stored, never the mission object itself).
- confidence is a deterministic heuristic over evidence quantity
  (number of recorded measurement cycles). It is NOT statistical certainty.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fire.config import load_config, paths
from fire.growth.lifecycle import MissionExecutionError, MissionRuntime
from fire.memory import EventLog

DECISION_SCALE = "SCALE"
DECISION_OPTIMIZE = "OPTIMIZE"
DECISION_KILL = "KILL"

CONFIDENCE_BASE = 0.50
CONFIDENCE_PER_CYCLE = 0.25
CONFIDENCE_CAP_CYCLES = 2


class LearningError(Exception):
    """Raised when lesson extraction violates the learning rules."""


# ---------------------------------------------------------------------------
# the lesson
# ---------------------------------------------------------------------------

@dataclass
class GrowthLesson:
    """A structured, traceable lesson from one decided mission.

    Distinct layers are kept separate (never collapsed):
    - observation: raw measured facts (facts only)
    - outcome:     the measured result summary
    - lesson:      the decision-bound interpretation (mission-scoped)
    - recommendation: what to do next
    """

    lesson_id: str
    mission_id: str
    business: str
    lever: str
    objective: str
    outcome: str
    decision: str
    evidence: list[str] = field(default_factory=list)
    observation: str = ""
    lesson: str = ""
    recommendation: str = ""
    confidence: float = 0.0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GrowthLesson":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lesson_id_for(mission_id: str) -> str:
    """Deterministic, mission-scoped lesson id (one lesson per mission)."""
    return "ln-" + hashlib.sha256(mission_id.encode("utf-8")).hexdigest()[:12]


# Evidence-bounded, mission-scoped wording. Deliberately never generalizes
# beyond the mission: "this mission achieved X measured result against Y
# target" — not "this strategy works".
_LESSON_TEXT = {
    DECISION_SCALE: (
        "Mission {mid} achieved its recorded target (overall progress {p:.2f}) "
        "for {lever} on {business}: the tested intervention met the recorded "
        "measurable criteria in this mission's cycle."
    ),
    DECISION_OPTIMIZE: (
        "Mission {mid} produced partial measured progress (overall {p:.2f}, "
        "below 1.00) for {lever} on {business}; iteration is required before "
        "any scale claim."
    ),
    DECISION_KILL: (
        "Mission {mid} failed to achieve sufficient measured progress "
        "(overall {p:.2f} < 0.50) for {lever} on {business} under the tested "
        "conditions."
    ),
}

_RECOMMENDATION = {
    DECISION_SCALE: (
        "Confirm in a fresh measurement cycle before scaling spend; a single "
        "cycle is evidence for this mission, not a guarantee."
    ),
    DECISION_OPTIMIZE: (
        "Open the next mission iteration on the same lever, adjust the "
        "intervention, and re-measure against the same recorded target."
    ),
    DECISION_KILL: (
        "Do not re-run the same intervention unchanged; re-diagnose the "
        "constraint with new evidence before attempting this lever again."
    ),
}


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

class GrowthLearningEngine:
    """Extract, persist and retrieve evidence-bounded growth lessons."""

    def __init__(self, memory_dir: str | Path | None = None):
        if memory_dir is not None:
            mem = Path(memory_dir)
        else:
            cfg = load_config()
            mem = paths(cfg)["memory_dir"]
        self.memory_dir = mem
        self.lessons_dir = mem / "lessons"
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self.events = EventLog(mem)
        self.runtime = MissionRuntime(mem)

    # -- persistence ---------------------------------------------------------
    def path_for(self, lesson_id: str) -> Path:
        return self.lessons_dir / f"{lesson_id}.json"

    def load(self, lesson_id: str) -> GrowthLesson:
        path = self.path_for(lesson_id)
        if not path.exists():
            raise LearningError(f"unknown lesson: {lesson_id}")
        return GrowthLesson.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _sort_key(lesson: GrowthLesson):
        return (lesson.business, lesson.lever, lesson.decision, lesson.lesson_id)

    def list_lessons(self) -> list[GrowthLesson]:
        out = [
            GrowthLesson.from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.lessons_dir.glob("ln-*.json"))
        ]
        return sorted(out, key=self._sort_key)

    # -- retrieval (read-only; no mutation events) -----------------------------
    def retrieve(self, business: str | None = None, lever: str | None = None,
                 decision: str | None = None,
                 objective: str | None = None) -> list[GrowthLesson]:
        """Dimensional retrieval in deterministic order.

        No vector database, no external store: JSON records filtered in
        memory and sorted by (business, lever, decision, lesson_id).
        """
        lev = getattr(lever, "value", lever)
        dec = getattr(decision, "value", decision)
        out = []
        for lesson in self.list_lessons():
            if business is not None and lesson.business != business:
                continue
            if lev is not None and lesson.lever != lev:
                continue
            if dec is not None and lesson.decision != dec:
                continue
            if objective is not None and \
                    objective.lower() not in lesson.objective.lower():
                continue
            out.append(lesson)
        return out

    # -- extraction --------------------------------------------------------------
    def learn(self, mission_id: str) -> GrowthLesson:
        """Extract and persist the lesson for a decided, measured mission.

        Idempotent: re-learning the same mission updates the single record
        (gm_lesson_updated) instead of duplicating it.
        """
        try:
            state = self.runtime.state(mission_id)
        except MissionExecutionError as exc:
            raise LearningError(str(exc)) from exc

        mission = state["mission"]
        measurements = state.get("measurements", [])
        decision = state.get("decision")
        if not measurements:
            raise LearningError(
                f"cannot learn from {mission_id}: no measurement recorded yet "
                "(run `fire growth measure` first)")
        if not decision:
            raise LearningError(
                f"cannot learn from {mission_id}: no decision recorded yet "
                "(run `fire growth decide` first)")
        if decision not in _LESSON_TEXT:
            raise LearningError(
                f"cannot learn from {mission_id}: unknown decision {decision!r}")

        latest = measurements[-1]
        overall = float(latest["overall"])
        lever = mission["lever"]
        business = mission["business_name"]
        baseline = mission.get("baseline", {})
        target = mission.get("target", {})
        progress = latest.get("progress", {})
        metrics = latest.get("metrics", {})

        steps = state.get("steps", {})
        completed = sum(1 for s in steps.values() if s.get("status") == "completed")
        total = len(mission.get("workflow", [])) or len(steps)

        # 1) observed facts (facts only, no interpretation)
        observation = (
            f"{business} ({lever}): "
            + "; ".join(
                f"{k}: baseline={baseline.get(k, 0)} "
                f"current={metrics.get(k, baseline.get(k, 0))} "
                f"target={target.get(k)} progress={progress.get(k, 0):.2f}"
                for k in target
            )
            + f"; overall progress {overall:.4f} after "
            f"{len(measurements)} measurement cycle(s)"
        )

        # 2) evidence: mission-recorded evidence + measured outcome facts
        evidence = list(mission.get("evidence", []))
        evidence += [
            f"steps completed: {completed} of {total}",
            "latest measurement: " + ", ".join(f"{k}={v}" for k, v in metrics.items()),
            "progress: " + ", ".join(f"{k}={v:.3f}" for k, v in progress.items()),
            f"recorded decision: {decision} (overall {overall:.4f})",
        ]

        # 3) measured outcome summary
        outcome = (
            f"overall progress {overall:.4f} on {len(progress)} metric(s); "
            f"mission status {mission.get('status')}; "
            f"{len(measurements)} measurement cycle(s)"
        )

        lesson_id = lesson_id_for(mission_id)
        path = self.path_for(lesson_id)
        if path.exists():
            existing = GrowthLesson.from_dict(
                json.loads(path.read_text(encoding="utf-8")))
            created_at = existing.created_at
            action = "updated"
        else:
            created_at = _now()
            action = "created"

        lesson = GrowthLesson(
            lesson_id=lesson_id,
            mission_id=mission_id,
            business=business,
            lever=lever,
            objective=mission.get("objective", ""),
            outcome=outcome,
            decision=decision,
            evidence=evidence,
            observation=observation,
            lesson=_LESSON_TEXT[decision].format(
                mid=mission_id, p=overall, lever=lever, business=business),
            recommendation=_RECOMMENDATION[decision],
            confidence=round(
                CONFIDENCE_BASE
                + CONFIDENCE_PER_CYCLE * min(len(measurements), CONFIDENCE_CAP_CYCLES),
                4),
            created_at=created_at,
            updated_at=_now(),
        )

        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lesson.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)

        # 4) audit through the existing single EventLog
        self.events.append(
            f"gm_lesson_{action}",
            {"lesson_id": lesson_id, "mission_id": mission_id,
             "business": business, "lever": lever, "decision": decision,
             "confidence": lesson.confidence},
        )
        return lesson

    def save_lesson(self, lesson: GrowthLesson) -> GrowthLesson:
        """Persist an externally constructed lesson (e.g. from a commercial
        experiment decision). Reuses the same lesson store, deterministic
        ordering and gm_lesson_* audit events as learn(); learn() and
        retrieve() semantics are unchanged. Idempotent per lesson_id."""
        path = self.path_for(lesson.lesson_id)
        if path.exists():
            existing = GrowthLesson.from_dict(
                json.loads(path.read_text(encoding="utf-8")))
            lesson.created_at = existing.created_at or lesson.created_at
            action = "updated"
        else:
            lesson.created_at = lesson.created_at or _now()
            action = "created"
        lesson.updated_at = _now()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lesson.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)
        self.events.append(
            f"gm_lesson_{action}",
            {"lesson_id": lesson.lesson_id, "mission_id": lesson.mission_id,
             "business": lesson.business, "lever": lesson.lever,
             "decision": lesson.decision, "confidence": lesson.confidence,
             "source": "external"},
        )
        return lesson
