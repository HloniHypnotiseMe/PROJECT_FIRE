"""FIRE configuration loader (JSON to stay dependency-free)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "root": str(Path(__file__).resolve().parent.parent),
    "agent_library": "agents/agency-agents",
    "registry_file": "registry/agent_registry.json",
    "memory_dir": "memory",
    "reports_dir": "reports",
    "artifacts_dir": "artifacts",
    "dashboard_dir": "control_room",
    "north_star_daily_zar": 1_000_000,
    "currency": "ZAR",
    "max_team_size": 6,
}


def load_config(path: str | None = None) -> dict:
    root = Path(__file__).resolve().parent.parent
    cfg_path = Path(path) if path else root / "config" / "fire.json"
    cfg = dict(DEFAULTS)
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception as exc:  # pragma: no cover
            print(f"[fire] warning: could not read {cfg_path}: {exc}")
    return cfg


def paths(cfg: dict) -> dict:
    """Resolve all configured paths relative to project root."""
    root = Path(cfg["root"])
    out = {}
    for key in ("agent_library", "registry_file", "memory_dir", "reports_dir",
                "artifacts_dir", "dashboard_dir"):
        out[key] = root / cfg[key]
    return out
