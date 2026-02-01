"""
WebSocket endpoint for real-time audio streaming from Chrome extension.
Receives audio chunks, transcribes them, and processes with the voice agent.
"""

import asyncio
import base64
import json
import io
import wave
from typing import Optional, Dict
from fastapi import WebSocket, WebSocketDisconnect
import httpx

# Optional: OpenAI Whisper for transcription
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Optional: Google Speech-to-Text
try:
    from google.cloud import speech
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False


class AudioSession:
    """Manages an audio streaming session."""

    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.audio_buffer = bytearray()
        self.sample_rate = 16000
        self.is_listening = False
        self.transcript_history = []

    def add_audio_chunk(self, chunk: bytes):
        """Add audio chunk to buffer."""
        self.audio_buffer.extend(chunk)

    def get_audio_and_clear(self) -> bytes:
        """Get accumulated audio and clear buffer."""
        audio = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        return audio

    def has_audio(self) -> bool:
        """Check if buffer has audio data."""
        return len(self.audio_buffer) > 0


# Active sessions
audio_sessions: Dict[str, AudioSession] = {}


async def transcribe_audio_openai(audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
    """Transcribe audio using OpenAI Whisper API."""
    if not OPENAI_AVAILABLE:
        return None

    try:
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)

        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"

        client = openai.OpenAI()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=wav_buffer,
            language="en"
        )

        return transcript.text

    except Exception as e:
        print(f"[AUDIO_WS] Transcription error: {e}")
        return None


async def process_voice_command(
    session: AudioSession,
    transcript: str,
    websocket: WebSocket
):
    """Process transcribed voice command and send response."""
    from voice.text_fallback import handle_text_message

    # Add to transcript history
    session.transcript_history.append({
        "role": "user",
        "text": transcript
    })

    # Send transcription back to client
    await websocket.send_json({
        "type": "transcription",
        "text": transcript,
        "speaker": "user"
    })

    # Process with text handler (reuses existing logic)
    try:
        response = await handle_text_message(
            session_id=session.session_id,
            user_id=session.user_id,
            message=transcript
        )

        # Send agent response
        await websocket.send_json({
            "type": "agent_response",
            "text": response.response,
            "is_complete": response.is_complete,
            "preferences": response.preferences.model_dump() if response.preferences else None
        })

        session.transcript_history.append({
            "role": "assistant",
            "text": response.response
        })

    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })


async def audio_websocket_handler(
    websocket: WebSocket,
    session_id: str,
    user_id: str = "anonymous"
):
    """
    WebSocket handler for audio streaming from Chrome extension.

    Connect to: ws://backend/voice/audio-stream/{session_id}

    Client sends:
    - {"type": "start_listening"} - Start audio capture
    - {"type": "stop_listening"} - Stop and process audio
    - {"type": "audio_chunk", "data": "<base64 audio>"} - Audio data
    - {"type": "ping"} - Keepalive

    Server sends:
    - {"type": "connected", "session_id": "..."}
    - {"type": "listening_started"}
    - {"type": "transcription", "text": "...", "speaker": "user"}
    - {"type": "agent_response", "text": "...", "is_complete": bool}
    - {"type": "error", "error": "..."}
    """
    await websocket.accept()

    # Create or get session
    session = AudioSession(session_id, user_id)
    audio_sessions[session_id] = session

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Audio streaming ready. Send 'start_listening' to begin."
        })

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=60.0
                )

                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "start_listening":
                    session.is_listening = True
                    session.audio_buffer.clear()
                    await websocket.send_json({"type": "listening_started"})

                elif msg_type == "stop_listening":
                    session.is_listening = False

                    if session.has_audio():
                        audio_data = session.get_audio_and_clear()

                        await websocket.send_json({
                            "type": "processing",
                            "message": "Transcribing audio..."
                        })

                        # Transcribe
                        transcript = await transcribe_audio_openai(
                            audio_data,
                            session.sample_rate
                        )

                        if transcript and transcript.strip():
                            await process_voice_command(
                                session,
                                transcript.strip(),
                                websocket
                            )
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": "Could not transcribe audio. Please try again."
                            })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No audio received"
                        })

                elif msg_type == "audio_chunk":
                    if session.is_listening:
                        # Decode base64 audio chunk
                        audio_b64 = data.get("data", "")
                        if audio_b64:
                            try:
                                audio_bytes = base64.b64decode(audio_b64)
                                session.add_audio_chunk(audio_bytes)
                            except Exception as e:
                                print(f"[AUDIO_WS] Error decoding audio: {e}")

                elif msg_type == "set_sample_rate":
                    session.sample_rate = data.get("sample_rate", 16000)
                    await websocket.send_json({
                        "type": "sample_rate_set",
                        "sample_rate": session.sample_rate
                    })

                elif msg_type == "get_transcript":
                    await websocket.send_json({
                        "type": "transcript_history",
                        "history": session.transcript_history
                    })

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        print(f"[AUDIO_WS] Client disconnected: {session_id}")
    except Exception as e:
        print(f"[AUDIO_WS] Error: {e}")
    finally:
        # Cleanup
        if session_id in audio_sessions:
            del audio_sessions[session_id]
