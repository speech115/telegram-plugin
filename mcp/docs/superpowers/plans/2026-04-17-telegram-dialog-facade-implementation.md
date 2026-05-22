# Telegram Dialog Facade Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a high-level live Telegram dialog facade to `telegram-mcp` so common read/send/reply tasks use one stable front door without removing the existing rich MCP API.

**Architecture:** Keep the current rich tool surface intact and add a new facade layer inside the same server. The facade resolves human dialog queries into a stable `dialog_ref`, routes all read flows through one shared internal read engine, and exposes a small set of task-oriented MCP tools. This plan intentionally covers Shipping Slice 1 only; Codex routing and app connector wiring should be separate follow-up plans after the facade is merged and exercised.

**Tech Stack:** Python 3.13, Telethon, Pydantic models in `telegram_mcp.types`, MCP tool wrappers in `telegram_mcp.tools`, unittest-based test suite.

---

## File map

**Create**

- `docs/superpowers/plans/2026-04-17-telegram-dialog-facade-implementation.md`
- `src/telegram_mcp/tools/dialog_facade_tools.py`
- `tests/test_dialog_facade_tools.py`

**Modify**

- `src/telegram_mcp/types.py`
- `src/telegram_mcp/client.py`
- `src/telegram_mcp/tools/__init__.py`
- `src/telegram_mcp/server.py`
- `README.md`
- `tests/test_client.py`
- `tests/test_registration.py`

**Keep untouched**

- Existing rich message/chat/contact/media/group/story tools and their names
- `telegram-mirror` routing/docs
- app connector wiring outside this repo

## Scope note

This spec spans three subsystems:

1. `telegram-mcp` facade backend
2. Codex routing updates
3. app / connector front door

This plan intentionally covers **only subsystem 1**. Do not mix routing or app-connector work into this implementation branch. After this lands and is exercised, create:

- one follow-up plan for Codex routing
- one follow-up plan for app / connector wiring

## Chunk 1: Client Contract And Shared Read Engine

### Task 1: Add failing client tests for dialog resolution and canonical handles

**Files:**
- Modify: `tests/test_client.py`
- Modify: `src/telegram_mcp/types.py`
- Modify: `src/telegram_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

Add new client tests that describe the canonical facade contract:

```python
def test_resolve_dialog_returns_stable_dialog_ref(self):
    settings = Settings(api_id=1, api_hash="hash")

    with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
        wrapper = TelegramWrapper(settings)

    result = _run(wrapper.resolve_dialog("@example_user"))

    self.assertEqual(result.id, 1)
    self.assertEqual(result.username, "example_user")
    self.assertEqual(result.dialog_ref, "tg://dialog/unknown/1")
    self.assertEqual(result.resolved_from, "@example_user")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client.ClientTests.test_resolve_dialog_returns_stable_dialog_ref
```

Expected: FAIL because `TelegramWrapper.resolve_dialog()` and `DialogHandle` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add facade contract models to `src/telegram_mcp/types.py`:

```python
class DialogHandle(BaseModel):
    dialog_ref: str
    id: int
    name: str
    type: str
    username: str | None = None
    resolved_from: str
    match_confidence: float = 1.0
```

Add a client method in `src/telegram_mcp/client.py`:

```python
async def resolve_dialog(self, query: str | int) -> DialogHandle:
    entity = await self._resolve_entity(query)
    chat = self._chat_info_from_entity(entity)
    return DialogHandle(
        dialog_ref=f"tg://dialog/{chat.type}/{chat.id}",
        id=chat.id,
        name=chat.name,
        type=chat.type,
        username=chat.username,
        resolved_from=str(query),
        match_confidence=1.0,
    )
