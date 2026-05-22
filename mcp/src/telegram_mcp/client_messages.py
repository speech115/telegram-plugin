"""Message operations public entrypoint.

The implementation lives in smaller message-client modules. Keep this module as
the stable import target for TelegramWrapper and downstream code.
"""

from __future__ import annotations

from .client_message_operations import MessageOperationsMixin

__all__ = ["MessageOperationsMixin"]
