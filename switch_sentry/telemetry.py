"""Switch Trust SDK telemetry & governance integration.

Adheres to the Switch Trust framework (sandbox-quantum/switch-trust-sdk-py)
for monitoring token spend, latency, and agent safety guardrails.
"""
from __future__ import annotations

import time
from typing import Any, Dict
from switch_sentry.models import TrustTelemetry


class TrustMonitor:
    """Manages Switch Trust metrics, safety scoring, and cost attribution."""

    # Baseline cost estimation ($ per 1M tokens)
    PROMPT_COST_PER_M = 3.00
    COMPLETION_COST_PER_M = 15.00

    def __init__(self, incident_id: str):
        self.incident_id = incident_id
        self.start_time = time.time()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.audit_trail: list[str] = []
        self.confidence_deductions = 0.0

    def record_step(
        self,
        step_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        safety_verified: bool = True,
    ) -> None:
        """Records an agent reasoning step."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        
        status_tag = "VERIFIED" if safety_verified else "FLAGGED"
        if not safety_verified:
            self.confidence_deductions += 5.0

        self.audit_trail.append(
            f"[{time.strftime('%H:%M:%S')}] {step_name} ({status_tag}) - "
            f"+{prompt_tokens + completion_tokens} tokens ({latency_ms:.1f}ms)"
        )

    def get_snapshot(self) -> TrustTelemetry:
        """Computes current telemetry metrics."""
        total = self.prompt_tokens + self.completion_tokens
        cost = (
            (self.prompt_tokens / 1_000_000) * self.PROMPT_COST_PER_M
            + (self.completion_tokens / 1_000_000) * self.COMPLETION_COST_PER_M
        )
        elapsed_ms = (time.time() - self.start_time) * 1000.0
        score = max(70.0, 98.5 - self.confidence_deductions)

        return TrustTelemetry(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=total,
            latency_ms=round(elapsed_ms, 1),
            estimated_cost_usd=round(cost, 5),
            trust_score=round(score, 1),
            audit_logs=list(self.audit_trail),
        )
