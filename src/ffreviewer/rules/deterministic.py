"""
Deterministic (no-LLM) compliance rule checks.
Each function returns a Finding if the rule fires, or None if it does not.
"""
from __future__ import annotations
import re
from datetime import timedelta
from typing import Optional

from ..models import Finding, Session

# ---------------------------------------------------------------------------
# R-001  Reason code quality
# ---------------------------------------------------------------------------

_GENERIC_RE = re.compile(
    r"""^
    (
        test | fix | asap | urgent | issue | problem | error | bug |
        critical | important | quick | temp | na | n/?a | tbd | todo |
        done | ok | yes | no | none | emergency | hotfix |
        (see\s+)?(ticket|inc\w*|jira|sr|sr\d+) |
        prod(uction)?\s*(fix|issue|problem|error)?
    )
    [\s.!,]*$""",
    re.IGNORECASE | re.VERBOSE,
)


def check_r001(session: Session) -> Optional[Finding]:
    reason = session.reason_code.strip()
    if not reason:
        return Finding(
            rule_id="R-001",
            severity="medium",
            location="reason_code",
            description="Reason code is empty.",
            evidence="(empty)",
        )
    if len(reason) < 20:
        return Finding(
            rule_id="R-001",
            severity="medium",
            location="reason_code",
            description=f"Reason code is too short ({len(reason)} chars; minimum 20 required).",
            evidence=reason,
        )
    if _GENERIC_RE.match(reason):
        return Finding(
            rule_id="R-001",
            severity="medium",
            location="reason_code",
            description="Reason code is generic and lacks operational specifics (e.g. which system, company code, or root cause).",
            evidence=reason,
        )
    return None


# ---------------------------------------------------------------------------
# R-003  Debug & replace activity
# ---------------------------------------------------------------------------

_DEBUG_MSG_RE = re.compile(
    r"\b(/h|debug|value\s+modif|field\s+modif|replace\s+mode|abap\s+debugger)\b",
    re.IGNORECASE,
)


def check_r003(session: Session) -> Optional[Finding]:
    hits: list[str] = []

    for entry in session.transaction_log:
        if entry.tcode.strip().upper() in {"/H", "/H "}:
            hits.append(f"{entry.timestamp.isoformat()} — tcode {entry.tcode}")

    for entry in session.system_log:
        if _DEBUG_MSG_RE.search(entry.message):
            hits.append(f"{entry.timestamp.isoformat()} — {entry.message} ({entry.type})")

    if hits:
        return Finding(
            rule_id="R-003",
            severity="critical",
            location="transaction_log / system_log",
            description="Debug session detected; debug & replace cannot be ruled out without further inspection.",
            evidence="; ".join(hits[:3]),
        )
    return None


# ---------------------------------------------------------------------------
# R-004  Direct table modification
# ---------------------------------------------------------------------------

_SENSITIVE_TABLES = {
    "USR02", "USR04", "USR10", "USR12",          # user authorizations
    "LFA1", "LFB1", "LFM1",                       # vendor master
    "KNA1", "KNB1",                               # customer master
    "BSEG", "BKPF",                               # FI documents
    "REGUH", "REGUP",                             # payment data
    "PAYR",                                       # payroll results
    "T001", "T001W",                              # company code / plant
    "PA0008", "PA0014", "PA0015",                 # HR payroll infotypes
}

_DIRECT_EDIT_TCODES = {"SE16N", "SM30", "SM31"}


def check_r004(session: Session) -> Optional[Finding]:
    risky_tcodes = [
        e for e in session.transaction_log
        if e.tcode.upper() in _DIRECT_EDIT_TCODES
    ]
    sensitive_changes = [
        e for e in session.change_log
        if e.table.upper() in _SENSITIVE_TABLES
    ]
    if not risky_tcodes or not sensitive_changes:
        return None

    evidence_parts: list[str] = [
        "Direct-edit transactions: " + ", ".join(e.tcode for e in risky_tcodes[:5]),
        "Sensitive tables modified: " + ", ".join({e.table for e in sensitive_changes}),
    ]

    return Finding(
        rule_id="R-004",
        severity="high",
        location="transaction_log / change_log",
        description="Direct table modification via SE16N/SM30/SM31 on sensitive tables detected without a verified data-fix request.",
        evidence="; ".join(evidence_parts),
    )


