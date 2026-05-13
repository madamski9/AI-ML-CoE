from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from ffreviewer.engine import review_session
from ffreviewer.models import Session

_DECISIONS_FILE = Path(__file__).parent.parent / "decisions.jsonl"
_decisions: dict[str, dict] = {}

app = FastAPI(title="FF Reviewer")


class DecisionBody(BaseModel):
    decision: Literal["PASS", "REJECT", "SEND_BACK"]
    notes: str = ""


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.post("/review")
async def review(file: UploadFile = File(...)):
    content = await file.read()
    try:
        session = Session.model_validate_json(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    verdict = review_session(session)
    return verdict.model_dump(mode="json")


@app.post("/decisions/{session_id}")
async def record_decision(session_id: str, body: DecisionBody):
    record = {
        "session_id": session_id,
        "decision": body.decision,
        "notes": body.notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _decisions[session_id] = record
    with _DECISIONS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return {"ok": True}


@app.get("/decisions")
async def list_decisions():
    return list(_decisions.values())