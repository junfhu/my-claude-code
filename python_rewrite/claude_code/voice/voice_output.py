"""
Voice output — text-to-speech integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class VoiceOutput:
    """Text-to-speech output for Claude Code responses.

    Supports:
    - macOS: ``say`` command
    - Linux: ``espeak`` or ``spd-say``
    - External: configurable TTS command
    """

    def __init__(
        self,
        *,
        tts_command: Optional[str] = None,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        enabled: bool = False,
    ) -> None:
        self._tts_command = tts_command or os.environ.get("CLAUDE_TTS_COMMAND")
        self._voice = voice or os.environ.get("CLAUDE_TTS_VOICE")
        self._rate = rate
        self.enabled = enabled
        self._process: Optional[asyncio.subprocess.Process] = None

    async def speak(self, text: str) -> None:
        """Speak the given text using TTS."""
        if not self.enabled:
            return
        if not text.strip():
            return

        # Stop any current speech
        await self.stop()

        if self._tts_command:
            await self._external_tts(text)
        else:
            await self._platform_tts(text)

    async def _external_tts(self, text: str) -> None:
        """Use external TTS command with text piped to stdin."""
        try:
            self._process = await asyncio.create_subprocess_shell(
                self._tts_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._process.communicate(input=text.encode("utf-8"))
        except Exception as exc:
            logger.debug("External TTS failed: %s", exc)
        finally:
            self._process = None

    async def _platform_tts(self, text: str) -> None:
        """Use platform-native TTS."""
        system = platform.system()

        # Sanitize text for shell safety
        safe_text = text.replace("'", "'\\''")

        if system == "Darwin":
            cmd = ["say"]
            if self._voice:
                cmd.extend(["-v", self._voice])
            if self._rate:
                cmd.extend(["-r", str(self._rate)])
            cmd.append(safe_text)
        elif system == "Linux":
            # Try espeak first, fall back to spd-say
            espeak = subprocess.run(
                ["which", "espeak-ng"], capture_output=True
            ).returncode == 0
            if espeak:
                cmd = ["espeak-ng"]
                if self._voice:
                    cmd.extend(["-v", self._voice])
                if self._rate:
                    cmd.extend(["-s", str(self._rate)])
                cmd.append(safe_text)
            else:
                cmd = ["spd-say"]
                if self._rate:
                    cmd.extend(["-r", str(self._rate)])
                cmd.append(safe_text)
        else:
            logger.debug("TTS not supported on %s", system)
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._process.wait()
        except FileNotFoundError:
            logger.debug("TTS command not found: %s", cmd[0])
        except Exception as exc:
            logger.debug("TTS failed: %s", exc)
        finally:
            self._process = None

    async def stop(self) -> None:
        """Stop current speech playback."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            self._process = None