```

Also add a tiny parser helper for later facade reads:

```python
def _coerce_dialog_query(self, chat: str | int) -> str | int:
    if isinstance(chat, str) and chat.startswith("tg://dialog/"):
        _prefix, _dialog, peer_type, peer_id = chat.split("/", 3)
        return int(peer_id)
    return chat
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client.ClientTests.test_resolve_dialog_returns_stable_dialog_ref
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_client.py src/telegram_mcp/types.py src/telegram_mcp/client.py
git commit -m "feat: add dialog handle contract"
```

### Task 2: Add the shared internal read engine and date-range facade read

**Files:**
- Modify: `tests/test_client.py`
- Modify: `src/telegram_mcp/types.py`
- Modify: `src/telegram_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

Add tests that pin the shared envelope and no-mirror live contract:

```python
def test_read_dialog_by_date_returns_stable_envelope(self):
    settings = Settings(api_id=1, api_hash="hash")

    with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
        wrapper = TelegramWrapper(settings)

    result = _run(
        wrapper.read_dialog_by_date(
            chat="@example_user",
            date_from="2026-04-16",
            date_to="2026-04-16",
            total_limit=20,
        )
    )

    self.assertEqual(result.chat.dialog_ref, "tg://dialog/unknown/1")
    self.assertEqual(result.message_count, 1)
    self.assertEqual(result.range.date_from, "2026-04-16")
    self.assertEqual(result.range.date_to, "2026-04-16")
    self.assertEqual(result.data_source, "live_telegram")
```

Also add a `dialog_ref` reuse test:

```python
def test_read_dialog_by_date_accepts_dialog_ref(self):
    ...
    handle = _run(wrapper.resolve_dialog("@example_user"))
    result = _run(
        wrapper.read_dialog_by_date(
            chat=handle.dialog_ref,
            date_from="2026-04-16",
            date_to="2026-04-16",
        )
    )
    self.assertEqual(result.message_count, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_client.ClientTests.test_read_dialog_by_date_returns_stable_envelope \
  tests.test_client.ClientTests.test_read_dialog_by_date_accepts_dialog_ref
```

Expected: FAIL because the facade read engine and read result model do not exist.

- [ ] **Step 3: Write minimal implementation**

Add new typed envelope models in `src/telegram_mcp/types.py`:

```python
class DialogReadRange(BaseModel):
    date_from: str | None = None
    date_to: str | None = None


class DialogReadResult(BaseModel):
    chat: DialogHandle
    messages: list[MessageInfo]
    message_count: int
    has_more_before: bool = False
    next_offset_id: int | None = None
    range: DialogReadRange
    data_source: str = "live_telegram"
```

Implement one shared private engine in `src/telegram_mcp/client.py`:

```python
async def _read_dialog_core(
    self,
    *,
    chat: str | int,
    limit: int,
    offset_id: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
) -> DialogReadResult:
    resolved_chat = self._coerce_dialog_query(chat)
    handle = await self.resolve_dialog(resolved_chat)
    slice_result = await self.read_dialog_slice(
        chat=resolved_chat,
        limit=limit,
        offset_id=offset_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DialogReadResult(
        chat=handle,
        messages=slice_result.messages,
        message_count=len(slice_result.messages),
        has_more_before=slice_result.has_more_before,
        next_offset_id=slice_result.next_offset_id,
        range=DialogReadRange(date_from=date_from, date_to=date_to),
        data_source="live_telegram",
    )
```

Then wrap it:

```python
async def read_dialog_by_date(...):
    return await self._read_dialog_core(...)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client -v
```

Expected: existing client tests still pass, including the new facade tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_client.py src/telegram_mcp/types.py src/telegram_mcp/client.py
git commit -m "feat: add dialog facade read engine"
```

## Chunk 2: Facade Wrappers And MCP Wiring

### Task 3: Add recent/search/reply facade behavior on top of the same engine

**Files:**
- Modify: `tests/test_client.py`
- Modify: `src/telegram_mcp/client.py`
- Modify: `src/telegram_mcp/types.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

Add tests for the remaining client-level facade behaviors:

