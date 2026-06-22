"""Server-side send confirmations with optional human approval."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .errors import ToolContractError

ApprovalState = Literal["pending", "approved", "rejected", "expired", "used"]


@dataclass
class SendConfirmationRecord:
    preview_id: str
    expires_at: float
    payload: dict[str, object]
    preview_text: str
    approval_state: ApprovalState
    risk_class: str = "standard"
    confirmation_token: str = ""
    one_time_nonce: str = ""


_GLOBAL_STORE: SendConfirmationStore | None = None


def bind_confirmation_store(store: SendConfirmationStore) -> None:
    global _GLOBAL_STORE
    _GLOBAL_STORE = store


def get_confirmation_store() -> SendConfirmationStore:
    if _GLOBAL_STORE is None:
        raise RuntimeError("send confirmation store is not initialized")
    return _GLOBAL_STORE


class SendConfirmationStore:
    def __init__(self, *, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, SendConfirmationRecord] = {}
        self._token_index: dict[str, str] = {}

    def _now(self) -> float:
        return time.time()

    def _resolve_key(self, key: str) -> str | None:
        if key in self._records:
            return key
        return self._token_index.get(key)

    def _expire_if_needed(self, preview_id: str, record: SendConfirmationRecord) -> SendConfirmationRecord:
        if record.approval_state in {"used", "rejected", "expired"}:
            return record
        if self._now() > record.expires_at:
            record.approval_state = "expired"
            self._records[preview_id] = record
        return record

    def mint(
        self,
        payload: dict[str, object],
        *,
        preview_text: str,
        risk_class: str = "standard",
    ) -> tuple[str, str, datetime]:
        preview_id = secrets.token_urlsafe(16)
        token = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(12)
        expires_at = self._now() + self._ttl_seconds
        self._records[preview_id] = SendConfirmationRecord(
            preview_id=preview_id,
            expires_at=expires_at,
            payload=dict(payload),
            preview_text=preview_text,
            approval_state="pending",
            risk_class=risk_class,
            confirmation_token=token,
            one_time_nonce=nonce,
        )
        self._token_index[token] = preview_id
        return preview_id, token, datetime.fromtimestamp(expires_at, tz=timezone.utc)

    def get(self, key: str) -> SendConfirmationRecord | None:
        preview_id = self._resolve_key(key)
        if preview_id is None:
            return None
        record = self._records.get(preview_id)
        if record is None:
            return None
        return self._expire_if_needed(preview_id, record)

    def approve(self, token: str) -> SendConfirmationRecord:
        record = self.get(token)
        if record is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown")
        if record.approval_state == "expired":
            raise ToolContractError("expired_confirmation_token", "confirmation token has expired")
        if record.approval_state == "used":
            raise ToolContractError("invalid_confirmation_token", "confirmation token was already used")
        if record.approval_state == "rejected":
            raise ToolContractError("confirmation_rejected", "confirmation was rejected by the operator")
        record.approval_state = "approved"
        self._records[token] = record
        return record

    def reject(self, token: str) -> SendConfirmationRecord:
        record = self.get(token)
        if record is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown")
        record.approval_state = "rejected"
        self._records[token] = record
        return record

    def consume(
        self,
        key: str | None,
        expected: dict[str, object] | None,
        *,
        approval_required: bool,
        preview_id_only: bool = False,
    ) -> SendConfirmationRecord:
        if not key:
            raise ToolContractError(
                "missing_confirmation_token",
                "send/reply requires preview_id or confirmation_token from prepare_*",
            )
        resolved = self._resolve_key(key)
        if resolved is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown or already used")
        record = self._records.get(resolved)
        if record is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown or already used")
        record = self._expire_if_needed(resolved, record)
        if record.approval_state == "expired":
            raise ToolContractError("expired_confirmation_token", "confirmation token has expired")
        if record.approval_state == "used":
            raise ToolContractError("invalid_confirmation_token", "confirmation token was already used")
        if record.approval_state == "rejected":
            raise ToolContractError("confirmation_rejected", "confirmation was rejected by the operator")
        if approval_required and record.approval_state != "approved":
            raise ToolContractError(
                "human_approval_required",
                "open the approval URL and click Approve before sending",
            )
        if not preview_id_only and expected is not None and record.payload != expected:
            raise ToolContractError(
                "confirmation_payload_mismatch",
                "send/reply arguments do not match the preview confirmation",
            )
        record.approval_state = "used"
        self._records.pop(resolved, None)
        self._token_index.pop(record.confirmation_token, None)
        return record