# ---------------------------------------------------------------------------
# R-005  OS-level commands
# ---------------------------------------------------------------------------

_OS_TCODES = {"SM49", "SM69", "OS06", "SM36"}


def check_r005(session: Session) -> Optional[Finding]:
    os_cmd_entries = session.os_command_log

    os_tcode_entries = [
        e for e in session.transaction_log
        if e.tcode.upper() in _OS_TCODES
    ]

    if not os_cmd_entries and not os_tcode_entries:
        return None

    evidence_parts: list[str] = []
    if os_tcode_entries:
        evidence_parts.append(
            "OS transactions: " + ", ".join(e.tcode for e in os_tcode_entries)
        )
    if os_cmd_entries:
        evidence_parts.append(
            "Commands: " + "; ".join(e.command for e in os_cmd_entries[:3])
        )

    return Finding(
        rule_id="R-005",
        severity="critical",
        location="transaction_log / os_command_log",
        description="OS-level command execution (SM49/SM69) detected in session.",
        evidence="; ".join(evidence_parts),
    )


# ---------------------------------------------------------------------------
# R-007  Outside business hours without emergency justification
# ---------------------------------------------------------------------------

_BUSINESS_HOURS = range(7, 20)  # 07:00–19:59 UTC

_EMERGENCY_RE = re.compile(
    r"\b(emergency|outage|down|unavailable|critical|p[- ]?1|priority[- ]?1|incident|ims|major)\b",
    re.IGNORECASE,
)

_SPECIFIC_REASON_MIN_LEN = 60

def check_r007(session: Session) -> Optional[Finding]:
    start = session.start_time
    is_weekend = start.weekday() >= 5
    is_after_hours = (start.hour not in _BUSINESS_HOURS) or is_weekend

    if not is_after_hours:
        return None
    if _EMERGENCY_RE.search(session.reason_code):
        return None
    if len(session.reason_code.strip()) >= _SPECIFIC_REASON_MIN_LEN:
        return None

    day_name = start.strftime("%A")
    time_str = start.strftime("%H:%M UTC")
    return Finding(
        rule_id="R-007",
        severity="medium",
        location="start_time",
        description=f"Session started outside business hours ({day_name} {time_str}) and the reason code does not indicate an emergency.",
        evidence=f"Start: {start.isoformat()}  Reason: {session.reason_code}",
    )


# ---------------------------------------------------------------------------
# R-008  Self-approval (firefighter == ticket requester)
# ---------------------------------------------------------------------------


def check_r008(session: Session) -> Optional[Finding]:
    if (
        session.ticket_requester
        and session.ticket_requester.upper() == session.firefighter_user.upper()
    ):
        return Finding(
            rule_id="R-008",
            severity="high",
            location="firefighter_user / ticket_requester",
            description="The firefighter user and the original ticket requester are the same person (self-approval pattern).",
            evidence=f"Firefighter: {session.firefighter_user}, Requester: {session.ticket_requester}",
        )
    return None


# ---------------------------------------------------------------------------
# R-009  Session duration exceeds auto-extend limit (default 120 min)
# ---------------------------------------------------------------------------

_MAX_SESSION_MINUTES = 120


def check_r009(session: Session) -> Optional[Finding]:
    duration_min = (session.end_time - session.start_time).total_seconds() / 60
    if duration_min <= _MAX_SESSION_MINUTES:
        return None
    return Finding(
        rule_id="R-009",
        severity="medium",
        location="start_time / end_time",
        description=(
            f"Session duration ({duration_min:.0f} min) exceeds the {_MAX_SESSION_MINUTES}-min "
            "auto-extend limit with no documented re-justification."
        ),
        evidence=f"{session.start_time.isoformat()} → {session.end_time.isoformat()} ({duration_min:.0f} min)",
    )


# ---------------------------------------------------------------------------
# R-010  Segregation-of-duties (SoD) conflict pairs
# ---------------------------------------------------------------------------

# Each entry: (label, set_a, set_b) — fires when ≥1 tcode from set_a AND ≥1 from set_b appear
_SOD_PAIRS: list[tuple[str, frozenset[str], frozenset[str]]] = [
    (
        "Vendor bank data change + payment run",
        frozenset({"XK02", "FK02", "MK02"}),
        frozenset({"F110", "F-53", "F-58", "F-47", "F-48"}),
    ),
    (
        "Bank master maintenance + payment run",
        frozenset({"FI12"}),
        frozenset({"F110", "F-53"}),
    ),
    (
        "Financial period manipulation + document posting",
        frozenset({"OB52", "MMPV", "MMRV"}),
        frozenset({"FB50", "FB60", "MIRO", "F110", "F-43", "F-02"}),
    ),
]


