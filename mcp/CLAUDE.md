# Project Instructions

## Language
Все комментарии и общение — на русском. Код, git-сообщения — на английском.

## Проект
Telegram MCP-сервер для Claude Code. Позволяет читать чаты, отправлять сообщения, искать, работать с медиа и Stories через Model Context Protocol.

## Стек
- Python ≥3.12, mcp ≥1.26.0
- Telethon (Telegram MTProto клиент)
- pydantic + pydantic-settings (конфиг)
- structlog (логирование)
- google-api-python-client (YouTube интеграция)
- hatchling (сборка)

## Структура
- `src/telegram_mcp/` — основной пакет
- `src/telegram_mcp/runtime.py` — transport/lifespan/runtime wiring
- `src/telegram_mcp/tools/` — MCP tools по доменам
- `src/telegram_mcp/locking.py` — advisory locking для file-based session
- `tests/` — unit/smoke tests
- `scripts/` — ops/auth утилиты (generate_session.py, install-launchd.sh, status.sh, smoke-check.sh)
- `.planning/` — ресёрч-документы

## Команды
- `uv run telegram-mcp` — запуск сервера
- `uv pip install -e .` — установка в dev-режиме
- `PYTHONPATH=src .venv/bin/python -m telegram_mcp health` — быстрый health-check
- `PYTHONPATH=src .venv/bin/python -m telegram_mcp doctor` — расширенная диагностика
- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — unit tests
- `PYTHONPATH=src .venv/bin/python -m compileall src tests` — compile smoke

## Правила
- HTTP-сервер слушает на `127.0.0.1:8799`
- Управляется через launchd
- `.env` содержит Telegram API credentials — никогда не коммитить
- Сессионные файлы (*.session) — в .gitignore
- Предпочитай `TELEGRAM_SESSION_STRING` или file-session с lock; не возвращайся к небезопасному параллельному stdio-паттерну
- MCP tools должны отдавать typed/structured payloads, а не JSON-строки в `str`
