"""Automated tests for Switch Sentry incident response pipeline."""
import pytest
from switch_sentry.models import (
    Incident,
    IncidentAlert,
    IncidentSeverity,
    IncidentStatus,
)
from switch_sentry.sample_incidents import SAMPLE_INCIDENTS
from switch_sentry.switch_bridge import SwitchBridge
from switch_sentry.telemetry import TrustMonitor
from switch_sentry.agents.remediator import CodeRemediator
from switch_sentry.agents.commander import IncidentCommander


def test_trust_telemetry_calculation():
    """Verifies Switch Trust metrics, cost attribution, and score tracking."""
    monitor = TrustMonitor(incident_id="TEST-INC-1")
    monitor.record_step(
        step_name="Step 1",
        prompt_tokens=1000,
        completion_tokens=500,
        latency_ms=120.5,
        safety_verified=True,
    )
    snapshot = monitor.get_snapshot()

    assert snapshot.total_tokens == 1500
    assert snapshot.prompt_tokens == 1000
    assert snapshot.completion_tokens == 500
    assert snapshot.estimated_cost_usd > 0
    assert snapshot.trust_score >= 95.0
    assert len(snapshot.audit_logs) == 1


def test_code_remediator_diff_generation():
    """Verifies that CodeRemediator crafts unified diffs and tests."""
    alert = SAMPLE_INCIDENTS[0]
    monitor = TrustMonitor(incident_id=alert.id)
    remediator = CodeRemediator()

    patch, rationale = remediator.generate_remediation(alert, monitor)

    assert patch.file_path == alert.affected_file
    assert "--- a/" in patch.unified_diff
    assert "+++ b/" in patch.unified_diff
    assert "PASSED" in patch.test_output
    assert patch.risk_level == "LOW"


@pytest.mark.asyncio
async def test_incident_commander_workflow_and_approval():
    """Verifies end-to-end multi-agent triage, approval, and RCA filing."""
    alert = SAMPLE_INCIDENTS[0]
    bridge = SwitchBridge()
    remediator = CodeRemediator()
    commander = IncidentCommander(bridge=bridge, remediator=remediator)
    monitor = TrustMonitor(incident_id=alert.id)

    incident = Incident(
        id="TEST-INC-99",
        alert=alert,
        status=IncidentStatus.TRIGGERED,
        switch_room_id="test-incident-room",
    )

    # 1. Trigger incident
    await commander.handle_new_incident(incident, monitor)

    assert incident.status == IncidentStatus.AWAITING_APPROVAL
    assert incident.patch is not None
    assert len(incident.messages) == 3  # Triage, Remediator Patch, Approval Prompt

    # Check Switch room messages
    room_msgs = bridge.get_room_messages(incident.switch_room_id)
    assert len(room_msgs) == 3

    # 2. Human approval action
    await commander.handle_human_action(
        incident=incident,
        action="approve",
        user_name="DevOps Lead",
        monitor=monitor,
    )

    assert incident.status == IncidentStatus.RESOLVED
    assert incident.rca_document is not None
    assert "Incident Post-Mortem & RCA" in incident.rca_document

    # Verify RCA is registered as a Switch Room Document
    docs = bridge.get_room_documents(incident.switch_room_id)
    assert f"RCA-{incident.id}.md" in docs


if __name__ == "__main__":
    pytest.main(["-v", __file__])
