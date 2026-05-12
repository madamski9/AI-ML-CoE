from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime


class TransactionEntry(BaseModel):
    timestamp: datetime
    tcode: str
    description: str = ""


class ChangeEntry(BaseModel):
    timestamp: datetime
    table: str
    key: str
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class SystemLogEntry(BaseModel):
    timestamp: datetime
    message: str
    type: str = ""


class OsCommandEntry(BaseModel):
    timestamp: datetime
    command: str
    user: Optional[str] = None


class Session(BaseModel):
    session_id: str
    firefighter_id: str
    firefighter_user: str
    controller: str
    system: str
    client: str
    start_time: datetime
    end_time: datetime
    reason_code: str
    ticket_reference: Optional[str] = None
    ticket_requester: Optional[str] = None
    transaction_log: List[TransactionEntry] = Field(default_factory=list)
    change_log: List[ChangeEntry] = Field(default_factory=list)
    system_log: List[SystemLogEntry] = Field(default_factory=list)
    os_command_log: List[OsCommandEntry] = Field(default_factory=list)


class Finding(BaseModel):
    rule_id: str
    severity: Literal["low", "medium", "high", "critical"]
    location: str
    description: str
    evidence: str


class SuggestedCorrection(BaseModel):
    message_to_firefighter: str
    suggested_reason_rewrite: str


class Verdict(BaseModel):
    session_id: str
    verdict: Literal["PASS", "REJECT", "NEEDS_CORRECTION"]
    confidence: float = Field(ge=0.0, le=1.0)
    findings: List[Finding] = Field(default_factory=list)
    suggested_correction: Optional[SuggestedCorrection] = None
