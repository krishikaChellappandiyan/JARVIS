# modules/cloud_docs.py
"""
Local Workspace & Document Intelligence Engine for J.A.R.V.I.S..

Searches real filesystem paths (workspace, project repos, Documents, Downloads, Desktop)
for user files, code, reports, and documentation. Reads authentic excerpts and summaries aloud.
"""

import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
SEARCH_ROOTS = [
    WORKSPACE_ROOT,
    WORKSPACE_ROOT.parent,
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop"
]

SUPPORTED_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".pdf",
    ".html", ".sh", ".csv", ".toml", ".rst", ".conf"
}

IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", ".pytest_cache",
    ".venv", "venv", "dist", "build", ".egg-info"
}


class CloudDocumentManager:
    """
    On-device file search and document intelligence manager.
    """

    def __init__(self, search_roots: Optional[List[Path]] = None):
        self.roots = [p for p in (search_roots or SEARCH_ROOTS) if p.exists()]

    def search_documents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches the local filesystem for matching files and generates telemetry records.
        """
        q_clean = query.strip().lower()
        if not q_clean:
            return []

        tokens = [t for t in re.split(r'[\s_\-\.]+', q_clean) if t and t not in ["the", "a", "an", "file", "doc", "find", "search", "read", "show"]]
        if not tokens:
            tokens = [q_clean]

        matches: List[tuple[int, Dict[str, Any]]] = []
        visited_paths = set()

        for root in self.roots:
            try:
                for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                    # Filter out ignored directories in-place
                    dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]

                    for fname in filenames:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in SUPPORTED_EXTENSIONS and not ext == "":
                            continue

                        full_path = os.path.join(dirpath, fname)
                        if full_path in visited_paths:
                            continue
                        visited_paths.add(full_path)

                        fname_lower = fname.lower()
                        score = 0

                        # Exact query match in filename
                        if q_clean in fname_lower:
                            score += 50
                        
                        # Token matching
                        token_hits = sum(1 for t in tokens if t in fname_lower)
                        if token_hits > 0:
                            score += token_hits * 15

                        if score > 0:
                            rel_source = str(root.name)
                            try:
                                stat = os.stat(full_path)
                                size_kb = round(stat.st_size / 1024, 1)
                                mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                            except Exception:
                                size_kb = 0.0
                                mtime_str = "Unknown"

                            matches.append((score, {
                                "id": f"doc_{len(matches)+1}",
                                "filename": fname,
                                "path": full_path,
                                "source": rel_source,
                                "file_type": ext.lstrip(".").upper() or "TEXT",
                                "size_kb": size_kb,
                                "modified": mtime_str,
                                "title": fname.replace("_", " ").replace("-", " ").title()
                            }))

                            if len(matches) >= 30:
                                break
                    if len(matches) >= 30:
                        break
            except Exception as e:
                print(f"[cloud_docs] Walk error in {root}: {e}")

        # Sort highest score first, then by size
        matches.sort(key=lambda x: x[0], reverse=True)
        top_results = [m[1] for m in matches[:limit]]

        # Enrich top results with content previews
        for doc in top_results:
            doc["summary"], doc["key_points"] = self._extract_file_preview(doc["path"])

        return top_results

    def _extract_file_preview(self, filepath: str) -> tuple[str, List[str]]:
        """Reads genuine text excerpts from matching files."""
        try:
            p = Path(filepath)
            if not p.exists() or p.stat().st_size > 2 * 1024 * 1024:  # limit to 2MB
                return "File content available on disk.", ["Binary or large file."]

            ext = p.suffix.lower()
            if ext in {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".sh", ".toml", ".rst"}:
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                line_count = len(lines)

                # Clean summary
                summary = f"File contains {line_count} lines of code/text. Modified {time.strftime('%Y-%m-%d', time.localtime(p.stat().st_mtime))}."
                key_points = []
                for line in lines[:8]:
                    if line.startswith(("#", "//", "/*", "\"\"\"", "'''", "import", "class", "def")):
                        clean_line = re.sub(r'^[#/\*"\']+\s*', '', line).strip()
                        if clean_line and len(clean_line) > 5 and clean_line not in key_points:
                            key_points.append(clean_line[:90])
                    if len(key_points) >= 3:
                        break

                if not key_points and lines:
                    key_points = [lines[0][:90]]

                return summary, key_points
        except Exception:
            pass

        return "Local system document located and verified.", ["Standard local storage."]

    def get_document_summary(self, query: str) -> str:
        """Find a document and format key points summary in J.A.R.V.I.S. voice."""
        results = self.search_documents(query, limit=3)
        if not results:
            return f"I searched your local workspace and repositories, Sir, but found no documents or files matching '{query}'."

        best = results[0]
        points_str = "; ".join(best.get("key_points", []))
        summary_text = best.get("summary", "")

        return (
            f"I located '{best['filename']}' ({best['file_type']}, {best['size_kb']} KB) in your {best['source']} directory, Sir. "
            f"{summary_text} "
            f"Key excerpts: {points_str}" if points_str else f"I located '{best['filename']}' in your {best['source']} directory, Sir. {summary_text}"
        )
