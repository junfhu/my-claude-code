"""
Voice input handling — speech-to-text integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class VoiceInput:
    """Handles voice input by recording audio and transcribing it.

    Supports multiple backends:
    - macOS: ``say`` for recording, Whisper API for transcription
    - External: configurable STT command
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        stt_command: Optional[str] = None,
        sample_rate: int = 16000,
        max_duration_s: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._stt_command = stt_command or os.environ.get("CLAUDE_STT_COMMAND")
        self._sample_rate = sample_rate
        self._max_duration = max_duration_s
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    async def record_and_transcribe(self) -> Optional[str]:
        """Record audio from the microphone and transcribe it.

        Returns the transcribed text, or None if recording failed.
        """
        if self._stt_command:
            return await self._external_stt()
        return await self._builtin_record()

    async def _external_stt(self) -> Optional[str]:
        """Use an external STT command."""
        if not self._stt_command:
            return None
        try:
            proc = await asyncio.create_subprocess_shell(
                self._stt_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._max_duration + 10
            )
            if proc.returncode == 0:
                return stdout.decode("utf-8").strip()
            logger.warning("STT command failed: %s", stderr.decode())
            return None
        except asyncio.TimeoutError:
            logger.warning("STT command timed out")
            return None
        except Exception as exc:
            logger.warning("STT error: %s", exc)
            return None

    async def _builtin_record(self) -> Optional[str]:
        """Record using system tools and transcribe via Whisper API."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            # Record audio
            self._recording = True
            success = await self._record_audio(wav_path)
            self._recording = False

            if not success:
                return None

            # Transcribe
            return await self._transcribe_whisper(wav_path)
        finally:
            self._recording = False
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    async def _record_audio(self, output_path: str) -> bool:
        """Record audio to a WAV file using platform-specific tools."""
        import platform
        system = platform.system()

        if system == "Darwin":
            # macOS: use sox or rec if available
            cmd = [
                "rec", "-q", "-r", str(self._sample_rate),
                "-c", "1", "-b", "16", output_path,
                "trim", "0", str(self._max_duration),
            ]
        elif system == "Linux":
            cmd = [
                "arecord", "-q", "-f", "S16_LE",
                "-r", str(self._sample_rate), "-c", "1",
                "-d", str(int(self._max_duration)),
                output_path,
            ]
        else:
            logger.warning("Voice recording not supported on %s", system)
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._max_duration + 5
            )
            return proc.returncode == 0
        except (asyncio.TimeoutError, FileNotFoundError) as exc:
            logger.warning("Audio recording failed: %s", exc)
            return False

    async def _transcribe_whisper(self, audio_path: str) -> Optional[str]:
        """Transcribe audio using OpenAI Whisper API (or compatible)."""
        import httpx

        whisper_url = os.environ.get(
            "CLAUDE_WHISPER_URL", "https://api.openai.com/v1/audio/transcriptions"
        )
        whisper_key = os.environ.get("OPENAI_API_KEY", self._api_key)

        if not whisper_key:
            logger.warning("No API key for Whisper transcription")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(audio_path, "rb") as f:
                    resp = await client.post(
                        whisper_url,
                        headers={"Authorization": f"Bearer {whisper_key}"},
                        files={"file": ("audio.wav", f, "audio/wav")},
                        data={"model": "whisper-1"},
                    )
                resp.raise_for_status()
                return resp.json().get("text", "").strip()
        except Exception as exc:
            logger.warning("Whisper transcription failed: %s", exc)
            return None

    def stop_recording(self) -> None:
        """Stop an active recording."""
        self._recording = False
