"""
Music Player — Local music playback control.
"""

import asyncio
import logging
import random
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("Jarvis.Music")


class MusicPlayer:
    """Manages local music playback."""

    def __init__(self, config: dict):
        self.music_dir = Path(config.get("music_dir", "./music"))
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._playlist: List[Path] = []
        self._current_index = 0
        self._is_playing = False
        self._scan_music()

    def _scan_music(self):
        extensions = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
        self._playlist = sorted(
            f for f in self.music_dir.rglob("*") if f.suffix.lower() in extensions
        )
        logger.info(f"Found {len(self._playlist)} music files")

    async def handle(self, intent: str, text: str) -> Optional[dict]:
        if intent == "music_play":
            return await self._play(text)
        elif intent == "music_stop":
            return await self._stop()
        elif intent == "music_next":
            return await self._next()
        return None

    async def _play(self, text: str) -> dict:
        if not self._playlist:
            return {"response": "No music files found in the music directory."}

        self._is_playing = True

        # Check if specific song requested
        text_lower = text.lower()
        for i, track in enumerate(self._playlist):
            if track.stem.lower() in text_lower:
                self._current_index = i
                return {
                    "response": f"Now playing: {track.stem}.",
                    "params": {"action": "play", "track": str(track), "name": track.stem},
                }

        track = self._playlist[self._current_index]
        return {
            "response": f"Playing music. Current track: {track.stem}.",
            "params": {"action": "play", "track": str(track), "name": track.stem},
        }

    async def _stop(self) -> dict:
        self._is_playing = False
        return {
            "response": "Music paused.",
            "params": {"action": "stop"},
        }

    async def _next(self) -> dict:
        if not self._playlist:
            return {"response": "No music available."}

        self._current_index = (self._current_index + 1) % len(self._playlist)
        track = self._playlist[self._current_index]
        return {
            "response": f"Skipping to next track: {track.stem}.",
            "params": {"action": "next", "track": str(track), "name": track.stem},
        }

    def shuffle(self):
        random.shuffle(self._playlist)
        self._current_index = 0

    @property
    def current_track(self) -> Optional[str]:
        if self._playlist:
            return self._playlist[self._current_index].stem
        return None
