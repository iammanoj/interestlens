"""
WebSocket endpoint for real-time preference updates during voice onboarding.
Clients can connect to receive live updates as preferences are extracted.
"""

import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

from models.profile import VoicePreferences


class ConnectionManager:
    """Manages WebSocket connections for voice sessions."""

    def __init__(self):
        # room_name -> set of connected websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, room_name: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if room_name not in self.active_connections:
                self.active_connections[room_name] = set()
            self.active_connections[room_name].add(websocket)

    async def disconnect(self, websocket: WebSocket, room_name: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if room_name in self.active_connections:
                self.active_connections[room_name].discard(websocket)
                if not self.active_connections[room_name]:
                    del self.active_connections[room_name]

    async def broadcast_to_room(self, room_name: str, message: dict):
        """Broadcast a message to all connections in a room."""
        async with self._lock:
            connections = self.active_connections.get(room_name, set()).copy()

        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                # Connection might be closed
                await self.disconnect(websocket, room_name)

    async def send_preference_update(self, room_name: str, preferences: VoicePreferences):
        """Send a preference update to all connected clients."""
        message = {
            "type": "preference_update",
            "preferences": preferences.model_dump(),
            "topics_count": len(preferences.topics)
        }
        await self.broadcast_to_room(room_name, message)

    async def send_session_complete(self, room_name: str, preferences: VoicePreferences):
        """Notify clients that the session is complete."""
        connection_count = self.get_connection_count(room_name)
        print(f"[WEBSOCKET] Sending session_complete to {room_name} ({connection_count} connections)")
        message = {
            "type": "session_complete",
            "preferences": preferences.model_dump(),
            "topics_count": len(preferences.topics)
        }
        await self.broadcast_to_room(room_name, message)
        print(f"[WEBSOCKET] session_complete sent successfully to {room_name}")

    async def send_status_update(self, room_name: str, status: dict):
        """Send a status update to all connected clients."""
        message = {
            "type": "status_update",
            **status
        }
        await self.broadcast_to_room(room_name, message)

    async def send_error(self, room_name: str, error: str):
        """Send an error message to all connected clients."""
        message = {
            "type": "error",
            "error": error
        }
        await self.broadcast_to_room(room_name, message)

    async def send_transcription(self, room_name: str, text: str, speaker: str):
        """Send a real-time transcription update to all connected clients."""
        message = {
            "type": "transcription",
            "text": text,
            "speaker": speaker  # "user" or "assistant"
        }
        await self.broadcast_to_room(room_name, message)

    def has_connections(self, room_name: str) -> bool:
        """Check if a room has any active connections."""
        return room_name in self.active_connections and len(self.active_connections[room_name]) > 0

    def get_connection_count(self, room_name: str) -> int:
        """Get the number of connections for a room."""
        return len(self.active_connections.get(room_name, set()))


# Global connection manager instance
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, room_name: str):
    """
    WebSocket endpoint handler for real-time voice session updates.

    Connect to: ws://backend/voice/session/{room_name}/updates

    Messages sent:
    - {"type": "preference_update", "preferences": {...}, "topics_count": N}
    - {"type": "session_complete", "preferences": {...}}
    - {"type": "status_update", "phase": "...", "turn_count": N}
    - {"type": "error", "error": "message"}

    Messages received:
    - {"type": "ping"} -> responds with {"type": "pong"}
    - {"type": "get_status"} -> responds with current session status
    """
    await manager.connect(websocket, room_name)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "room_name": room_name,
            "message": "Connected to voice session updates"
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0  # Heartbeat timeout
                )

                # Handle client messages
                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "get_status":
                    # Import here to avoid circular imports
                    from voice.session_manager import get_session_status
                    status = await get_session_status(room_name)
                    await websocket.send_json({
                        "type": "status_response",
                        **status
                    })

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error for room {room_name}: {e}")
    finally:
        await manager.disconnect(websocket, room_name)


def get_preference_update_callback(room_name: str):
    """
    Create a callback function for preference updates.

    This is passed to the OnboardingAgent to notify WebSocket clients.
    """
    async def callback(preferences: VoicePreferences):
        await manager.send_preference_update(room_name, preferences)

    return callback


def get_session_complete_callback(room_name: str):
    """
    Create a callback function for session completion.

    This is passed to the OnboardingAgent to notify WebSocket clients.
    """
    async def callback(preferences: VoicePreferences):
        await manager.send_session_complete(room_name, preferences)

    return callback


def get_transcription_callback(room_name: str):
    """
    Create a callback function for real-time transcription updates.

    This is passed to the OnboardingAgent to stream transcript to WebSocket clients.
    """
    async def callback(text: str, speaker: str):
        await manager.send_transcription(room_name, text, speaker)

    return callback
