"""
Main review orchestrator.

Usage:
    from ffreviewer.engine import review_session
    from ffreviewer.models import Session

    session = Session.model_validate_json(open("session.json").read())
    verdict = review_session(session)
    print(verdict.model_dump_json(indent=2))
"""
from __future__ import annotations

from .models import Finding, Session, SuggestedCorrection, Verdict
from .rules.deterministic import (
    check_r001,
    check_r003,
    check_r004,
    check_r005,
    check_r007,
    check_r008,
    check_r009,
    check_r010,
    check_r011,
    check_r012,
    check_r013,
)
from .rules.semantic_checks import check_r002, check_r006
from .llm.semantic import generate_correction

_DETERMINISTIC_CHECKS = [
    check_r001,
    check_r003,
    check_r004,
    check_r005,
    check_r007,
    check_r008,
    check_r009,
    check_r010,
    check_r011,
    check_r012,
    check_r013,
]

_SEMANTIC_CHECKS = [
    check_r002,
    check_r006,
]


def review_session(session: Session) -> Verdict:
    findings: list[Finding] = []

    for check_fn in _DETERMINISTIC_CHECKS:
        finding = check_fn(session)
        if finding:
            findings.append(finding)

    # Semantic checks use the LLM — skip gracefully if unavailable
    for check_fn in _SEMANTIC_CHECKS:
        try:
            finding = check_fn(session)
            if finding:
                findings.append(finding)
        except Exception:
            pass

    verdict_label, confidence = _determine_verdict(findings)

    correction: SuggestedCorrection | None = None
    if verdict_label == "NEEDS_CORRECTION":
        try:
            result = generate_correction(
                session.model_dump(mode="json"),
                [f.model_dump() for f in findings],
            )
            correction = SuggestedCorrection(
                message_to_firefighter=result["message_to_firefighter"],
                suggested_reason_rewrite=result["suggested_reason_rewrite"],
            )
        except Exception:
            pass

    return Verdict(
        session_id=session.session_id,
        verdict=verdict_label,
        confidence=confidence,
        findings=findings,
        suggested_correction=correction,
    )


def _determine_verdict(findings: list[Finding]) -> tuple[str, float]:
    if not findings:
        return "PASS", 0.93

    severities = [f.severity for f in findings]

    if "critical" in severities:
        return "REJECT", 0.91

    high_count = severities.count("high")
    if high_count >= 2:
        return "REJECT", 0.86
    if high_count == 1:
        return "NEEDS_CORRECTION", 0.76

    medium_count = severities.count("medium")
    if medium_count >= 1:
        return "NEEDS_CORRECTION", 0.70

    # low findings only
    return "PASS", 0.80
