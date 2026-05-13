from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from ffreviewer.engine import review_session
from ffreviewer.models import Session, Verdict

_DECISIONS_FILE = Path(__file__).parent.parent / "decisions.jsonl"

_SEV_COLOR = {
    "critical": ("#fef2f2", "#dc2626"),
    "high":     ("#fff7ed", "#ea580c"),
    "medium":   ("#fefce8", "#ca8a04"),
    "low":      ("#eff6ff", "#2563eb"),
}
_VERDICT_COLOR = {
    "PASS":             ("#f0fdf4", "#16a34a"),
    "REJECT":           ("#fef2f2", "#dc2626"),
    "NEEDS_CORRECTION": ("#fff7ed", "#ea580c"),
}
_VERDICT_ICON = {
    "PASS": "✅",
    "REJECT": "❌",
    "NEEDS_CORRECTION": "⚠️",
}


def save_decision(session_id: str, decision: str) -> None:
    record = {
        "session_id": session_id,
        "decision": decision,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _DECISIONS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def render_finding(finding) -> None:
    bg, border = _SEV_COLOR.get(finding.severity, ("#f8fafc", "#64748b"))
    st.markdown(
        f"""<div style="border-left:4px solid {border};background:{bg};
            border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:10px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
            <code style="background:#e2e8f0;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;">
              {finding.rule_id}</code>
            <span style="background:{border}22;color:{border};font-size:11px;font-weight:700;
              padding:2px 9px;border-radius:12px;text-transform:uppercase;">{finding.severity}</span>
            <span style="color:#64748b;font-size:12px;">{finding.location}</span>
          </div>
          <p style="margin:0 0 8px;font-size:14px;color:#1e293b;line-height:1.5;">{finding.description}</p>
          <code style="display:block;background:#e2e8f0;padding:8px 11px;border-radius:6px;
            font-size:12px;color:#475569;word-break:break-all;white-space:pre-wrap;">{finding.evidence}</code>
        </div>""",
        unsafe_allow_html=True,
    )


def render_verdict(v: Verdict) -> None:
    bg, color = _VERDICT_COLOR[v.verdict]
    icon = _VERDICT_ICON[v.verdict]

    col_v, col_c = st.columns([3, 1])
    with col_v:
        st.markdown(
            f"""<div style="background:{bg};border:1.5px solid {color};border-radius:10px;padding:18px 22px;">
              <p style="margin:0 0 2px;font-size:12px;color:#64748b;">Session ID</p>
              <p style="margin:0 0 8px;font-weight:600;color:#334155;">{v.session_id}</p>
              <p style="margin:0;font-size:26px;font-weight:800;color:{color};">{icon} {v.verdict.replace("_", " ")}</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col_c:
        pct = int(v.confidence * 100)
        st.metric("Confidence", f"{pct}%")
        st.progress(v.confidence)

    st.markdown("")

    if v.findings:
        st.markdown(f"### Findings &nbsp; `{len(v.findings)}`", unsafe_allow_html=True)
        for f in sorted(v.findings, key=lambda x: ["critical","high","medium","low"].index(x.severity)):
            render_finding(f)
    else:
        st.success("No compliance issues detected.")

    if v.suggested_correction:
        st.markdown("### Suggested Correction")
        with st.container(border=True):
            st.markdown("**Message to firefighter**")
            st.info(v.suggested_correction.message_to_firefighter)
            if v.suggested_correction.suggested_reason_rewrite:
                st.markdown("**Suggested reason rewrite**")
                st.success("✎ &nbsp;" + v.suggested_correction.suggested_reason_rewrite)

    st.divider()
    st.markdown("#### Controller Decision")

    if st.session_state.get("decision_done"):
        decision = st.session_state["decision_done"]
        st.success(f"✓ Decision recorded: **{decision.replace('_', ' ')}**")
        if st.button("Review another session"):
            del st.session_state["verdict"]
            del st.session_state["decision_done"]
            st.rerun()
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✓  PASS", use_container_width=True, type="primary"):
            save_decision(v.session_id, "PASS")
            st.session_state["decision_done"] = "PASS"
            st.rerun()
    with c2:
        if st.button("✗  REJECT", use_container_width=True):
            save_decision(v.session_id, "REJECT")
            st.session_state["decision_done"] = "REJECT"
            st.rerun()
    with c3:
        if st.button("↩  SEND BACK", use_container_width=True):
            save_decision(v.session_id, "SEND_BACK")
            st.session_state["decision_done"] = "SEND_BACK"
            st.rerun()


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SAP FF Reviewer",
    page_icon="🛡️",
    layout="centered",
)

st.markdown(
    "<h2 style='margin-bottom:2px'>🛡️ SAP Firefighter Log Reviewer</h2>"
    "<p style='color:#64748b;margin-top:0'>Compliance Screening Tool &nbsp;·&nbsp; Seargin AMS CoE</p>",
    unsafe_allow_html=True,
)
st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────

if "verdict" not in st.session_state:
    uploaded = st.file_uploader(
        "Upload session JSON",
        type=["json"],
        help="Single FF session file, e.g. FF-TRAIN-0001.json",
    )
    if uploaded:
        if st.button("▶ Run Review", type="primary", use_container_width=True):
            with st.spinner("Analyzing session…"):
                try:
                    session = Session.model_validate_json(uploaded.read())
                    verdict = review_session(session)
                    st.session_state["verdict"] = verdict
                    st.session_state["decision_done"] = None
                    st.rerun()
                except Exception as exc:
                    st.error(f"**Error parsing session:** {exc}")
else:
    render_verdict(st.session_state["verdict"])
