"""Automated tests for Switch Sentry incident response pipeline."""
import pytest
from switch_sentry.models import (
    Incident,
    IncidentAlert,
    IncidentSeverity,
    IncidentStage,
)
from switch_sentry.sample_incidents import SAMPLE_INCIDENTS
from switch_sentry.switch_bridge import SwitchBridge
from switch_sentry.telemetry import TrustMonitor
from switch_sentry.mistakes import MISTAKE_REGISTRY
from switch_sentry.agents.remediator import CodeRemediator
from switch_sentry.agents.verifier import QAVerifier
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


def test_remediator_and_verifier_pipeline():
    """Verifies solution planning, patch synthesis, and independent QA verification."""
    alert = SAMPLE_INCIDENTS[0]
    monitor = TrustMonitor(incident_id=alert.id)
    remediator = CodeRemediator()
    verifier = QAVerifier()

    # 1. Solution plan
    plan = remediator.formulate_plan(alert)
    assert plan.approach is not None
    assert alert.affected_file in plan.affected_files

    # 2. Patch delivery
    patch, rationale = remediator.generate_remediation(alert, monitor)
    assert patch.file_path == alert.affected_file
    assert "--- a/" in patch.unified_diff
    assert "+++ b/" in patch.unified_diff

    # 3. Independent QA verification
    verdict, summary = verifier.evaluate_patch(alert, patch, monitor)
    assert verdict.is_good_to_merge is True
    assert "goodToMerge = TRUE" in summary
    assert len(verdict.tests_executed) > 0


@pytest.mark.asyncio
async def test_full_ziki_inspired_lifecycle_and_mistakes():
    """Verifies end-to-end 6-stage lifecycle and mistake registry logging."""
    alert = SAMPLE_INCIDENTS[0]
    bridge = SwitchBridge()
    remediator = CodeRemediator()
    verifier = QAVerifier()
    commander = IncidentCommander(bridge=bridge, remediator=remediator, verifier=verifier)
    monitor = TrustMonitor(incident_id=alert.id)

    incident = Incident(
        id="TEST-INC-ZIKI",
        alert=alert,
        stage=IncidentStage.TRIAGE,
        switch_room_id="test-incident-room",
    )

    initial_mistakes_count = len(MISTAKE_REGISTRY.get_all())

    # 1. Run pipeline through Stage 5 (Human Gate)
    await commander.handle_new_incident(incident, monitor)

    assert incident.stage == IncidentStage.AWAITING_APPROVAL
    assert incident.plan is not None
    assert incident.patch is not None
    assert incident.verdict is not None
    assert incident.verdict.is_good_to_merge is True
    assert len(incident.messages) == 5  # Triage, Plan, Patch, QA Verdict, Human Gate Prompt

    # 2. Human approval action -> Stage 6 (Resolved & Mistake Logged)
    await commander.handle_human_action(
        incident=incident,
        action="approve",
        user_name="Lead SRE",
        monitor=monitor,
    )

    assert incident.stage == IncidentStage.RESOLVED
    assert incident.rca_document is not None
    assert "Incident Post-Mortem & RCA" in incident.rca_document
    assert incident.mistake_entry is not None

    # Verify Mistake Registry grew
    assert len(MISTAKE_REGISTRY.get_all()) == initial_mistakes_count + 1

    # Verify documents in Switch Room
    docs = bridge.get_room_documents(incident.switch_room_id)
    assert f"RCA-{incident.id}.md" in docs
    assert "PROJECT_MISTAKE_REGISTRY.md" in docs


if __name__ == "__main__":
    pytest.main(["-v", __file__])