```python
def test_read_recent_dialog_uses_live_envelope(self):
    ...
    result = _run(wrapper.read_recent_dialog(chat="@example_user", limit=2))
    self.assertEqual(result.message_count, 2)
    self.assertEqual(result.data_source, "live_telegram")


def test_search_dialog_messages_scopes_to_one_dialog(self):
    ...
    result = _run(wrapper.search_dialog_messages(chat="@example_user", query="hello", limit=5))
    self.assertEqual(result.chat.username, "example_user")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client.ClientTests.test_read_recent_dialog_uses_live_envelope tests.test_client.ClientTests.test_search_dialog_messages_scopes_to_one_dialog
```

Expected: FAIL because the client wrapper methods are missing.

- [ ] **Step 3: Write minimal implementation**

Add lightweight client wrappers in `src/telegram_mcp/client.py`:

```python
async def read_recent_dialog(self, chat: str | int, limit: int = 50) -> DialogReadResult:
    return await self._read_dialog_core(chat=chat, limit=limit)


async def search_dialog_messages(
    self,
    chat: str | int,
    query: str,
    limit: int = 20,
) -> DialogReadResult:
    resolved_chat = self._coerce_dialog_query(chat)
    handle = await self.resolve_dialog(resolved_chat)
    messages = await self.search_messages(query=query, chat=resolved_chat, limit=limit)
    return DialogReadResult(
        chat=handle,
        messages=messages,
        message_count=len(messages),
        has_more_before=False,
        next_offset_id=None,
        range=DialogReadRange(),
        data_source="live_telegram",
    )
```

Keep `send_dialog_message` and `reply_in_dialog` as thin aliases over existing client
methods so the facade and raw API stay aligned:

```python
async def send_dialog_message(...):
    return await self.send_message(...)

async def reply_in_dialog(...):
    return await self.reply_to_message(...)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_client.py src/telegram_mcp/client.py src/telegram_mcp/types.py
git commit -m "feat: add dialog facade client wrappers"
```

### Task 4: Add MCP tool wrappers and expose them through the public server surface

**Files:**
- Create: `src/telegram_mcp/tools/dialog_facade_tools.py`
- Create: `tests/test_dialog_facade_tools.py`
- Modify: `src/telegram_mcp/tools/__init__.py`
- Modify: `src/telegram_mcp/server.py`
- Modify: `tests/test_registration.py`
- Test: `tests/test_dialog_facade_tools.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dialog_facade_tools.py` with focused wrapper tests:

```python
import unittest
from unittest.mock import AsyncMock, patch

from telegram_mcp import server
from telegram_mcp.types import DialogHandle, DialogReadResult, DialogReadRange


class DialogFacadeToolTests(unittest.TestCase):
    def test_resolve_dialog_returns_dialog_handle(self):
        wrapper = AsyncMock()
        wrapper.resolve_dialog.return_value = DialogHandle(
            dialog_ref="tg://dialog/user/1",
            id=1,
            name="Andrei",
            type="user",
            username="example_user",
            resolved_from="@example_user",
            match_confidence=1.0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.resolve_dialog("@example_user"))

        self.assertEqual(result.dialog_ref, "tg://dialog/user/1")
```

Update `tests/test_registration.py` so the expected tool list includes:

- `resolve_dialog`
- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`
- `send_dialog_message`
- `reply_in_dialog`

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_dialog_facade_tools tests.test_registration -v
```

Expected: FAIL because the facade tool module and exports do not exist.

- [ ] **Step 3: Write minimal implementation**

Create `src/telegram_mcp/tools/dialog_facade_tools.py`:

