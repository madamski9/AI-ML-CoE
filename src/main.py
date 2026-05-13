from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from ffreviewer.engine import review_session
from ffreviewer.models import Session

_DECISIONS_FILE = Path(__file__).parent.parent / "decisions.jsonl"
_decisions: dict[str, dict] = {}
_verdicts: dict[str, dict] = {}  # keyed by session_id, populated by /review

app = FastAPI(title="FF Reviewer")


class DecisionBody(BaseModel):
    decision: Literal["PASS", "REJECT", "SEND_BACK"]
    notes: str = ""


@app.post("/review")
async def review(file: UploadFile = File(...)):
    content = await file.read()
    try:
        session = Session.model_validate_json(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    verdict = review_session(session)
    result = verdict.model_dump(mode="json")
    _verdicts[verdict.session_id] = result
    return result


@app.post("/decisions/{session_id}")
async def record_decision(session_id: str, body: DecisionBody):
    ai = _verdicts.get(session_id, {})
    record = {
        "session_id": session_id,
        "controller_decision": body.decision,
        "controller_notes": body.notes,
        "ai_verdict": ai.get("verdict"),
        "ai_confidence": ai.get("confidence"),
        "override": body.decision != ai.get("verdict") and not (
            body.decision == "SEND_BACK" and ai.get("verdict") == "NEEDS_CORRECTION"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "findings": ai.get("findings", []),
        "suggested_correction": ai.get("suggested_correction"),
    }
    _decisions[session_id] = record
    with _DECISIONS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return {"ok": True}


@app.get("/decisions")
async def list_decisions():
    return list(_decisions.values())