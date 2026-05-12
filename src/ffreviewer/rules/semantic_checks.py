"""
LLM-backed compliance rule checks.
These are called only after deterministic checks because they incur an LLM request.
"""
from __future__ import annotations
from typing import Optional

from ..models import Finding, Session
from ..llm.client import generate_json
from ..llm.semantic import classify_reason_module

# ---------------------------------------------------------------------------
# R-002  Module mismatch between reason code and actual transactions
# ---------------------------------------------------------------------------

# Best-effort mapping from tcode prefix / known codes → SAP module
_TCODE_MODULE: dict[str, str] = {
    # FI
    "F110": "FI", "FB50": "FI", "FB01": "FI", "FB02": "FI", "FBL1N": "FI",
    "FBL3N": "FI", "FBL5N": "FI", "FI12": "FI", "F-53": "FI", "F-58": "FI",
    "F-47": "FI", "F-48": "FI", "F-43": "FI", "OB52": "FI",
    "MIRO": "FI", "MR11": "FI", "MRRL": "FI",
    # MM
    "MIGO": "MM", "ME21N": "MM", "ME21": "MM", "ME23N": "MM", "ME25": "MM",
    "ME51N": "MM", "ME2N": "MM", "MB51": "MM", "MMPV": "MM", "MMRV": "MM",
    "XK01": "MM", "XK02": "MM", "XK05": "MM", "MK01": "MM", "MK02": "MM",
    # SD
    "VA01": "SD", "VA02": "SD", "VF01": "SD", "VF02": "SD",
    "VK11": "SD", "VL01N": "SD", "VL02N": "SD",
    # HR
    "PA30": "HR", "PA20": "HR", "PC00": "HR", "PU12": "HR",
    # BC (Basis/Technical)
    "SM49": "BC", "SM69": "BC", "SE16N": "BC", "SM30": "BC", "SM31": "BC",
    "SU01": "BC", "SU10": "BC", "PFCG": "BC", "SE10": "BC", "SE09": "BC",
    "STMS": "BC", "RZ10": "BC", "SM21": "BC",
    # Vendor master is shared FI/MM — treated as MM for module check
    "FK01": "MM", "FK02": "MM",
}


def _infer_session_modules(session: Session) -> set[str]:
    modules: set[str] = set()
    for entry in session.transaction_log:
        mod = _TCODE_MODULE.get(entry.tcode.upper())
        if mod:
            modules.add(mod)
    return modules


def check_r002(session: Session) -> Optional[Finding]:
    reason_module = classify_reason_module(session.reason_code)
    if reason_module == "UNKNOWN":
        return None

    session_modules = _infer_session_modules(session)
    if not session_modules:
        return None

    if reason_module in session_modules:
        return None

    tcodes_sample = ", ".join(e.tcode for e in session.transaction_log[:6])
    return Finding(
        rule_id="R-002",
        severity="high",
        location="reason_code / transaction_log",
        description=(
            f"Reason code implies {reason_module} activity but transactions touch "
            f"{', '.join(sorted(session_modules))}."
        ),
        evidence=f"Reason: '{session.reason_code}' → classified as {reason_module}; Transactions: {tcodes_sample}",
    )


# ---------------------------------------------------------------------------
# R-006  Transaction/change volume disproportionate to stated reason
# ---------------------------------------------------------------------------

_LOW_VOLUME_THRESHOLD_CHANGES = 10
_LOW_VOLUME_THRESHOLD_TCODES = 20


def check_r006(session: Session) -> Optional[Finding]:
    change_count = len(session.change_log)
    tcode_count = len(session.transaction_log)

    # Skip LLM call for clearly low-volume sessions
    if change_count < _LOW_VOLUME_THRESHOLD_CHANGES and tcode_count < _LOW_VOLUME_THRESHOLD_TCODES:
        return None

    unique_tcodes = ", ".join(sorted({e.tcode for e in session.transaction_log}))
    modified_tables = ", ".join(sorted({e.table for e in session.change_log}))

    data = generate_json(
        system=(
            "You are an SAP compliance expert. Assess whether the volume of activity in a "
            "firefighter session is proportionate to the stated reason.\n"
            "Return JSON: {\"anomaly\": true/false, \"explanation\": \"...\", \"confidence\": 0.0}"
        ),
        user=(
            f"Reason: {session.reason_code}\n"
            f"Transaction count: {tcode_count}\n"
            f"Change-document count: {change_count}\n"
            f"Transactions used: {unique_tcodes}\n"
            f"Tables modified: {modified_tables}\n\n"
            "Is the volume of activity proportionate to the stated reason?"
        ),
    )

    if data.get("anomaly") and float(data.get("confidence", 0)) > 0.6:
        return Finding(
            rule_id="R-006",
            severity="high",
            location="transaction_log / change_log",
            description=f"Volume anomaly: {data['explanation']}",
            evidence=(
                f"{change_count} change documents, {tcode_count} transactions "
                f"for reason: '{session.reason_code}'"
            ),
        )
    return None
