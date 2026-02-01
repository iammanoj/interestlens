"""
Pipecat pipeline configuration for voice onboarding.
Pipeline: Daily Audio In -> Google STT -> OnboardingAgent -> Google TTS -> Daily Audio Out
"""

import os
import asyncio
from typing import Optional, Callable

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    EndFrame,
    LLMMessagesFrame
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.services.openai import OpenAITTSService
from pipecat.transports.services.daily import DailyParams, DailyTransport

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

        if isinstance(frame, TranscriptionFrame):
            # User speech transcribed
            if frame.text and frame.text.strip():
                # Process through agent
                response = await self.agent.process_user_message(frame.text)

                # Output response as text frame (will be picked up by TTS)
                await self.push_frame(TextFrame(text=response))

                # Check if conversation is complete
                if self.agent.state.is_complete:
                    await self.push_frame(EndFrame())

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
        on_preferences_update=on_preferences_update,
        on_session_complete=on_session_complete,
        on_transcription=on_transcription
    )

    # Daily transport configuration
    transport = DailyTransport(
        room_url=room_url,
        token=room_token,
        bot_name="InterestLens Onboarding",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_audio_passthrough=True,
            transcription_enabled=True,  # Use Daily's transcription
        )
    )

    # OpenAI TTS for speech synthesis
    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",  # Friendly female voice
    )

    # Create the onboarding processor
    processor = OnboardingProcessor(
        agent=agent,
        on_preferences_update=on_preferences_update,
        on_transcription=on_transcription
    )

    # Build pipeline
    # Flow: Transport (audio in) -> Processor (handles transcription) -> TTS -> Transport (audio out)
    pipeline = Pipeline([
        transport.input(),   # Audio input with VAD and transcription
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
        )
    )

    # Create runner
    runner = PipelineRunner()

    # Register event handlers
    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        """Handle bot joining the room."""
        print(f"Bot joined room: {room_name}")
        # Start the conversation after a short delay
        await asyncio.sleep(1)
        await processor.start_conversation()

    @transport.event_handler("on_left")
    async def on_left(transport, data):
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


# Alternative: Use Google Speech-to-Text directly instead of Daily's transcription
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
    Alternative pipeline using Google STT for transcription.
    Use this if Daily's built-in transcription is not available.
    """
    from pipecat.services.google import GoogleSTTService

    agent = OnboardingAgent(
        user_id=user_id,
        room_name=room_name,
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
            transcription_enabled=False,  # We'll use Google STT
        )
    )

    # Google Speech-to-Text
    stt = GoogleSTTService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        params={
            "language_code": "en-US",
            "model": "latest_long",
        }
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",
    )

    processor = OnboardingProcessor(
        agent=agent,
        on_preferences_update=on_preferences_update
    )

    pipeline = Pipeline([
        transport.input(),
        stt,                 # Google STT for transcription
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
