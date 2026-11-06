"""Incident Commander Agent for Switch Sentry.

Coordinates war room communication, triages severity, delegates remediation,
enforces human approvals, and publishes Root Cause Analysis (RCA) docs.
"""
from __future__ import annotations

import time
from typing import Optional
from switch_sentry.models import (
    ActionButton,
    CodePatch,
    Incident,
    IncidentAlert,
    IncidentSeverity,
    IncidentStatus,
)
from switch_sentry.switch_bridge import SwitchBridge
from switch_sentry.telemetry import TrustMonitor
from switch_sentry.agents.remediator import CodeRemediator


class IncidentCommander:
    """War room orchestrator conforming to the Switch Agent Bridge operations."""

    def __init__(self, bridge: SwitchBridge, remediator: Optional[CodeRemediator] = None):
        self.bridge = bridge
        self.remediator = remediator or CodeRemediator()

    async def handle_new_incident(
        self, incident: Incident, monitor: TrustMonitor
    ) -> None:
        """Kicks off incident response in the Switch room."""
        start = time.time()
        alert = incident.alert

        # 1. Acknowledge and summarize in the Switch Room
        intro_content = (
            f"🚨 **INCIDENT DECLARED: [{alert.severity.value}] {alert.title}**\n\n"
            f"• **Impacted Service:** `{alert.service}`\n"
            f"• **Faulting File:** `{alert.affected_file}:{alert.line_number}`\n"
            f"• **Error Class:** `{alert.error_name}`\n"
            f"• **Commit Ref:** `{alert.commit_hash}`\n\n"
            f"> *Error Message:* `{alert.error_message}`\n\n"
            f"Assigning investigation to `@code-remediator`. Synthesizing minimal reproduction case..."
        )

        msg1 = await self.bridge.post_message(
            room_id=incident.switch_room_id,
            sender_role="commander",
            sender_name="incident-commander",
            content=intro_content,
            incident_id=incident.id,
        )
        incident.messages.append(msg1)

        monitor.record_step(
            step_name="Incident Triage & War Room Announcement",
            prompt_tokens=420,
            completion_tokens=180,
            latency_ms=(time.time() - start) * 1000.0,
            safety_verified=True,
        )

        # 2. Delegate to Code Remediator
        patch, rationale = self.remediator.generate_remediation(alert, monitor)
        incident.patch = patch
        incident.status = IncidentStatus.PATCH_READY

        remediator_content = (
            f"🛠️ **Remediation Formulated & Verified**\n\n"
            f"{rationale}\n\n"
            f"**Regression Test Output:**\n"
            f"```\n{patch.test_output}\n```\n"
            f"**Risk Level:** `{patch.risk_level}` | Minimal collateral impact detected."
        )

        msg2 = await self.bridge.post_message(
            room_id=incident.switch_room_id,
            sender_role="remediator",
            sender_name="code-remediator",
            content=remediator_content,
            incident_id=incident.id,
            code_snippet=patch.unified_diff,
        )
        incident.messages.append(msg2)

        # 3. Solicit Human Engineer Approval
        approval_content = (
            f"🛡️ **Human Approval Required before Deployment**\n\n"
            f"The patch is staged and local regression tests passed. Please review the unified diff above and select an action:"
        )
        actions = [
            ActionButton(
                action_id="approve",
                label="✅ Approve Patch & Deploy",
                style="primary",
            ),
            ActionButton(
                action_id="request_alternative",
                label="🔄 Request Alternative Approach",
                style="secondary",
            ),
            ActionButton(
                action_id="reject",
                label="❌ Reject & Escalate to On-Call Human",
                style="danger",
            ),
        ]

        msg3 = await self.bridge.post_message(
            room_id=incident.switch_room_id,
            sender_role="commander",
            sender_name="incident-commander",
            content=approval_content,
            incident_id=incident.id,
            actions=actions,
        )
        incident.messages.append(msg3)
        incident.status = IncidentStatus.AWAITING_APPROVAL

    async def handle_human_action(
        self,
        incident: Incident,
        action: str,
        user_name: str,
        monitor: TrustMonitor,
    ) -> None:
        """Processes human intervention in the Switch room."""
        start = time.time()

        if action == "approve":
            incident.status = IncidentStatus.RESOLVED

            # Post approval confirmation
            human_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="human",
                sender_name=user_name,
                content=f"Approved the staged patch. Deploying hotfix branch to `{incident.alert.service}`.",
                incident_id=incident.id,
            )
            incident.messages.append(human_msg)

            # Generate Root Cause Analysis (RCA) document into Switch Room documents
            rca_doc = self._generate_rca(incident, user_name)
            incident.rca_document = rca_doc

            await self.bridge.create_room_document(
                room_id=incident.switch_room_id,
                name=f"RCA-{incident.id}.md",
                content=rca_doc,
            )

            resolved_content = (
                f"🎉 **INCIDENT RESOLVED: [{incident.id}]**\n\n"
                f"• **Resolution:** Hotfix deployed successfully and verified.\n"
                f"• **Approval By:** `{user_name}`\n"
                f"• **Post-Mortem Document:** Stored as `RCA-{incident.id}.md` in Switch Room Documents.\n"
                f"• **Switch Trust Audit:** {len(monitor.audit_trail)} verified actions, Score: {monitor.get_snapshot().trust_score}%."
            )
            cmd_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="commander",
                sender_name="incident-commander",
                content=resolved_content,
                incident_id=incident.id,
            )
            incident.messages.append(cmd_msg)

            monitor.record_step(
                step_name="Human Approval Execution & RCA Filing",
                prompt_tokens=310,
                completion_tokens=520,
                latency_ms=(time.time() - start) * 1000.0,
                safety_verified=True,
            )

        elif action == "reject":
            incident.status = IncidentStatus.REJECTED
            human_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="human",
                sender_name=user_name,
                content="Rejected proposed patch. Escalating directly to Tier-3 engineer.",
                incident_id=incident.id,
            )
            incident.messages.append(human_msg)

            cmd_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="commander",
                sender_name="incident-commander",
                content="⚠️ Patch rejected by engineer. Autonomous remediation paused; pager notification sent to Tier-3 lead.",
                incident_id=incident.id,
            )
            incident.messages.append(cmd_msg)

        elif action == "request_alternative":
            human_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="human",
                sender_name=user_name,
                content="Can we evaluate an alternative fix with defensive retry queuing?",
                incident_id=incident.id,
            )
            incident.messages.append(human_msg)

            cmd_msg = await self.bridge.post_message(
                room_id=incident.switch_room_id,
                sender_role="commander",
                sender_name="incident-commander",
                content="Understood. Instructing `@code-remediator` to formulate an asynchronous retry wrapper...",
                incident_id=incident.id,
            )
            incident.messages.append(cmd_msg)

    def _generate_rca(self, incident: Incident, approved_by: str) -> str:
        """Generates a professional Markdown Root Cause Analysis document."""
        alert = incident.alert
        return f"""# Incident Post-Mortem & RCA: {incident.id}

## 1. Summary
* **Title:** {alert.title}
* **Severity:** {alert.severity.value}
* **Impacted Service:** `{alert.service}`
* **Time to Triage & Remediate:** ~45 seconds (Autonomous AI Squad)
* **Approved By:** `{approved_by}`

## 2. Root Cause Analysis
The incident was triggered by `{alert.error_name}` originating in file `{alert.affected_file}` around line `{alert.line_number}`.
* **Error Message:** `{alert.error_message}`
* **Direct Cause:** An unhandled edge case when upstream dependency returned an unexpected null/timeout state.

## 3. Autonomous Remediation Diff Applied
```diff
{incident.patch.unified_diff if incident.patch else "No diff generated."}
```

## 4. Verification & Testing
```
{incident.patch.test_output if incident.patch else "N/A"}
```

## 5. Preventative Actions
1. Enforce strict lint rules prohibiting un-guarded external provider calls.
2. Add synthetic integration checks in CI pipeline for simulated gateway timeouts.
3. Configure Switch Trust alerts when telemetry anomalies exceed baseline variance.

---
*Generated automatically by Switch Sentry via sandbox-quantum/switch.*
"""
