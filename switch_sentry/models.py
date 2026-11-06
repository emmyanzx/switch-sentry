"""Data models and schemas for Switch Sentry."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    P0 = "P0 - Critical"
    P1 = "P1 - High"
    P2 = "P2 - Medium"
    P3 = "P3 - Low"


class IncidentStage(str, Enum):
    TRIAGE = "1. Triage & Confirmation"
    PLANNING = "2. Solution Plan"
    REMEDIATION = "3. Patch Delivery"
    PEER_REVIEW = "4. Independent QA (goodToMerge)"
    AWAITING_APPROVAL = "5. Human Sign-Off Gate"
    RESOLVED = "6. Resolved & Mistake Logged"
    REJECTED = "Rejected"


class ActionButton(BaseModel):
    action_id: str
    label: str
    style: str = "primary"  # primary, danger, secondary


class TrustTelemetry(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    trust_score: float = 98.5
    audit_logs: List[str] = Field(default_factory=list)


class SwitchMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str
    sender_role: str  # "commander", "remediator", "verifier", "human", "system"
    sender_name: str
    content: str
    code_snippet: Optional[str] = None
    actions: List[ActionButton] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    telemetry: Optional[TrustTelemetry] = None


class SolutionPlan(BaseModel):
    approach: str
    affected_files: List[str]
    risk_level: str = "LOW"
    estimated_effort: str = "15 min"


class CodePatch(BaseModel):
    file_path: str
    original_code: str
    patched_code: str
    unified_diff: str
    test_code: str
    test_output: str
    risk_level: str = "LOW"


class PeerReviewVerdict(BaseModel):
    reviewer_name: str = "qa-verifier"
    is_good_to_merge: bool = True
    tests_executed: List[str] = Field(default_factory=list)
    verdict_summary: str
    confidence_score: float = 98.0


class MistakeEntry(BaseModel):
    id: str
    title: str
    anti_pattern: str
    root_cause: str
    prevention_rule: str
    timestamp: float = Field(default_factory=time.time)


class IncidentAlert(BaseModel):
    id: str = Field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:6].upper()}")
    title: str
    service: str
    severity: IncidentSeverity = IncidentSeverity.P1
    error_name: str
    error_message: str
    stack_trace: str
    affected_file: str
    line_number: int
    repo_url: str = "github.com/org/checkout-service"
    commit_hash: str = "e4f8b91"
    timestamp: float = Field(default_factory=time.time)


class Incident(BaseModel):
    id: str
    alert: IncidentAlert
    stage: IncidentStage = IncidentStage.TRIAGE
    assigned_commander: str = "incident-commander"
    assigned_remediator: str = "code-remediator"
    assigned_verifier: str = "qa-verifier"
    switch_room_id: str = "incident-war-room"
    switch_room_uuid: Optional[str] = None
    plan: Optional[SolutionPlan] = None
    patch: Optional[CodePatch] = None
    verdict: Optional[PeerReviewVerdict] = None
    messages: List[SwitchMessage] = Field(default_factory=list)
    rca_document: Optional[str] = None
    mistake_entry: Optional[MistakeEntry] = None
    telemetry: TrustTelemetry = Field(default_factory=TrustTelemetry)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
