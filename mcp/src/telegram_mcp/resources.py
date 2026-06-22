"""MCP resources for static/cacheable Telegram data."""

from __future__ import annotations

from .agent_docs import AgentDocError, list_doc_topics, load_doc_topic
from .runtime import get_tg, mcp


@mcp.resource(
    "telegram://me",
    name="current_user",
    description="Current Telegram user info",
    mime_type="application/json",
)
async def me_resource() -> dict[str, object]:
    tg = await get_tg()
    info = await tg.get_me()
    return info.model_dump(mode="json")


@mcp.resource(
    "telegram://docs/{topic}",
    name="agent_doc",
    title="Telegram agent routing doc",
    description=(
        "Portable agent routing/safety markdown. Topics: "
        + ", ".join(list_doc_topics())
        + ". Start with index or routing before tool calls."
    ),
    mime_type="text/markdown",
)
def agent_doc_resource(topic: str) -> str:
    """Return one agent doc topic as markdown (telegram://docs/routing, etc.)."""
    try:
        return load_doc_topic(topic)
    except AgentDocError as exc:
        return f"# Doc unavailable\n\n{exc}\n"