def check_r010(session: Session) -> Optional[Finding]:
    used_tcodes = {e.tcode.upper() for e in session.transaction_log}
    triggered: list[str] = []

    for label, set_a, set_b in _SOD_PAIRS:
        hit_a = used_tcodes & set_a
        hit_b = used_tcodes & set_b
        if hit_a and hit_b:
            triggered.append(f"{label} ({', '.join(hit_a)} / {', '.join(hit_b)})")

    if triggered:
        return Finding(
            rule_id="R-010",
            severity="critical",
            location="transaction_log",
            description="Session contains known SoD-conflict transaction pairs that should never be executed by the same person.",
            evidence="; ".join(triggered),
        )
    return None


# ---------------------------------------------------------------------------
# R-011  Authorization / privilege-management transactions  (additional)
# ---------------------------------------------------------------------------

_AUTH_TCODES_HIGH_RISK = {"PFCG", "SU24", "SU25", "RZ10", "SU10"}
_AUTH_TABLES = {"USR02", "USR04", "USR10", "USR12", "AGR_USERS", "AGR_1251"}


def check_r011(session: Session) -> Optional[Finding]:
    hits = [e for e in session.transaction_log if e.tcode.upper() in _AUTH_TCODES_HIGH_RISK]
    if not hits:
        return None
    auth_changes = [e for e in session.change_log if e.table.upper() in _AUTH_TABLES]
    if not auth_changes:
        return None
    tcodes = ", ".join(e.tcode for e in hits)
    tables = ", ".join({e.table for e in auth_changes})
    return Finding(
        rule_id="R-011",
        severity="critical",
        location="transaction_log / change_log",
        description="Authorization/role-management transactions with confirmed auth-table writes detected — privilege-escalation risk.",
        evidence=f"Transactions: {tcodes}; Auth tables modified: {tables}",
    )


# ---------------------------------------------------------------------------
# R-012  Transport/change-management activity without CR reference  (additional)
# ---------------------------------------------------------------------------

_TRANSPORT_TCODES = {"SE10", "SE09", "STMS", "SPDD", "SPAU", "SE01", "SE06"}
_TRANSPORT_REASON_RE = re.compile(
    r"\b(transport|tr[- ]?\d{10}|change\s+request|workbench\s+request)\b",
    re.IGNORECASE,
)


def check_r012(session: Session) -> Optional[Finding]:
    hits = [e for e in session.transaction_log if e.tcode.upper() in _TRANSPORT_TCODES]
    if not hits:
        return None
    if _TRANSPORT_REASON_RE.search(session.reason_code):
        return None  # reason explicitly mentions the transport

    tcodes = ", ".join(e.tcode for e in hits)
    return Finding(
        rule_id="R-012",
        severity="high",
        location="transaction_log",
        description="Transport/change-management transactions executed without a transport reference in the reason code; transports must go through the standard change-management process.",
        evidence=f"Transactions: {tcodes}",
    )


# ---------------------------------------------------------------------------
# R-013  Change-log timestamps outside session window  (additional)
# ---------------------------------------------------------------------------

_CLOCK_TOLERANCE = timedelta(minutes=5)


def check_r013(session: Session) -> Optional[Finding]:
    window_start = session.start_time - _CLOCK_TOLERANCE
    window_end = session.end_time + _CLOCK_TOLERANCE
    anomalies = [
        e for e in session.change_log
        if e.timestamp < window_start or e.timestamp > window_end
    ]
    if not anomalies:
        return None

    evidence = "; ".join(
        f"{e.timestamp.isoformat()} ({e.table}.{e.field})" for e in anomalies[:3]
    )
    return Finding(
        rule_id="R-013",
        severity="medium",
        location="change_log",
        description=(
            f"{len(anomalies)} change-log entr{'y' if len(anomalies) == 1 else 'ies'} "
            "have timestamps outside the session window, indicating possible log anomaly or clock skew."
        ),
        evidence=evidence,
    )
