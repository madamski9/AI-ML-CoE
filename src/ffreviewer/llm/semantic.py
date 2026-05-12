from .client import generate_json


def classify_reason_module(reason_code: str) -> str:
    data = generate_json(
        system=(
            "You classify SAP firefighter reason codes into the primary SAP module they refer to.\n"
            "Modules: FI (Finance/Accounting), MM (Materials Management/Procurement), "
            "SD (Sales & Distribution), HR (Human Resources/Payroll), "
            "BC (Basis/Technical/System Administration), UNKNOWN (cannot determine).\n"
            "Return JSON: {\"module\": \"FI|MM|SD|HR|BC|UNKNOWN\", \"confidence\": 0.0}"
        ),
        user=f"Reason Code: {reason_code}",
    )
    return data.get("module", "UNKNOWN")


def generate_correction(session: dict, findings: list) -> dict:
    findings_summary = "\n".join(
        f"- [{f['rule_id']}] {f['severity'].upper()}: {f['description']}"
        for f in findings
    )
    transactions = ", ".join(
        e["tcode"] for e in session.get("transaction_log", [])[:10]
    )
    data = generate_json(
        system=(
            "You are an SAP GRC compliance expert helping controllers communicate with firefighters.\n"
            "Given a session summary and its compliance findings, produce:\n"
            "1. A clear, professional message to the firefighter listing exactly what information "
            "is missing or needs clarification.\n"
            "2. A suggested rewrite of their reason code that would pass compliance review. "
            "The rewrite must include: the specific transaction/process affected, company code or plant "
            "(if applicable), the root cause, and actions taken.\n"
            "Return JSON: {\"message_to_firefighter\": \"...\", \"suggested_reason_rewrite\": \"...\"}"
        ),
        user=(
            f"Session ID: {session['session_id']}\n"
            f"Original Reason: {session['reason_code']}\n"
            f"Ticket: {session.get('ticket_reference', 'N/A')}\n"
            f"Transactions: {transactions}\n\n"
            f"Findings:\n{findings_summary}"
        ),
    )
    return {
        "message_to_firefighter": data.get("message_to_firefighter", ""),
        "suggested_reason_rewrite": data.get("suggested_reason_rewrite", ""),
    }
