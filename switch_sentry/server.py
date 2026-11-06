"""FastAPI Backend for Switch Sentry War Room."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from switch_sentry.agents.commander import IncidentCommander
from switch_sentry.agents.remediator import CodeRemediator
from switch_sentry.agents.verifier import QAVerifier
from switch_sentry.mistakes import MISTAKE_REGISTRY
from switch_sentry.models import (
    ActionButton,
    Incident,
    IncidentAlert,
    IncidentSeverity,
    IncidentStage,
)
from switch_sentry.sample_incidents import SAMPLE_INCIDENTS
from switch_sentry.switch_bridge import SwitchBridge
from switch_sentry.telemetry import TrustMonitor

app = FastAPI(
    title="Switch Sentry",
    description="Multi-Agent Incident Response & Quality Governance Squad powered by Switch",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INCIDENTS: Dict[str, Incident] = {}
MONITORS: Dict[str, TrustMonitor] = {}

bridge = SwitchBridge()
remediator = CodeRemediator()
verifier = QAVerifier()
commander = IncidentCommander(bridge=bridge, remediator=remediator, verifier=verifier)

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


class TriggerRequest(BaseModel):
    preset_id: Optional[str] = None
    title: Optional[str] = None
    service: Optional[str] = None
    severity: Optional[str] = None
    error_name: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    affected_file: Optional[str] = None
    line_number: Optional[int] = 1


class ActionRequest(BaseModel):
    action: str  # approve, reject, request_alternative
    user_name: str = "Lead Engineer (You)"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Switch Sentry Backend Running</h1>"


@app.get("/api/presets")
async def get_presets():
    """Returns available demo incident scenarios."""
    return [
        {
            "id": inc.id,
            "title": inc.title,
            "service": inc.service,
            "severity": inc.severity.value,
            "error_name": inc.error_name,
        }
        for inc in SAMPLE_INCIDENTS
    ]


@app.get("/api/mistakes")
async def get_mistakes():
    """Returns the living Project Mistake Registry."""
    return MISTAKE_REGISTRY.get_all()


@app.get("/api/switch/status")
async def get_switch_status():
    """Reports status of the live Switch Agent Bridge."""
    live = await bridge.check_live_connection()
    return {
        "switch_bridge_mode": "Live Switch Core (Docker)" if live else "Embedded Standalone Hub",
        "live_connected": live,
        "endpoint": bridge.switch_url,
        "registered_agents": list(bridge._registered_agents.keys()),
        "mattermost_mirror": "http://localhost:8065" if live else None,
    }


@app.get("/api/incidents")
async def list_incidents():
    """Lists all incidents and their current statuses."""
    return list(INCIDENTS.values())


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Retrieves full incident details, timeline, diff, and telemetry."""
    if incident_id not in INCIDENTS:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    incident = INCIDENTS[incident_id]
    monitor = MONITORS.get(incident_id)
    if monitor:
        incident.telemetry = monitor.get_snapshot()
    return incident


@app.post("/api/incidents/trigger")
async def trigger_incident(req: TriggerRequest):
    """Triggers a new incident and initiates autonomous squad triage."""
    alert: Optional[IncidentAlert] = None

    if req.preset_id:
        for p in SAMPLE_INCIDENTS:
            if p.id == req.preset_id:
                alert = p.copy(deep=True)
                alert.id = f"{p.id}-{int(time.time() % 1000)}"
                break
    
    if not alert:
        alert = IncidentAlert(
            title=req.title or "Production Outage Alert",
            service=req.service or "backend-service",
            severity=IncidentSeverity.P1,
            error_name=req.error_name or "RuntimeError: Unexpected exception",
            error_message=req.error_message or "Internal error processing request",
            stack_trace=req.stack_trace or "Traceback (most recent call last):\n  line 42",
            affected_file=req.affected_file or "src/server.py",
            line_number=req.line_number or 42,
        )

    monitor = TrustMonitor(incident_id=alert.id)
    incident = Incident(
        id=alert.id,
        alert=alert,
        stage=IncidentStage.TRIAGE,
        switch_room_id=f"incident-{alert.id.lower()}",
    )

    INCIDENTS[alert.id] = incident
    MONITORS[alert.id] = monitor

    # Run the autonomous triage, planning, patch, and independent QA pipeline
    await commander.handle_new_incident(incident, monitor)
    incident.telemetry = monitor.get_snapshot()

    return incident


@app.post("/api/incidents/{incident_id}/action")
async def execute_human_action(incident_id: str, req: ActionRequest):
    """Executes a human approval or rejection in the incident room."""
    if incident_id not in INCIDENTS:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = INCIDENTS[incident_id]
    monitor = MONITORS.get(incident_id)
    if not monitor:
        monitor = TrustMonitor(incident_id=incident_id)
        MONITORS[incident_id] = monitor

    await commander.handle_human_action(
        incident=incident,
        action=req.action,
        user_name=req.user_name,
        monitor=monitor,
    )
    incident.telemetry = monitor.get_snapshot()
    return incident
