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


class IncidentStatus(str, Enum):
    TRIGGERED = "TRIGGERED"
    INVESTIGATING = "INVESTIGATING"
    PATCH_READY = "PATCH_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


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
    trust_score: float = 95.0  # Percentage confidence/safety
    audit_logs: List[str] = Field(default_factory=list)


class SwitchMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str
    sender_role: str  # "commander", "remediator", "human", "system"
    sender_name: str
    content: str
    code_snippet: Optional[str] = None
    actions: List[ActionButton] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    telemetry: Optional[TrustTelemetry] = None


class CodePatch(BaseModel):
    file_path: str
    original_code: str
    patched_code: str
    unified_diff: str
    test_code: str
    test_output: str
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH


class Incident(BaseModel):
    id: str
    alert: IncidentAlert
    status: IncidentStatus = IncidentStatus.TRIGGERED
    assigned_commander: str = "incident-commander"
    assigned_remediator: str = "code-remediator"
    switch_room_id: str = "incident-war-room"
    patch: Optional[CodePatch] = None
    messages: List[SwitchMessage] = Field(default_factory=list)
    rca_document: Optional[str] = None
    telemetry: TrustTelemetry = Field(default_factory=TrustTelemetry)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
