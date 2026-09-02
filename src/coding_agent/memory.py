"""Local, human-readable long-term memory for the coding agent.

The Markdown file is the source users can inspect and edit.  A small JSON
index stores hashes and metadata used for deduplication and lexical retrieval.
No network service or vector database is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping


MEMORY_VERSION = 1
DEFAULT_MEMORY_CONTEXT_CHARS = 4_000
MAX_MEMORY_ITEMS_PER_EXTRACTION = 5
MAX_MEMORY_CONTENT_CHARS = 300
SCOPES = ("global", "project")
SECTIONS = ("user_profile", "project_context", "decisions", "conventions", "lessons")
SECTION_TITLES = {
    "user_profile": "User Profile",
    "project_context": "Project Context",
    "decisions": "Decisions",
    "conventions": "Conventions",
    "lessons": "Lessons",
}
SENSITIVE_PATTERN = re.compile(
    r"(?:api[_ -]?key|authorization|bearer|password|passwd|secret|token|private key|"
    r"-----begin [^-]+ private key-----)",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _content_hash(content: str) -> str:
    return hashlib.sha256(_normalise(content).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryItem:
    id: str
    scope: str
    section: str
    content: str
    tags: tuple[str, ...] = ()
    source_session: str | None = None
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    active: bool = True


@dataclass(frozen=True)
class MemoryCandidate:
    scope: str
    section: str
    content: str
    tags: tuple[str, ...] = ()
    confidence: float = 1.0

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryCandidate | None":
        scope = value.get("scope")
        section = value.get("section")
        content = value.get("content")
        tags = value.get("tags", [])
        confidence = value.get("confidence", 1.0)
        if scope not in SCOPES or section not in SECTIONS or not isinstance(content, str):
            return None
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            tags = []
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        content = " ".join(content.split())
        return cls(scope, section, content, tuple(_normalise(tag) for tag in tags if tag.strip()), confidence)


@dataclass(frozen=True)
class MemoryLoad:
    items: tuple[MemoryItem, ...]
    global_count: int
    project_count: int
    rendered: str


class MemoryStore:
    """Read, retrieve and atomically update global and project memory files."""

    def __init__(self, workspace: Path, global_root: Path | None = None) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        root = Path(global_root).expanduser() if global_root is not None else Path.home() / ".coding-agent"
        self.global_path = root / "memory.md"
        self.global_index_path = root / "memory-index.json"
        self.project_root = self.workspace / ".coding-agent"
        self.project_path = self.project_root / "memory.md"
        self.project_index_path = self.project_root / "memory-index.json"

    def load(self, scope: str) -> list[MemoryItem]:
        if scope not in SCOPES:
            raise ValueError(f"Unknown memory scope: {scope}")
        path, index_path = self._paths(scope)
        metadata = self._load_index(index_path)
        parsed = self._parse_markdown(path, scope)
        items: list[MemoryItem] = []
        for content, section in parsed:
            key = _content_hash(content)
            old = metadata.get(key, {})
            items.append(
                MemoryItem(
                    id=str(old.get("id") or f"memory-{key[:16]}"),
                    scope=scope,
                    section=section,
                    content=content,
                    tags=tuple(item for item in old.get("tags", []) if isinstance(item, str)),
                    source_session=old.get("source_session") if isinstance(old.get("source_session"), str) else None,
                    confidence=float(old.get("confidence", 1.0) or 1.0),
                    created_at=str(old.get("created_at") or ""),
                    updated_at=str(old.get("updated_at") or ""),
                    active=bool(old.get("active", True)),
                )
            )
        if parsed and not metadata:
            try:
                self._write_scope(scope, items)
            except OSError:
                pass
        return [item for item in items if item.active]

    def load_relevant(self, task: str, max_chars: int = DEFAULT_MEMORY_CONTEXT_CHARS) -> MemoryLoad:
        if max_chars < 1:
            raise ValueError("Memory context budget must be positive.")
        global_items = self.load("global")
        project_items = self.load("project")
        selected = self._rank(task, global_items, project_items)
        rendered_items: list[str] = []
        used = 0
        for item in selected:
            line = f"[{item.scope}/{item.section}] - {item.content}"
            if used + len(line) + 1 > max_chars:
                continue
            rendered_items.append(line)
            used += len(line) + 1
        rendered = "\n".join(rendered_items)
        return MemoryLoad(tuple(selected), len(global_items), len(project_items), rendered)

    def save_candidates(self, candidates: Iterable[MemoryCandidate], source_session: str | None = None) -> int:
        grouped: dict[str, list[MemoryCandidate]] = {scope: [] for scope in SCOPES}
        for candidate in candidates:
            valid = self._validate_candidate(candidate)
            if valid is not None:
                grouped[valid.scope].append(valid)
        saved = 0
        for scope, values in grouped.items():
            if not values:
                continue
            existing = self.load(scope)
            by_hash = {_content_hash(item.content): item for item in existing}
            now = _timestamp()
            for candidate in values:
                key = _content_hash(candidate.content)
                if key in by_hash:
                    old = by_hash[key]
                    by_hash[key] = MemoryItem(
                        old.id, old.scope, old.section, old.content,
                        tuple(dict.fromkeys((*old.tags, *candidate.tags))),
                        source_session or old.source_session,
                        max(old.confidence, candidate.confidence), old.created_at or now, now, True,
                    )
                else:
                    by_hash[key] = MemoryItem(
                        f"memory-{key[:16]}", candidate.scope, candidate.section, candidate.content,
                        candidate.tags, source_session, candidate.confidence, now, now, True,
                    )
                    saved += 1
            self._write_scope(scope, list(by_hash.values()))
        return saved

    def read_markdown(self, scope: str) -> str:
        path, _ = self._paths(scope)
        if not path.is_file():
            return "# Long-term Memory\n"
        return path.read_text(encoding="utf-8")

    def _rank(self, task: str, global_items: list[MemoryItem], project_items: list[MemoryItem]) -> list[MemoryItem]:
        query = set(TOKEN_PATTERN.findall(task.casefold()))
        def score(item: MemoryItem) -> tuple[int, int]:
            tokens = set(TOKEN_PATTERN.findall((item.content + " " + " ".join(item.tags)).casefold()))
            match = len(query & tokens)
            scope_bonus = 2 if item.scope == "project" else 0
            return match + scope_bonus, 1 if item.updated_at else 0
        ordered = sorted(project_items + global_items, key=score, reverse=True)
        matched = [item for item in ordered if score(item)[0] > (2 if item.scope == "project" else 0)]
        fallback = [item for item in ordered if item not in matched]
        return (matched + fallback)[:16]

    def _validate_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate | None:
        if candidate.scope not in SCOPES or candidate.section not in SECTIONS:
            return None
        if not candidate.content or len(candidate.content) > MAX_MEMORY_CONTENT_CHARS:
            return None
        if SENSITIVE_PATTERN.search(candidate.content):
            return None
        if not 0.0 <= candidate.confidence <= 1.0:
            return None
        if candidate.scope == "global" and candidate.section != "user_profile":
            return None
        if candidate.scope == "project" and candidate.section == "user_profile":
            return None
        return candidate

    def _paths(self, scope: str) -> tuple[Path, Path]:
        if scope == "global":
            return self.global_path, self.global_index_path
        if scope == "project":
            return self.project_path, self.project_index_path
        raise ValueError(f"Unknown memory scope: {scope}")

    def _load_index(self, path: Path) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("version") != MEMORY_VERSION or not isinstance(value.get("items"), list):
                return {}
            return {
                item.get("content_hash"): item
                for item in value["items"]
                if isinstance(item, dict) and isinstance(item.get("content_hash"), str)
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _parse_markdown(path: Path, scope: str) -> list[tuple[str, str]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return []
        sections: dict[str, str] = {title: section for section, title in SECTION_TITLES.items()}
        current: str | None = None
        result: list[tuple[str, str]] = []
        for line in lines:
            if line.startswith("## "):
                current = sections.get(line[3:].strip())
            elif current and line.startswith("- "):
                content = line[2:].strip()
                if content:
                    result.append((content, current))
        return result

    def _write_scope(self, scope: str, items: list[MemoryItem]) -> None:
        path, index_path = self._paths(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        by_section = {section: [] for section in SECTIONS}
        for item in items:
            by_section.setdefault(item.section, []).append(item)
        markdown = ["# Long-term Memory", ""]
        for section in SECTIONS:
            markdown.extend([f"## {SECTION_TITLES[section]}", ""])
            markdown.extend(f"- {item.content}" for item in by_section.get(section, []))
            markdown.append("")
        index = {
            "version": MEMORY_VERSION,
            "items": [
                {
                    "id": item.id, "scope": item.scope, "section": item.section,
                    "content_hash": _content_hash(item.content), "tags": list(item.tags),
                    "source_session": item.source_session, "confidence": item.confidence,
                    "created_at": item.created_at, "updated_at": item.updated_at, "active": item.active,
                }
                for item in items
            ],
        }
        self._atomic_write(path, "\n".join(markdown) + "\n")
        self._atomic_write(index_path, json.dumps(index, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        try:
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


EXTRACTION_SYSTEM = """Extract only stable, reusable coding-agent memories. Return strict JSON with a memories array.
Global memories must be user preferences or working habits. Project memories must be project facts,
conventions, decisions, or lessons. Never include credentials, secrets, raw code, temporary test output,
or instructions that conflict with the current system message."""


class MemoryExtractor:
    """Model-backed candidate extraction with deterministic output validation."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def extract(
        self,
        task: str,
        answer: str,
        changed_files: Iterable[str] = (),
        explicit: bool = False,
    ) -> list[MemoryCandidate]:
        prompt = (
            "Task:\n" + task + "\n\nFinal answer:\n" + answer +
            "\n\nChanged files:\n" + ", ".join(changed_files) +
            f"\n\nExplicit memory request: {explicit}\n"
            "Return at most five stable memories."
        )
        response = self.client.complete(
            [{"role": "system", "content": EXTRACTION_SYSTEM}, {"role": "user", "content": prompt}],
            tools=None,
        )
        content = response.content if isinstance(getattr(response, "content", None), str) else ""
        try:
            value = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return []
        raw = value.get("memories", []) if isinstance(value, dict) else []
        if not isinstance(raw, list):
            return []
        candidates: list[MemoryCandidate] = []
        for item in raw[:MAX_MEMORY_ITEMS_PER_EXTRACTION]:
            if isinstance(item, Mapping):
                candidate = MemoryCandidate.from_mapping(item)
                if candidate is not None:
                    candidates.append(candidate)
        return candidates


class MemoryManager:
    """Facade used by Agent and GUI to load and persist long-term memory."""

    def __init__(self, workspace: Path, client: Any, *, global_root: Path | None = None, max_context_chars: int = DEFAULT_MEMORY_CONTEXT_CHARS) -> None:
        self.store = MemoryStore(workspace, global_root=global_root)
        self.extractor = MemoryExtractor(client)
        self.max_context_chars = max_context_chars

    def load_for_task(self, task: str) -> MemoryLoad:
        return self.store.load_relevant(task, self.max_context_chars)

    def extract_and_save(
        self,
        task: str,
        answer: str,
        changed_files: Iterable[str] = (),
        source_session: str | None = None,
        explicit: bool = False,
    ) -> int:
        candidates = self.extractor.extract(task, answer, changed_files, explicit)
        return self.store.save_candidates(candidates, source_session=source_session)
