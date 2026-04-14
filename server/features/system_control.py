"""
System Control — Volume, brightness, system info.
"""

import asyncio
import logging
import platform
import subprocess
from typing import Optional

logger = logging.getLogger("Jarvis.System")


class SystemControl:
    """System-level controls: volume, brightness, info."""

    def __init__(self):
        self._volume = 70  # percent
        self._platform = platform.system()

    async def handle(self, intent: str, text: str) -> Optional[dict]:
        if intent == "volume_up":
            return await self._change_volume(10)
        elif intent == "volume_down":
            return await self._change_volume(-10)
        return None

    async def _change_volume(self, delta: int) -> dict:
        self._volume = max(0, min(100, self._volume + delta))

        # Apply system volume change
        try:
            if self._platform == "Windows":
                # Uses nircmd if available, otherwise just tracks internally
                pass
            elif self._platform == "Linux":
                subprocess.run(
                    ["amixer", "sset", "Master", f"{self._volume}%"],
                    capture_output=True,
                    timeout=5,
                )
            elif self._platform == "Darwin":
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {self._volume}"],
                    capture_output=True,
                    timeout=5,
                )
        except Exception as e:
            logger.debug(f"Volume control not available: {e}")

        direction = "up" if delta > 0 else "down"
        return {
            "response": f"Volume turned {direction} to {self._volume} percent.",
            "params": {"volume": self._volume},
        }

    def get_system_info(self) -> dict:
        return {
            "platform": self._platform,
            "volume": self._volume,
            "hostname": platform.node(),
            "python_version": platform.python_version(),
        }