```python
from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import DialogHandle, DialogReadResult, MessageInfo

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


async def resolve_dialog(query: str) -> DialogHandle:
    tg = await runtime.get_tg()
    return await tg.resolve_dialog(query)


async def read_dialog_by_date(chat: str | int, date_from: str, date_to: str, page_size: int = 50) -> DialogReadResult:
    tg = await runtime.get_tg()
    return await tg.read_dialog_by_date(chat=chat, date_from=date_from, date_to=date_to, total_limit=page_size)


async def read_recent_dialog(chat: str | int, limit: int = 50) -> DialogReadResult:
    tg = await runtime.get_tg()
    return await tg.read_recent_dialog(chat=chat, limit=limit)


async def search_dialog_messages(chat: str | int, query: str, limit: int = 20) -> DialogReadResult:
    tg = await runtime.get_tg()
    return await tg.search_dialog_messages(chat=chat, query=query, limit=limit)


async def send_dialog_message(chat: str | int, text: str, parse_mode: str = "md") -> MessageInfo:
    tg = await runtime.get_tg()
    return await tg.send_dialog_message(chat=chat, text=text, parse_mode=parse_mode)


async def reply_in_dialog(chat: str | int, message_id: int, text: str, parse_mode: str = "md") -> MessageInfo:
    tg = await runtime.get_tg()
    return await tg.reply_in_dialog(chat=chat, message_id=message_id, text=text, parse_mode=parse_mode)
```

Wire it through:

- `src/telegram_mcp/tools/__init__.py`
- `src/telegram_mcp/server.py`
- `register_all_tools(mcp)`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_dialog_facade_tools tests.test_registration -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dialog_facade_tools.py tests/test_registration.py src/telegram_mcp/tools/dialog_facade_tools.py src/telegram_mcp/tools/__init__.py src/telegram_mcp/server.py
git commit -m "feat: expose telegram dialog facade tools"
```

## Chunk 3: Documentation And Release Gate

### Task 5: Document the facade and run the release gate for slice 1

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-17-telegram-app-facade-design.md` (status line only if implementation actually lands)
- Test: `tests/test_client.py`
- Test: `tests/test_dialog_facade_tools.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the failing doc/test delta**

Update `README.md` to introduce the facade as a first-class concept:

```md
## Dialog facade

High-level live-dialog tools:

- `resolve_dialog`
- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`
- `send_dialog_message`
- `reply_in_dialog`

Use these for normal conversational Telegram work. Use the existing rich tool set for
power-user operations such as contacts, stories, groups, media, and moderation.
```

Also update any tool inventory text to distinguish:

- rich Telegram MCP API
- high-level dialog facade

- [ ] **Step 2: Run verification before touching docs status**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest tests.test_client tests.test_dialog_facade_tools tests.test_registration
PYTHONPATH=src .venv/bin/python -m compileall src tests
```

Expected:

- unittest suite passes
- compileall completes without syntax errors

- [ ] **Step 3: Write minimal documentation**

Update `README.md` with:

- facade purpose
- which tasks should use facade vs rich API
- one example read command and one example reply command

If implementation is complete and verified, change the spec status line from:

```md
- Status: `proposed`
```

to:

```md
- Status: `implemented`
```

- [ ] **Step 4: Run final verification**

Run:

```bash
cd ${TELEGRAM_MCP_REPO:-./mcp}
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src .venv/bin/python -m compileall src tests
```

Expected: full test suite green, no compile errors.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-17-telegram-app-facade-design.md tests/test_client.py tests/test_dialog_facade_tools.py tests/test_registration.py src/telegram_mcp/types.py src/telegram_mcp/client.py src/telegram_mcp/tools/dialog_facade_tools.py src/telegram_mcp/tools/__init__.py src/telegram_mcp/server.py
git commit -m "feat: ship telegram dialog facade"
```

## Follow-up plans required after this merges

Do **not** implement these in this branch. Write separate plans:

1. Codex routing plan
   - prefer facade for normal live Telegram work
   - keep `telegram-mirror` for archive and analytics paths

2. App / connector plan
   - expose the facade through app-style Telegram actions
   - keep app surface intentionally smaller than the rich MCP API

## Completion checklist

- [ ] `DialogHandle`, `DialogReadRange`, and `DialogReadResult` exist and are typed
- [ ] `dialog_ref` is stable and accepted by facade read tools
- [ ] all facade reads go through one shared internal client engine
- [ ] facade never silently falls back to mirror data
- [ ] new tool names are registered and exported through `server.py`
- [ ] README explains facade vs rich API
- [ ] targeted tests pass
- [ ] full suite passes
