"""Living Project Mistake Registry.

Inspired by Ziki's Project Mistake Registry, this records known anti-patterns
and prevention rules so agents and human engineers never repeat past bugs.
"""
from __future__ import annotations

import time
from typing import Dict, List
from switch_sentry.models import MistakeEntry

DEFAULT_MISTAKES: List[MistakeEntry] = [
    MistakeEntry(
        id="MISTAKE-001",
        title="Un-guarded External Payment Gateway Timeouts",
        anti_pattern="Calling external payment API response properties directly without checking for None or timeout status.",
        root_cause="Third-party payment gateways can return 504 Gateway Timeout or partial payload, yielding None in client SDKs.",
        prevention_rule="Always wrap gateway client responses in explicit null-checks and raise typed retryable exceptions.",
        timestamp=time.time() - 86400 * 5,
    ),
    MistakeEntry(
        id="MISTAKE-002",
        title="Leaked Async Database Connections on High-Throughput Routes",
        anti_pattern="Acquiring connection via `conn = await pool.acquire()` without try/finally or async context manager.",
        root_cause="Exceptions or early return paths bypass `.release()`, exhausting the 50-connection pool under load.",
        prevention_rule="Mandate `async with pool.acquire() as conn:` context managers across all database access.",
        timestamp=time.time() - 86400 * 2,
    ),
]


class MistakeRegistry:
    """Manages the living registry of project mistakes."""

    def __init__(self):
        self._mistakes: Dict[str, MistakeEntry] = {m.id: m for m in DEFAULT_MISTAKES}

    def get_all(self) -> List[MistakeEntry]:
        return list(self._mistakes.values())

    def record_mistake(
        self,
        title: str,
        anti_pattern: str,
        root_cause: str,
        prevention_rule: str,
    ) -> MistakeEntry:
        new_id = f"MISTAKE-{len(self._mistakes) + 1:03d}"
        entry = MistakeEntry(
            id=new_id,
            title=title,
            anti_pattern=anti_pattern,
            root_cause=root_cause,
            prevention_rule=prevention_rule,
        )
        self._mistakes[new_id] = entry
        return entry

    def generate_markdown(self) -> str:
        """Generates a Switch Room Document for the Mistake Registry."""
        lines = [
            "# 📚 Living Project Mistake Registry",
            "> *Shared organizational memory: anti-patterns, root causes, and prevention rules.*",
            "",
            "| ID | Title | Anti-Pattern | Prevention Rule |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for m in self._mistakes.values():
            lines.append(f"| **{m.id}** | {m.title} | `{m.anti_pattern}` | {m.prevention_rule} |")
        lines.append("")
        lines.append("---")
        lines.append("*Maintained automatically by Switch Sentry Squad.*")
        return "\n".join(lines)


# Singleton instance
MISTAKE_REGISTRY = MistakeRegistry()
