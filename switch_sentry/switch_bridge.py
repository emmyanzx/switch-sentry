"""Switch Agent Bridge & Operations Adapter.

Speaks the real Switch wire protocol (sandbox-quantum/switch):
- Agent Registration via POST /agents/register-known
- Message Delivery via POST /agents/{agent_id}/message
- Room Operations via POST /agents/{agent_id}/ops/{operation}
- Dual-Mode: Live Switch Core (backed by Mattermost) with embedded fallback.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from switch_sentry.models import SwitchMessage, ActionButton

logger = logging.getLogger(__name__)


def load_switch_env() -> Dict[str, str]:
    """Reads Switch environment configuration from infra/switch.env if present."""
    cfg = {}
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, "infra", "switch.env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
                    if match:
                        cfg[match.group(1)] = match.group(2)
        except Exception as e:
            logger.warning(f"Could not parse switch.env: {e}")
    return cfg


class SwitchBridge:
    """Manages communication with the Switch Agent Bridge and Room bus."""

    def __init__(self, switch_url: Optional[str] = None):
        env_cfg = load_switch_env()
        self.switch_url = switch_url or os.getenv("SWITCH_URL") or "http://localhost:8000"
        self.registration_token = (
            os.getenv("AGENT_REGISTRATION_TOKEN")
            or env_cfg.get("AGENT_REGISTRATION_TOKEN")
            or ""
        )

        self._local_rooms: Dict[str, List[SwitchMessage]] = {}
        self._local_documents: Dict[str, Dict[str, str]] = {}
        
        # Real Switch agent credentials
        self._registered_agents: Dict[str, Dict[str, str]] = {}
        self._switch_room_uuids: Dict[str, str] = {}
        self._initialized = False

    async def check_live_connection(self) -> bool:
        """Probes Switch Core /health."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.switch_url}/health")
                return res.status_code == 200 and res.json().get("status") == "ok"
        except Exception:
            return False

    async def initialize_squad_agents(self) -> None:
        """Registers the 3-agent squad into Switch Core if reachable."""
        if self._initialized:
            return

        is_live = await self.check_live_connection()
        if not is_live or not self.registration_token:
            return

        specs = [
            ("commander", "claude-code", "sentry-commander", "Incident Commander"),
            ("remediator", "codex", "sentry-remediator", "Code Remediator"),
            ("verifier", "opencode", "sentry-verifier", "Independent QA Verifier"),
        ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for role_key, agent_type, name, desc in specs:
                try:
                    res = await client.post(
                        f"{self.switch_url}/agents/register-known",
                        headers={"Authorization": f"Bearer {self.registration_token}"},
                        json={
                            "agent_type": agent_type,
                            "name": name,
                            "description": desc,
                            "overwrite": True,
                        },
                    )
                    if res.status_code == 200:
                        data = res.json()
                        self._registered_agents[role_key] = {
                            "agent_id": data["id"],
                            "api_key": data["api_key"],
                        }
                        logger.info(f"Registered Switch agent: {name} ({data['id']})")
                except Exception as e:
                    logger.warning(f"Failed to register Switch agent {name}: {e}")

        # Resolve or pick default room (e.g. Town Square)
        if "commander" in self._registered_agents:
            cmd = self._registered_agents["commander"]
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(
                        f"{self.switch_url}/agents/{cmd['agent_id']}/ops/list_rooms",
                        headers={
                            "Authorization": f"Bearer {cmd['api_key']}",
                            "Content-Type": "application/json",
                        },
                        json={},
                    )
                    if res.status_code == 200:
                        rooms = res.json().get("result", [])
                        for r in rooms:
                            if "Town Square" in r.get("name", ""):
                                self._switch_room_uuids["default"] = r["room_id"]
                                break
                        if not self._switch_room_uuids.get("default") and rooms:
                            self._switch_room_uuids["default"] = rooms[0]["room_id"]
            except Exception as e:
                logger.warning(f"Could not list Switch rooms: {e}")

        self._initialized = True

    async def post_message(
        self,
        room_id: str,
        sender_role: str,
        sender_name: str,
        content: str,
        incident_id: str,
        code_snippet: Optional[str] = None,
        actions: Optional[List[ActionButton]] = None,
    ) -> SwitchMessage:
        """Posts a message to the Switch room and mirrors to Mattermost/Slack."""
        msg = SwitchMessage(
            incident_id=incident_id,
            sender_role=sender_role,
            sender_name=sender_name,
            content=content,
            code_snippet=code_snippet,
            actions=actions or [],
        )

        # Store locally for the web interface
        if room_id not in self._local_rooms:
            self._local_rooms[room_id] = []
        self._local_rooms[room_id].append(msg)

        # Send to real Switch Core if available
        if not self._initialized:
            await self.initialize_squad_agents()

        agent_cred = self._registered_agents.get(sender_role) or self._registered_agents.get("commander")
        target_room_uuid = self._switch_room_uuids.get("default")

        if agent_cred and target_room_uuid:
            try:
                full_body = content
                if code_snippet:
                    full_body += f"\n\n```diff\n{code_snippet}\n```"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{self.switch_url}/agents/{agent_cred['agent_id']}/message",
                        headers={"Authorization": f"Bearer {agent_cred['api_key']}"},
                        json={"room_id": target_room_uuid, "content": full_body},
                    )
            except Exception as e:
                logger.warning(f"Could not push message to live Switch: {e}")

        return msg

    async def create_room_document(
        self, room_id: str, name: str, content: str
    ) -> Dict[str, Any]:
        """Creates an official document in the Switch room."""
        if room_id not in self._local_documents:
            self._local_documents[room_id] = {}
        self._local_documents[room_id][name] = content

        if not self._initialized:
            await self.initialize_squad_agents()

        agent_cred = self._registered_agents.get("commander")
        if agent_cred:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{self.switch_url}/agents/{agent_cred['agent_id']}/ops/create_room_document",
                        headers={
                            "Authorization": f"Bearer {agent_cred['api_key']}",
                            "Content-Type": "application/json",
                        },
                        json={"name": name, "content": content},
                    )
            except Exception as e:
                logger.warning(f"Could not sync room document to live Switch: {e}")

        return {"status": "created", "name": name, "length": len(content)}

    def get_room_messages(self, room_id: str) -> List[SwitchMessage]:
        return self._local_rooms.get(room_id, [])

    def get_room_documents(self, room_id: str) -> Dict[str, str]:
        return self._local_documents.get(room_id, {})
