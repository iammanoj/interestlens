"""
Pipecat pipeline configuration for voice onboarding.
Pipeline: Daily Audio In -> Google STT -> OnboardingAgent -> Google TTS -> Daily Audio Out
"""

import os
import sys
import asyncio
from typing import Optional, Callable
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    EndFrame,
    LLMMessagesFrame
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer

from voice.bot import OnboardingAgent
from models.profile import VoicePreferences


class OnboardingProcessor(FrameProcessor):
    """
    Pipecat frame processor that wraps the OnboardingAgent.
    Converts transcription frames to agent responses and outputs TTS frames.
    """

    def __init__(
        self,
        agent: OnboardingAgent,
        on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None
    ):
        super().__init__()
        self.agent = agent
        self.on_preferences_update = on_preferences_update
        self.on_transcription = on_transcription
        self._started = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames."""
        await super().process_frame(frame, direction)

        # Debug: log all incoming frames
        frame_type = type(frame).__name__
        if frame_type not in ["AudioRawFrame", "StartFrame", "StartInterruptionFrame", "StopInterruptionFrame"]:
            logger.info(f"[PIPELINE] Received frame: {frame_type}")
            sys.stdout.flush()

        if isinstance(frame, TranscriptionFrame):
            # User speech transcribed (final)
            logger.info(f"[TRANSCRIPTION FINAL] Text: '{frame.text}' User: {getattr(frame, 'user_id', 'unknown')}")
            sys.stdout.flush()
            if frame.text and frame.text.strip():
                # Send user transcription to WebSocket
                if self.on_transcription:
                    try:
                        if asyncio.iscoroutinefunction(self.on_transcription):
                            await self.on_transcription(frame.text, "user")
                        else:
                            self.on_transcription(frame.text, "user")
                    except Exception as e:
                        print(f"Transcription callback error: {e}")

                # Process through agent
                response = await self.agent.process_user_message(frame.text)

                # Output response as text frame (will be picked up by TTS)
                await self.push_frame(TextFrame(text=response))

                # Check if conversation is complete
                if self.agent.state.is_complete:
                    await self.push_frame(EndFrame())

        elif isinstance(frame, InterimTranscriptionFrame):
            # Interim/partial transcription - log for debugging
            logger.info(f"[TRANSCRIPTION INTERIM] Text: '{frame.text}' User: {getattr(frame, 'user_id', 'unknown')}")
            sys.stdout.flush()
            # Pass through but don't process
            await self.push_frame(frame, direction)

        elif isinstance(frame, EndFrame):
            # Pass through end frames
            await self.push_frame(frame)

        else:
            # Pass through other frames
            await self.push_frame(frame, direction)

    async def start_conversation(self):
        """Send the opening message."""
        if not self._started:
            self._started = True
            opening = self.agent.get_opening_message()
            await self.push_frame(TextFrame(text=opening))
            # Send transcription for opening message
            if self.on_transcription:
                try:
                    if asyncio.iscoroutinefunction(self.on_transcription):
                        await self.on_transcription(opening, "assistant")
                    else:
                        self.on_transcription(opening, "assistant")
                except Exception as e:
                    print(f"Opening transcription callback error: {e}")


async def create_voice_pipeline(
    room_url: str,
    room_token: str,
    user_id: str,
    room_name: str,
    on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
    on_session_complete: Optional[Callable[[VoicePreferences], None]] = None,
    on_transcription: Optional[Callable[[str, str], None]] = None
) -> tuple[PipelineRunner, PipelineTask]:
    """
    Create and configure the Pipecat pipeline for voice onboarding.

    Args:
        room_url: Daily room URL
        room_token: Daily meeting token for the bot
        user_id: User ID for preference saving
        room_name: Room name for session tracking
        on_preferences_update: Callback for real-time preference updates
        on_session_complete: Callback when session ends
        on_transcription: Callback for real-time transcription (text, speaker)

    Returns:
        Tuple of (PipelineRunner, PipelineTask)
    """
    # Create the onboarding agent
    agent = OnboardingAgent(
        user_id=user_id,
        room_name=room_name,
        session_id=room_name,  # Use room_name as session_id for Redis storage
        on_preferences_update=on_preferences_update,
        on_session_complete=on_session_complete,
        on_transcription=on_transcription
    )

    # Daily transport configuration - disable built-in transcription, use OpenAI STT instead
    # Optimized VAD settings for lower latency
    vad = SileroVADAnalyzer(
        params=SileroVADAnalyzer.VADParams(
            confidence=0.6,      # Lower threshold = faster detection (default 0.7)
            start_secs=0.1,      # Start speaking detection (default 0.2)
            stop_secs=0.4,       # Reduced from 0.8 - faster end-of-speech detection
            min_volume=0.5,      # Slightly lower volume threshold
        )
    )

    transport = DailyTransport(
        room_url=room_url,
        token=room_token,
        bot_name="InterestLens Onboarding",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad,  # Optimized VAD for low latency
            transcription_enabled=False,  # Disable Daily's transcription - using OpenAI STT
        )
    )

    # OpenAI STT for speech-to-text (Whisper) - optimized for low latency
    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="whisper-1",  # Fastest Whisper model
    )

    # OpenAI TTS for speech synthesis - optimized for streaming
    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",        # Friendly female voice
        model="tts-1",       # Faster model (vs tts-1-hd)
        speed=1.1,           # Slightly faster speech
    )

    # Create the onboarding processor
    processor = OnboardingProcessor(
        agent=agent,
        on_preferences_update=on_preferences_update,
        on_transcription=on_transcription
    )

    # Build pipeline
    # Flow: Transport (audio in) -> STT (transcription) -> Processor -> TTS -> Transport (audio out)
    pipeline = Pipeline([
        transport.input(),   # Audio input with VAD
        stt,                 # OpenAI Whisper STT for transcription
        processor,           # Onboarding agent logic
        tts,                 # Text to speech
        transport.output()   # Audio output
    ])

    # Create task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            idle_timeout_seconds=120,  # 2 minutes before idle timeout
        )
    )

    # Create runner
    runner = PipelineRunner()

    # Register event handlers
    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        """Handle bot joining the room."""
        logger.info(f"Bot joined room: {room_name}")
        sys.stdout.flush()
        # Start the conversation with minimal delay
        await asyncio.sleep(0.3)
        await processor.start_conversation()

    @transport.event_handler("on_left")
    async def on_left(transport, data=None):
        """Handle bot leaving the room."""
        print(f"Bot left room: {room_name}")
        # Force end if not already complete
        if not agent.state.is_complete:
            await agent.force_end()

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        """Handle user leaving the room."""
        print(f"Participant left: {participant.get('user_id', 'unknown')}")
        # End session when user leaves
        if not agent.state.is_complete:
            await agent.force_end()
            await task.cancel()

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        """Handle participant joining."""
        logger.warning(f"[DAILY EVENT] *** PARTICIPANT JOINED ***: {participant}")
        sys.stdout.flush()

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        """Handle first participant joining."""
        logger.warning(f"[DAILY EVENT] *** FIRST PARTICIPANT JOINED ***: {participant}")
        sys.stdout.flush()

    @transport.event_handler("on_participant_updated")
    async def on_participant_updated(transport, participant):
        """Handle participant updated."""
        logger.info(f"[DAILY EVENT] Participant updated: {participant}")
        sys.stdout.flush()

    @transport.event_handler("on_active_speaker_changed")
    async def on_active_speaker_changed(transport, participant):
        """Handle active speaker changed."""
        logger.warning(f"[DAILY EVENT] *** ACTIVE SPEAKER CHANGED ***: {participant}")
        sys.stdout.flush()

    @transport.event_handler("on_transcription_message")
    async def on_transcription_message(transport, message):
        """Debug: Handle transcription messages from Daily."""
        logger.warning(f"[DAILY EVENT] *** TRANSCRIPTION MESSAGE ***: {message}")
        sys.stdout.flush()
        # Extract useful info
        text = message.get("text", "")
        participant_id = message.get("participantId", message.get("participant_id", "unknown"))
        is_final = message.get("is_final", message.get("isFinal", True))
        logger.warning(f"[TRANSCRIPTION] Text: '{text}' | Participant: {participant_id} | Final: {is_final}")
        sys.stdout.flush()

    @transport.event_handler("on_app_message")
    async def on_app_message(transport, message, sender):
        """Handle app messages."""
        logger.info(f"[DAILY EVENT] App message from {sender}: {message}")
        sys.stdout.flush()

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        """Handle Daily errors."""
        logger.error(f"[DAILY ERROR] {error}")
        sys.stdout.flush()

    return runner, task, agent


async def run_voice_bot(
    room_url: str,
    room_token: str,
    user_id: str,
    room_name: str,
    on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
    on_session_complete: Optional[Callable[[VoicePreferences], None]] = None,
    on_transcription: Optional[Callable[[str, str], None]] = None
):
    """
    Run the voice bot until completion.

    This is the main entry point for running the bot in a separate process.

    Args:
        room_url: Daily room URL
        room_token: Daily meeting token
        user_id: User ID
        room_name: Room name
        on_preferences_update: Callback for preference updates
        on_session_complete: Callback for session completion
        on_transcription: Callback for real-time transcription (text, speaker)
    """
    runner, task, agent = await create_voice_pipeline(
        room_url=room_url,
        room_token=room_token,
        user_id=user_id,
        room_name=room_name,
        on_preferences_update=on_preferences_update,
        on_session_complete=on_session_complete,
        on_transcription=on_transcription
    )

    try:
        await runner.run(task)
    except Exception as e:
        print(f"Pipeline error: {e}")
        # Ensure cleanup on error
        if not agent.state.is_complete:
            await agent.force_end()
    finally:
        print(f"Voice bot session ended for room: {room_name}")


# Alternative: Use Deepgram Speech-to-Text directly instead of Daily's transcription
async def create_voice_pipeline_with_stt(
    room_url: str,
    room_token: str,
    user_id: str,
    room_name: str,
    on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
    on_session_complete: Optional[Callable[[VoicePreferences], None]] = None,
    on_transcription: Optional[Callable[[str, str], None]] = None
) -> tuple[PipelineRunner, PipelineTask]:
    """
    Alternative pipeline using Deepgram STT for transcription.
    Use this if Daily's built-in transcription is not available.
    """
    from pipecat.services.deepgram import DeepgramSTTService

    agent = OnboardingAgent(
        user_id=user_id,
        room_name=room_name,
        session_id=room_name,  # Use room_name as session_id for Redis storage
        on_preferences_update=on_preferences_update,
        on_session_complete=on_session_complete,
        on_transcription=on_transcription
    )

    transport = DailyTransport(
        room_url=room_url,
        token=room_token,
        bot_name="InterestLens Onboarding",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_audio_passthrough=True,
            transcription_enabled=False,  # We'll use Deepgram STT
        )
    )

    # Deepgram Speech-to-Text
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",
    )

    processor = OnboardingProcessor(
        agent=agent,
        on_preferences_update=on_preferences_update,
        on_transcription=on_transcription
    )

    pipeline = Pipeline([
        transport.input(),
        stt,                 # Deepgram STT for transcription
        processor,
        tts,
        transport.output()
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        )
    )

    runner = PipelineRunner()

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        await asyncio.sleep(1)
        await processor.start_conversation()

    return runner, task, agent
