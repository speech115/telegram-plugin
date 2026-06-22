"""Deterministic live-vs-archive routing for facade tools (fail closed)."""

from __future__ import annotations

from datetime import date

from .errors import ToolContractError

NEXT_ACTION_BY_CODE: dict[str, str] = {
    "archive_route_blocked": (
        "Use live Telegram only: tg read today <chat> --limit 30 --json "
        "(then telegram_read mode=fast). Do not use mirror or telecrawl for today/latest."
    ),
    "archive_fallback_blocked": (
        "Repeat the read via tg/telegram_read until data_source=live_telegram; "
        "never answer from archive or mirror for this intent."
    ),
    "live_intent_conflict": (
        "Use telegram_read(day=...) or tg read today for a single calendar day; "
        "remove date_from/date_to for today/recent intents."
    ),
    "invalid_intent": "Classify as today/recent (live) or explicit archive; see telegram://docs/routing.",
}

LIVE_INTENTS = frozenset({"today", "latest", "recent", "current", "live_search", "live_read"})
ARCHIVE_HINTS = frozenset(
    {
        "mirror",
        "telecrawl",
        "archive",
        "archived",
        "historical",
        "backfill",
    }
)


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def classify_read_intent(
    *,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    explicit_intent: str | None = None,
) -> str:
    if explicit_intent:
        intent = _normalized(explicit_intent)
        if intent in LIVE_INTENTS or intent in {"history", "archive", "date_range"}:
            return intent
        raise ToolContractError("invalid_intent", f"unsupported intent: {explicit_intent}")

    if date_from or date_to:
        return "date_range"
    if day:
        return "today"
    return "recent"


def enforce_live_read_route(
    *,
    tool_name: str,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    data_source_hint: str | None = None,
    explicit_intent: str | None = None,
) -> str:
    """Return resolved intent; raise if a live read would use non-live evidence."""

    intent = classify_read_intent(
        day=day,
        date_from=date_from,
        date_to=date_to,
        explicit_intent=explicit_intent,
    )

    hint = _normalized(data_source_hint)
    if hint and hint != "live_telegram":
        for marker in ARCHIVE_HINTS:
            if marker in hint:
                raise ToolContractError(
                    "archive_route_blocked",
                    f"{tool_name} for intent={intent} must use live Telegram, not {hint}",
                )

    if intent in {"today", "latest", "recent", "current", "live_search"}:
        if date_from or date_to:
            raise ToolContractError(
                "live_intent_conflict",
                f"{tool_name}: intent={intent} cannot use date_from/date_to; use live read only",
            )
    return intent


def assert_live_result_data_source(payload: object, *, tool_name: str, intent: str) -> None:
    if not isinstance(payload, dict):
        return
    source = _normalized(str(payload.get("data_source") or "live_telegram"))
    if intent in LIVE_INTENTS or intent in {"today", "recent", "latest", "current"}:
        if source != "live_telegram":
            raise ToolContractError(
                "archive_fallback_blocked",
                f"{tool_name} returned data_source={source} for live intent={intent}",
            )
        for marker in ARCHIVE_HINTS:
            if marker in source:
                raise ToolContractError(
                    "archive_fallback_blocked",
                    f"{tool_name} must not fall back to archive for intent={intent}",
                )


def default_today() -> str:
    return date.today().isoformat()


def format_contract_error(exc: ToolContractError) -> str:
    """Single-line fail-closed error with one next action for agents."""
    action = NEXT_ACTION_BY_CODE.get(
        exc.code,
        "Run tg read today <chat> --limit 30 --json or MCP telegram_read mode=fast.",
    )
    return f"{exc.code}: {exc.message} | next: {action}"