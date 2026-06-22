"""Portable agent routing docs served as MCP resources."""

from __future__ import annotations

from pathlib import Path

AGENT_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "agent"

DOC_TOPICS: dict[str, str] = {
    "index": "index.md",
    "routing": "routing.md",
    "tools": "tools.md",
    "sources": "sources.md",
    "writes": "writes.md",
    "media": "media.md",
}


class AgentDocError(ValueError):
    """Raised when a requested agent doc topic is unknown or missing on disk."""


def list_doc_topics() -> list[str]:
    return sorted(DOC_TOPICS)


def load_doc_topic(topic: str) -> str:
    normalized = topic.strip().lower()
    filename = DOC_TOPICS.get(normalized)
    if filename is None:
        known = ", ".join(list_doc_topics())
        raise AgentDocError(f"Unknown doc topic {topic!r}. Known topics: {known}")

    path = AGENT_DOCS_DIR / filename
    if not path.is_file():
        raise AgentDocError(f"Agent doc file missing: {path.name}")

    return path.read_text(encoding="utf-8")