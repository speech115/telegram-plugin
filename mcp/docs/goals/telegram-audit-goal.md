# Telegram Skill / MCP Audit Goal

Ты работаешь в новой Codex CLI сессии.

Цель: целиком заново провести аудит `@telegram` plugin/skill и связанного локального Telegram MCP / Telegram skill слоя, чтобы понять, что можно рефакторить, ускорить, упростить, удалить, стабилизировать и улучшить.

Если доступны OpenAI Developers docs/tools, используй их для проверки актуальных правил Codex CLI, `/goal`, MCP, Apps/Plugins или OpenAI developer docs. Не придумывай поведение OpenAI/Codex из памяти, если есть локальная или официальная документация.

## Critical Source Of Truth

- Treat `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp` as the likely canonical source repo, but verify it.
- Plugin cache, local skills, launchd files, and MCP connector config are read-only audit surfaces unless you prove they are the actual source of truth.
- Do not edit plugin cache or generated plugin bundles directly if a repo source exists.
- Do not read private Telegram message content for this audit.
- Live Telegram usage is limited to tool discovery, health/status, doctor, contract smoke, and bounded read-only smoke against already-safe repo scripts.

## Working Style

- Пиши по-русски, коротко и по делу.
- Сначала inspect, потом plan, потом scoped changes, потом verification.
- Do not stop at findings if a low-risk scoped fix is reachable.
- For broad refactors, public API/schema changes, connector/plugin-cache edits, launchd contract changes, or anything that could alter Telegram write behavior, first produce a concrete plan and risk review before editing.
- Use subagents only when the current Codex CLI session actually supports them. If subagents are unavailable, explicitly say so and simulate the split with separate local audit sections instead of pretending parallel work happened.
- Не пушь в remote.
- Не трогай production, credentials, Telegram session artifacts, `.env`, личные переписки и destructive paths.
- Не отправляй Telegram сообщения. Все write/send paths только через preview/safety audit, если явно не попросили отправить.
- Не ломай существующий rich API ради красивого facade/alias слоя.
- Любой refactor должен быть доказан тестами или live smoke.

## Before Starting

1. Найди фактический Telegram skill/plugin/MCP код на машине.
2. Определи source repo, runtime entrypoints, MCP tools, Telethon usage, launchd/daemon scripts, tests, docs, skills, plugin cache.
3. Прочитай repo-local `AGENTS.md`, `README.md`, `CLAUDE.md`, docs/superpowers, roadmap/specs/plans, если есть.
4. Проверь `git status`, текущую ветку, последние коммиты.
5. Проверь live состояние daemon/status, но только read-only командами.

## Known Context, Verify Again

- В прошлом `telegram-mcp` уже получил speed layer, facade v2, runtime stats, contract smoke, media manifest, app-style aliases и cache proof.
- Это не значит, что всё хорошо. Проверь заново из текущего кода.
- Особенно проверь, нет ли нового структурного долга после этих слоёв.

## Audit Slices

### A. Architecture / Structure

- Где лежит skill, где plugin, где MCP server, где Telethon client wrapper.
- Нет ли монолитов, дублирующих фасадов, циклических зависимостей, лишних abstraction layers.
- Что можно упростить без потери API.
- Что можно удалить как dead code или устаревший compatibility мусор.

### B. Performance

- Telegram read paths, entity/input peer cache, dialog cache, in-flight dedupe.
- Search, media manifest/download, voice transcription, sender resolution.
- Лишние Telethon calls, повторные `get_messages`, лишний `get_sender`, лишний resolve.
- MCP external overhead через `mcporter`, daemon startup, status/doctor paths.
- Найди quick wins и deep wins отдельно.

### C. Stability / Safety

- Session lock risks, reconnect behavior, flood wait handling, circuit breakers.
- Write tools, send/reply safety, preview-only helpers.
- Cache invalidation after all write-like actions: send/edit/delete/forward/pin/unpin/reaction/poll/media.
- Typed errors vs raw backend noise.
- Что может сломаться при долгоживущем daemon.

### D. API / MCP Contract

- Полный список tools.
- Какие tools дублируют друг друга.
- Какие должны быть rich low-level tools, какие facade tools, какие app-style aliases.
- Проверить, что aliases не создают второй backend.
- Проверить output shapes и backward compatibility.
- Проверить external MCP contract smoke, не только unit tests.

### E. Observability / Ops

- `health`, `doctor`, `status`, runtime stats, hit rates, scheduler lanes.
- Есть ли достаточно диагностики, чтобы понять: “ускорение реально работает”.
- Где counters бесполезны, где нужны derived fields, где не надо строить мини-Prometheus.
- Smoke/stress scripts: быстрые, live, optional, flaky risks.

### F. Media / Voice

- Media manifest: не скачивает ли лишнее, не делает ли лишние fetch.
- Download registry, local paths, cleanup policy.
- Voice transcription: только Telegram/Telethon built-in, не локальный Whisper.
- Caps: max messages/chars/media/transcriptions.

### G. Tests / Verification

- Unit tests.
- Contract tests через external MCP.
- Live read-only smoke.
- Stress/cache-pair.
- Compileall/lint/diff hygiene.
- Какие тесты missing, какие flaky, какие слишком завязаны на live Telegram.

## Required Red-Team Loop

1. Составь стратегию улучшений.
2. Сразу сам её атакуй: найди лазейки, риски, ложные оптимизации, потенциальные API breakages.
3. Исправь стратегию.
4. Повтори, пока стратегия не станет практически надёжной.
5. Только после этого реализуй изменения.

## Implementation Gate

1. First produce an audit map and findings.
2. Red-team the findings and proposed strategy.
3. Implement only the safest high-value slice in this session.
4. Keep every patch scoped and reversible.
5. Use scoped staging before commit; never stage unrelated dirty files.

## Priority

- Сначала исправления, которые повышают доказуемость и безопасность: tests, contract smoke, diagnostics, cache invalidation.
- Потом performance quick wins.
- Потом структурный refactor.
- Потом новые возможности.
- Не начинай большой rewrite, если маленький scoped refactor закрывает проблему.

## Deliverables

1. Короткая карта системы: skill/plugin/MCP/Telethon/runtime/tests.
2. Таблица findings: severity, file/path, issue, fix, verification.
3. Исправленная стратегия.
4. Реализованные patches.
5. Verification log с конкретными командами и результатами.
6. Scoped commit, если все проверки зелёные.
7. Короткий next-layer backlog: что осталось, почему не делалось сейчас.

## Verification Minimum

- `git status --short` before staging.
- `git diff --check`.
- strongest local unit suite.
- `compileall` для Python.
- repo canonical check script, если есть.
- daemon/status read-only check, если daemon есть.
- external MCP contract smoke, если есть.
- live read-only smoke только без отправки сообщений.
- scoped `git diff --cached --stat` before commit.
- if daemon code or registered tools changed: restart local daemon and run live external contract smoke after restart.

## Stop Conditions

- Если находишь риск data loss, production impact, credential/session mutation или Telegram write/send side effect — остановись и явно спроси.
- Если public API/schema надо менять несовместимо — сначала предложи migration/compat plan.
- Если live Telegram недоступен — продолжай offline audit, но явно пометь, что live verification не выполнен.

## Final Answer Shape

Финальный ответ должен быть коротким:

- что изменено;
- чем проверено;
- commit hash;
- что осталось.
