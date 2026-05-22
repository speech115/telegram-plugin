# Workspace Instructions

## Language
Всегда отвечай на русском. Код, git, CLI — на английском.

## Что это
Telegram MCP-сервер — мост между Claude Code и Telegram через Telethon.

## Роль агента
Разработчик MCP-сервера. Код в `src/telegram_mcp/`.

## Хорошее изменение
- Новые MCP-tools для работы с Telegram
- Улучшение error handling и логирования
- Тесты
- Typed/structured outputs вместо JSON-строк
- Улучшение health/doctor и ops tooling
- Изменения в `runtime.py` и `tools/`, которые упрощают поддержку и agent UX
- Для Telegram voice использовать только встроенную Telegram/Telethon
  транскрибацию (`TranscribeAudioRequest`). Локальный Whisper, особенно на CPU,
  для Telegram voice здесь запрещён.

## Плохое изменение
- Хардкод credentials
- Изменение порта без обновления launchd-конфига
- Удаление существующих MCP-tools без миграции
- Возврат к stringified error responses вместо нормальных MCP ошибок и typed payloads
- Возврат к stdio/multi-process паттерну, который снова откроет `*.session` lock проблемы

## Граница
Этот репо — только MCP-сервер. Бот-постер — в `telegram-posting`. Метарепо — в `telegram-digest`.
