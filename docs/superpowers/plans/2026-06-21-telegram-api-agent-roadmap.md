# Telegram API Agent Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram API features that improve AI-agent context retrieval while keeping default operations safe.

**Architecture:** Implement read-only wrappers first in the `telegram-mcp` runtime, expose them through MCP tool modules, then update the control-plane SurfaceContract and docs. Keep Bot API/business-bot capabilities behind audit-only surfaces until a separate permission model exists.

**Tech Stack:** Python, Telethon, FastMCP, Pydantic, pytest, local control-plane policy JSON.

---

### Task 1: Global Search And Sent Media

**Files:**
- Modify: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/src/telegram_mcp/client_message_search.py`
- Modify: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/src/telegram_mcp/tools/message_tools.py`
- Modify: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/tests/test_registration.py`
- Create/modify focused tests under `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/tests/`

- [x] **Step 1: Write failing registration tests**

Add assertions that `global_search` and `sent_media_search` are registered as read-only tools in the full surface.

- [x] **Step 2: Run failing tests**

Run: `uv run --with pytest --with-editable . pytest tests/test_registration.py -k full_tool_registration_surface_is_stable`

- [x] **Step 3: Implement wrapper methods and MCP tools**

Use Telethon search APIs; return existing `MessagesResult`/`MessageInfo` shapes.

- [x] **Step 4: Run focused tests**

Run: `uv run --with pytest --with-editable . pytest tests/test_registration.py tests/test_server.py`

### Task 2: Thread Context And Forum Tools

**Files:**
- Modify/create runtime client module for thread/forum reads.
- Modify MCP tool registration.
- Add tests for registration and result shape.

- [x] **Step 1: Add read-only `get_thread_replies` wrapper**
- [x] **Step 2: Add read-only `get_discussion_message` wrapper**
- [x] **Step 3: Add read-only `list_forum_topics` wrapper**
- [x] **Step 4: Add tests and run focused suite**

### Task 3: Reaction Analytics

**Files:**
- Modify runtime message/reaction module.
- Modify MCP message tools.
- Add Pydantic result models if existing `MessagesResult` is insufficient.

- [x] **Step 1: Add read-only `get_message_reactions`**
- [x] **Step 2: Add read-only `get_unread_reactions`**
- [x] **Step 3: Keep `read_reactions` separate from read-only analytics**
- [x] **Step 4: Add tests and update surface contract**

### Task 4: Story, Business, Docs Gap

**Files:**
- Modify story docs/tool naming only where behavior already exists.
- Add read-only business audit command in control-plane.
- Add docs-gap audit command in control-plane.

- [x] **Step 1: Promote story analytics docs and contract entries**
- [ ] **Step 2: Add read-only business audit**
- [ ] **Step 3: Add docs-gap audit**
- [ ] **Step 4: Run control-plane doctor and command registry tests**

### Task 5: Verification

- [x] **Step 1: Run runtime focused tests**

Run: `uv run --with pytest --with-editable . pytest tests/test_registration.py tests/test_server.py tests/test_telemetry.py`

- [x] **Step 2: Run control-plane tests**

Run: `pytest tests/test_command_registry.py tests/test_doctor.py tests/test_control_plane.py`

- [x] **Step 3: Run live read-only surface smoke**

Run: `./bin/telegram-mcp-surface --json`

- [ ] **Step 4: Update final operator summary**

Summarize added tools, safety classification, and any remaining gaps.
