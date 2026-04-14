"""
Notes Manager — Save and retrieve text notes/memos offline.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("Jarvis.Notes")


class NotesManager:
    """Manages persistent text notes stored as JSON files."""

    def __init__(self, config: dict):
        self.notes_dir = Path(config.get("notes_dir", "./data/notes"))
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self._notes_file = self.notes_dir / "notes.json"
        self._notes: List[dict] = self._load_notes()

    def _load_notes(self) -> List[dict]:
        if self._notes_file.exists():
            try:
                with open(self._notes_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_notes(self):
        with open(self._notes_file, "w") as f:
            json.dump(self._notes, f, indent=2)

    async def handle(self, intent: str, text: str) -> Optional[dict]:
        if intent == "note_save":
            return await self._save_note(text)
        elif intent == "note_read":
            return await self._read_notes()
        return None

    async def _save_note(self, text: str) -> dict:
        # Extract note content after common prefixes
        content = text
        for prefix in ["save a note", "take a note", "make a note", "write a note",
                        "create a note", "note that", "remember that", "save note"]:
            idx = content.lower().find(prefix)
            if idx >= 0:
                content = content[idx + len(prefix):].strip()
                # Remove leading "that", "saying", ":"
                content = re.sub(r'^(that|saying|:)\s*', '', content, flags=re.IGNORECASE)
                break

        if not content.strip():
            return {"response": "What would you like me to note down?"}

        note = {
            "id": len(self._notes) + 1,
            "content": content.strip(),
            "created": datetime.now().isoformat(),
        }
        self._notes.append(note)
        self._save_notes()

        return {
            "response": f"Note saved: '{content.strip()}'",
            "params": {"action": "save", "note": note},
        }

    async def _read_notes(self) -> dict:
        if not self._notes:
            return {"response": "You don't have any saved notes."}

        recent = self._notes[-5:]  # Last 5 notes
        notes_text = ". ".join(
            f"Note {n['id']}: {n['content']}" for n in recent
        )
        count = len(self._notes)
        return {
            "response": f"You have {count} note{'s' if count > 1 else ''}. "
                        f"Here are the most recent: {notes_text}",
            "params": {"action": "read", "count": count, "notes": recent},
        }
