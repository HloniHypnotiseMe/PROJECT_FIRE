"""Memory: durable record of missions, decisions, executions and lessons.

JSONL append-only store — safe, diffable, and trivially queryable.
FIRE learns from execution; memory feeds better future decisions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import MissionRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventLog:
    def __init__(self, memory_dir: Path):
        self.dir = memory_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.missions_path = self.dir / "missions.jsonl"

    # -- generic events ----------------------------------------------------
    def append(self, etype: str, payload: dict[str, Any]) -> dict:
        ev = {"ts": _now(), "type": etype, **payload}
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev) + "\n")
        return ev

    def list(self, etype: Optional[str] = None, limit: int = 200) -> list[dict]:
        out = []
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if etype is None or ev.get("type") == etype:
                    out.append(ev)
        return out[-limit:]

    # -- missions ----------------------------------------------------------
    def start_mission(self, objective: str, intent: str, team: list[dict]) -> MissionRecord:
        rec = MissionRecord(
            mission_id="M-" + uuid.uuid4().hex[:8].upper(),
            objective=objective, intent=intent, status="running",
            team=team, created_at=_now(),
        )
        self._write_mission(rec)
        self.append("mission_started", {"mission_id": rec.mission_id, "objective": objective})
        return rec

    def update_mission(self, mission_id: str, **fields) -> Optional[MissionRecord]:
        recs = self.all_missions()
        target = next((r for r in recs if r.mission_id == mission_id), None)
        if target is None:
            return None
        for k, v in fields.items():
            if hasattr(target, k):
                setattr(target, k, v)
        self._rewrite_missions(recs)
        return target

    def _write_mission(self, rec: MissionRecord):
        with open(self.missions_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict()) + "\n")

    def _rewrite_missions(self, recs: list[MissionRecord]):
        with open(self.missions_path, "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r.to_dict()) + "\n")

    def all_missions(self) -> list[MissionRecord]:
        out = []
        if self.missions_path.exists():
            for line in self.missions_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    out.append(MissionRecord(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue
        return out

    def add_lesson(self, lesson: str, mission_id: Optional[str] = None):
        payload = {"lesson": lesson}
        if mission_id:
            payload["mission_id"] = mission_id
        self.append("lesson", payload)
