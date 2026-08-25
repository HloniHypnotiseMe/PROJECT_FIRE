"""Quality / Reality Engine.

FIRE must NOT become a bullshit amplifier. This module independently evaluates
artifacts, plans and claims against evidence, feasibility, economics and
execution quality, and returns GO / REVISE / NO-GO verdicts.

Creator/reviewer separation: an output produced by an executor agent is
evaluated here by a different path (independent checks, not the same prompt).
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import CheckResult, Evaluation

FORBIDDEN_CLAIMS = [
    (r"R\s?1[,\s]?000[,\s]?000\s*/?\s*day", "R1M/day claimed as achieved (it is a capacity target)"),
    (r"guaranteed\s+(revenue|income|results)", "guarantee claim"),
    (r"100%\s+(success|accurate|guaranteed)", "absolute certainty claim"),
]

# phrases that neutralize a forbidden-claim hit (the claim is disclaimed)
_NEGATIONS = (
    "not", "no ", "never", "target", "capacity", "hypothesis", "disclaimer",
    "not realised", "not claimed", "model", "illustration", "illustrative",
)

REQUIRED_REPORT_SECTIONS = [
    "opportunity ranking", "evidence", "economics", "customer", "problem",
    "proposed solution", "validation experiment", "required agent team",
    "execution workflow", "success criteria", "kill criteria", "scale criteria",
]


def evaluate_artifact(path: str | Path,
                      required_sections: list[str] | None = None,
                      forbid_claims: bool = True,
                      min_bytes: int = 200) -> Evaluation:
    p = Path(path)
    checks: list[CheckResult] = []

    checks.append(CheckResult("file_exists", p.exists()))
    if not p.exists():
        return Evaluation(verdict="NO-GO", checks=checks, summary="Artifact does not exist")

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        checks.append(CheckResult("readable", False, str(exc)))
        return Evaluation(verdict="NO-GO", checks=checks, summary="Artifact unreadable")

    size_ok = len(text.encode("utf-8")) >= min_bytes
    checks.append(CheckResult("non_trivial_size", size_ok, f"{len(text)} chars"))

    if required_sections:
        low = text.lower()
        missing = [s for s in required_sections if s not in low]
        checks.append(CheckResult("required_sections", not missing,
                                  "missing: " + ", ".join(missing) if missing else "all present"))

    if forbid_claims:
        violations = []
        for pattern, msg in FORBIDDEN_CLAIMS:
            for m in re.finditer(pattern, text, re.I):
                ctx = text[max(0, m.start() - 60): m.end() + 60].lower()
                if any(neg in ctx for neg in _NEGATIONS):
                    continue  # explicitly disclaimed in context
                violations.append(msg)
                break
        checks.append(CheckResult("no_forbidden_claims", not violations,
                                  "; ".join(violations) if violations else "clean"))

    # evidence criterion: any external citations present?
    has_citations = bool(re.search(r"https?://", text)) or bool(re.search(r"\[\d+\]\(http", text))
    checks.append(CheckResult("has_citations", has_citations,
                              "cited sources found" if has_citations else "no external citations"))

    failed = [c for c in checks if not c.passed]
    if not failed:
        verdict = "GO"
    elif len(failed) <= 1 and (not any(c.name == "no_forbidden_claims" and not c.passed for c in failed)):
        verdict = "REVISE"
    else:
        verdict = "NO-GO"

    summary = f"{len(checks) - len(failed)}/{len(checks)} checks passed"
    return Evaluation(verdict=verdict, checks=checks, summary=summary)


def evaluate_opportunity(opp: dict, min_score: float = 6.5) -> Evaluation:
    """Gate an opportunity before money or build time is committed."""
    checks: list[CheckResult] = []
    checks.append(CheckResult("has_name", bool(opp.get("name"))))
    checks.append(CheckResult("has_problem", bool(opp.get("problem"))))
    checks.append(CheckResult("has_customer", bool(opp.get("customer"))))
    checks.append(CheckResult("has_pricing", bool(opp.get("pricing"))))
    checks.append(CheckResult("has_validation_experiment", bool(opp.get("validation_experiment"))))
    checks.append(CheckResult("has_kill_criteria", bool(opp.get("kill_criteria"))))
    checks.append(CheckResult("score_above_gate", float(opp.get("weighted_score", 0)) >= min_score,
                              f"score={opp.get('weighted_score')} gate={min_score}"))

    failed = [c for c in checks if not c.passed]
    if not failed:
        verdict = "GO"
    elif len(failed) <= 2:
        verdict = "REVISE"
    else:
        verdict = "NO-GO"
    return Evaluation(
        verdict=verdict,
        checks=checks,
        summary=f"{len(checks)-len(failed)}/{len(checks)} checks passed",
    )
