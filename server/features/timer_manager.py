"""
Timer Manager — Set, track, and fire timers/alarms with audio notifications.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("Jarvis.Timers")


class Timer:
    def __init__(self, name: str, duration_seconds: float, created_at: float):
        self.name = name
        self.duration = duration_seconds
        self.created_at = created_at
        self.end_time = created_at + duration_seconds
        self.task: Optional[asyncio.Task] = None
        self.fired = False
        self.cancelled = False

    @property
    def remaining(self) -> float:
        return max(0, self.end_time - time.time())

    @property
    def is_active(self) -> bool:
        return not self.fired and not self.cancelled and self.remaining > 0

    def __repr__(self):
        return f"Timer('{self.name}', {self.remaining:.0f}s remaining)"


class TimerManager:
    """Manages countdown timers and alarms."""

    def __init__(self, config: dict):
        self.max_timers = config.get("max_timers", 10)
        self._timers: Dict[str, Timer] = {}
        self._callbacks = []

    def on_timer_fire(self, callback):
        self._callbacks.append(callback)

    async def handle(self, intent: str, text: str) -> Optional[dict]:
        if intent == "timer":
            return await self._set_timer(text)
        elif intent == "cancel_timer":
            return await self._cancel_timer(text)
        return None

    async def _set_timer(self, text: str) -> dict:
        duration = self._parse_duration(text)
        if duration is None:
            return {"response": "I couldn't understand the timer duration. Please specify like '5 minutes' or '30 seconds'."}

        name = self._extract_timer_name(text) or f"timer_{len(self._timers) + 1}"

        if len(self._timers) >= self.max_timers:
            return {"response": f"Maximum timers ({self.max_timers}) reached. Cancel one first."}

        timer = Timer(name, duration, time.time())
        self._timers[name] = timer

        # Start async countdown
        timer.task = asyncio.create_task(self._timer_countdown(timer))

        duration_str = self._format_duration(duration)
        return {
            "response": f"Timer '{name}' set for {duration_str}.",
            "params": {"name": name, "duration": duration, "duration_str": duration_str},
        }

    async def _cancel_timer(self, text: str) -> dict:
        name = self._extract_timer_name(text)

        if name and name in self._timers:
            timer = self._timers[name]
            timer.cancelled = True
            if timer.task:
                timer.task.cancel()
            del self._timers[name]
            return {"response": f"Timer '{name}' cancelled.", "params": {"name": name}}

        # Cancel most recent
        active = [t for t in self._timers.values() if t.is_active]
        if active:
            timer = active[-1]
            timer.cancelled = True
            if timer.task:
                timer.task.cancel()
            del self._timers[timer.name]
            return {"response": f"Timer '{timer.name}' cancelled.", "params": {"name": timer.name}}

        return {"response": "No active timers to cancel."}

    async def _timer_countdown(self, timer: Timer):
        try:
            await asyncio.sleep(timer.duration)
            timer.fired = True
            logger.info(f"Timer '{timer.name}' fired!")
            for callback in self._callbacks:
                await callback(timer)
        except asyncio.CancelledError:
            pass

    def get_active_timers(self) -> List[str]:
        return [
            f"{t.name}: {self._format_duration(t.remaining)} remaining"
            for t in self._timers.values()
            if t.is_active
        ]

    def _parse_duration(self, text: str) -> Optional[float]:
        text = text.lower()
        total_seconds = 0
        found = False

        patterns = [
            (r'(\d+)\s*(?:hour|hr|h)\b', 3600),
            (r'(\d+)\s*(?:minute|min|m)\b', 60),
            (r'(\d+)\s*(?:second|sec|s)\b', 1),
        ]

        for pattern, multiplier in patterns:
            match = re.search(pattern, text)
            if match:
                total_seconds += int(match.group(1)) * multiplier
                found = True

        return total_seconds if found else None

    def _extract_timer_name(self, text: str) -> Optional[str]:
        match = re.search(r'(?:called|named|for)\s+"?([^"]+)"?', text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _format_duration(self, seconds: float) -> str:
        seconds = int(seconds)
        parts = []
        if seconds >= 3600:
            parts.append(f"{seconds // 3600} hour{'s' if seconds // 3600 > 1 else ''}")
            seconds %= 3600
        if seconds >= 60:
            parts.append(f"{seconds // 60} minute{'s' if seconds // 60 > 1 else ''}")
            seconds %= 60
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        return " and ".join(parts)
