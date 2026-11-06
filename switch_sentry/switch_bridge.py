"""Switch Agent Bridge & Operations Adapter.

Provides the interface into sandbox-quantum/switch core operations:
- post_message
- create_room_document
- read_context
- run_template
Supports dual execution: live Switch Core server or local standalone hub.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx

from switch_sentry.models import SwitchMessage, ActionButton

logger = logging.getLogger(__name__)


class SwitchBridge:
    """Interface to the Switch agent bus and collaboration bridges."""

    def __init__(self, switch_url: Optional[str] = "http://localhost:8000"):
        self.switch_url = switch_url.rstrip("/") if switch_url else None
        self._local_rooms: Dict[str, List[SwitchMessage]] = {}
        self._local_documents: Dict[str, Dict[str, str]] = {}

    async def check_live_connection(self) -> bool:
        """Checks if a real Switch Core instance is reachable."""
        if not self.switch_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{self.switch_url}/health")
                return res.status_code == 200
        except Exception:
            return False

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
        """Posts a message to a Switch room and mirrors to active chat bridges."""
        msg = SwitchMessage(
            incident_id=incident_id,
            sender_role=sender_role,
            sender_name=sender_name,
            content=content,
            code_snippet=code_snippet,
            actions=actions or [],
        )

        # Store locally
        if room_id not in self._local_rooms:
            self._local_rooms[room_id] = []
        self._local_rooms[room_id].append(msg)

        # If connected to live Switch Core, forward to the Agent Bridge endpoint
        is_live = await self.check_live_connection()
        if is_live and self.switch_url:
            try:
                payload = {
                    "room_id": room_id,
                    "body": content,
                    "metadata": {
                        "incident_id": incident_id,
                        "sender_role": sender_role,
                        "sender_name": sender_name,
                        "code_snippet": code_snippet,
                    },
                }
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(
                        f"{self.switch_url}/api/v1/rooms/{room_id}/messages",
                        json=payload,
                    )
            except Exception as e:
                logger.warning(f"Could not forward to live Switch: {e}")

        return msg

    async def create_room_document(
        self, room_id: str, name: str, content: str
    ) -> Dict[str, Any]:
        """Creates an official document in the Switch room (e.g. Incident RCA)."""
        if room_id not in self._local_documents:
            self._local_documents[room_id] = {}
        self._local_documents[room_id][name] = content

        is_live = await self.check_live_connection()
        if is_live and self.switch_url:
            try:
                payload = {"name": name, "content": content}
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(
                        f"{self.switch_url}/api/v1/rooms/{room_id}/documents",
                        json=payload,
                    )
            except Exception as e:
                logger.warning(f"Could not sync document to live Switch: {e}")

        return {"status": "created", "name": name, "length": len(content)}

    def get_room_messages(self, room_id: str) -> List[SwitchMessage]:
        """Retrieves messages for a room."""
        return self._local_rooms.get(room_id, [])

    def get_room_documents(self, room_id: str) -> Dict[str, str]:
        """Retrieves documents created for a room."""
        return self._local_documents.get(room_id, {})
