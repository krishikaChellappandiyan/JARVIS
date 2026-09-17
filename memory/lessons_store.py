# memory/lessons_store.py
"""
Persistent lesson store for false-positive memory.
Uses ChromaDB + sentence-transformers for semantic search when available,
falls back to a simple JSON file store otherwise.
"""
import json
from pathlib import Path
from datetime import datetime

LESSONS_DIR = Path(__file__).parent.parent / "cases" / ".lessons"


class LessonsStore:
    """
    Stores lessons learned from false-positive reports.
    Two backends:
      1. ChromaDB + sentence-transformers (semantic RAG)
      2. JSON flat-file fallback (keyword match)
    """

    def __init__(self):
        self._chroma = None
        self._collection = None
        self._available = False
        LESSONS_DIR.mkdir(parents=True, exist_ok=True)
        self._json_path = LESSONS_DIR / "lessons.json"
        self._lessons = self._load_json()
        self._init_chroma()

    # ── ChromaDB bootstrap ────────────────────────────────────
    def _init_chroma(self):
        try:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(LESSONS_DIR / "chroma"),
                anonymized_telemetry=False,
            ))
            self._collection = client.get_or_create_collection(
                name="lessons",
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
            self._available = True
        except Exception:
            # ChromaDB or sentence-transformers not installed — use JSON fallback
            self._available = False

    # ── JSON fallback I/O ─────────────────────────────────────
    def _load_json(self) -> list:
        if self._json_path.exists():
            try:
                return json.loads(self._json_path.read_text())
            except Exception:
                return []
        return []

    def _save_json(self):
        self._json_path.write_text(json.dumps(self._lessons, indent=2))

    # ── Public API ────────────────────────────────────────────
    def add_lesson(
        self,
        trigger: str,
        lesson: str,
        platform: str,
        context: str = "general",
    ) -> bool:
        """
        Store a lesson. Returns True on success.
        """
        entry = {
            "trigger": trigger,
            "lesson": lesson,
            "platform": platform.lower(),
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Always persist to JSON regardless of Chroma availability
        self._lessons.append(entry)
        self._save_json()

        # Also add to ChromaDB if available
        if self._available and self._collection is not None:
            try:
                doc_id = f"{platform.lower()}_{len(self._lessons)}"
                self._collection.add(
                    documents=[f"{trigger} | {lesson}"],
                    metadatas=[{
                        "platform": platform.lower(),
                        "context": context,
                    }],
                    ids=[doc_id],
                )
            except Exception:
                pass

        return True

    def has_platform_warning(self, platform: str) -> str | None:
        """
        Check if there's a stored lesson warning about a platform.
        Returns the lesson text if found, None otherwise.
        """
        platform_lower = platform.lower()

        # Try ChromaDB semantic search first
        if self._available and self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[f"{platform} false positive unreliable"],
                    n_results=1,
                    where={"platform": platform_lower},
                )
                if results and results["documents"] and results["documents"][0]:
                    return results["documents"][0][0]
            except Exception:
                pass

        # JSON fallback — simple keyword match
        for entry in reversed(self._lessons):
            if entry.get("platform", "").lower() == platform_lower:
                return entry.get("lesson", "")

        return None

    def get_lessons_for_context(self, context: str = "general") -> list:
        """Return all lessons matching a given context."""
        return [
            entry for entry in self._lessons
            if entry.get("context", "general") == context
        ]
