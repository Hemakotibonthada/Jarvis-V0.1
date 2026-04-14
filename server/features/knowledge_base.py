"""
Knowledge Base — Offline document Q&A using local files.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Jarvis.Knowledge")


class KnowledgeBase:
    """Simple offline knowledge base from local text/markdown files."""

    def __init__(self, data_dir: str = "./data/knowledge"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._documents: dict = {}
        self._load_documents()

    def _load_documents(self):
        extensions = {".txt", ".md", ".text"}
        for f in self.data_dir.rglob("*"):
            if f.suffix.lower() in extensions:
                try:
                    content = f.read_text(encoding="utf-8")
                    self._documents[f.stem] = content
                except Exception as e:
                    logger.warning(f"Failed to load {f}: {e}")

        logger.info(f"Knowledge base: {len(self._documents)} documents loaded")

    def search(self, query: str) -> Optional[str]:
        """Simple keyword search across documents."""
        query_lower = query.lower()
        results = []

        for name, content in self._documents.items():
            if query_lower in content.lower():
                # Extract relevant paragraph
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        start = max(0, i - 1)
                        end = min(len(lines), i + 3)
                        snippet = "\n".join(lines[start:end])
                        results.append(f"[{name}] {snippet}")
                        break

        if results:
            return "\n\n".join(results[:3])
        return None

    def add_document(self, name: str, content: str):
        """Add a document to the knowledge base."""
        file_path = self.data_dir / f"{name}.md"
        file_path.write_text(content, encoding="utf-8")
        self._documents[name] = content
        logger.info(f"Added document: {name}")
