"""Configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
import sqlite3

from pydantic_settings import BaseSettings, SettingsConfigDict
from telethon.sessions import StringSession

from .media_policy import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_DOWNLOAD_RETENTION_DAYS,
    DEFAULT_SESSION_DIR,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_id: int
    api_hash: str
    session_string: str | None = None
    session_dir: Path = DEFAULT_SESSION_DIR
    download_dir: Path = DEFAULT_DOWNLOAD_DIR
    download_registry_path: Path | None = None
    download_retention_days: int = DEFAULT_DOWNLOAD_RETENTION_DAYS
    download_cleanup_interval_seconds: int = 60 * 60
    resolve_cache_size: int = 256

    # Runtime / transport (previously raw os.getenv in runtime.py)
    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8799
    mcp_http_path: str = "/mcp"
    mcp_mount_path: str = "/"
    mcp_json_response: bool = True
    mcp_auth_token: str | None = None
    mcp_shared_client: bool = True
    mcp_include_diagnostics: bool = False
    mcp_probe_timeout_seconds: float = 15.0
    cache_ttl: int = 60  # TTL in seconds for read-only API results (0 = disabled)
    dialog_read_cache_ttl_seconds: int = 60
    result_cache_size: int = 256
    read_inflight_dedupe_size: int = 128
    transcript_cache_size: int = 256
    connect_timeout_seconds: float = 15.0
    tool_read_timeout_seconds: float = 30.0
    tool_write_timeout_seconds: float = 30.0
    tool_media_timeout_seconds: float = 120.0
    tool_transcribe_timeout_seconds: float = 45.0
    tool_enrich_timeout_seconds: float = 15.0
    scheduler_read_concurrency: int = 4
    scheduler_write_concurrency: int = 1
    scheduler_media_concurrency: int = 2
    scheduler_transcribe_concurrency: int = 1
    scheduler_enrich_concurrency: int = 4
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_seconds: float = 30.0
    default_voice_transcription_budget: int = 3
    read_max_messages: int = 100
    read_max_chars: int = 40000
    read_max_media_items: int = 25
    write_audit_enabled: bool = True
    write_audit_log_path: Path = Path.home() / "telegram-mcp" / "write-audit.jsonl"
    telemetry_enabled: bool = True
    telemetry_log_dir: Path = Path.home() / "telegram-mcp" / "telemetry"
    telemetry_log_path: Path = Path.home() / "telegram-mcp" / "telemetry.jsonl"
    telemetry_stats_path: Path = Path.home() / "telegram-mcp" / "telemetry-stats.json"
    telemetry_stats_flush_seconds: int = 60
    telemetry_daily_rotation: bool = True
    telemetry_retention_days: int = 30
    telemetry_prometheus_enabled: bool = True
    telemetry_metrics_host: str = "127.0.0.1"
    telemetry_metrics_port: int = 9109
    write_approval_required: bool = False
    approval_host: str = "127.0.0.1"
    approval_port: int = 8798

    @property
    def session_path(self) -> Path:
        return self.session_dir / "session"

    @property
    def media_download_registry_path(self) -> Path:
        return self.download_registry_path or self.download_dir / "download_registry.sqlite3"

    @property
    def uses_file_session(self) -> bool:
        return not bool(self.session_string)

    @property
    def session_backend(self) -> str:
        return "sqlite" if self.uses_file_session else "string"

    def build_session(self) -> str | StringSession:
        if self.session_string:
            return StringSession(self.session_string)
        self._ensure_sqlite_session_schema()
        return str(self.session_path)

    def _ensure_sqlite_session_schema(self) -> None:
        path = self.session_path.with_suffix(".session")
        if not path.exists():
            return
        with sqlite3.connect(path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "select name from sqlite_master where type = 'table'"
                )
            }
            if "sessions" not in tables or "version" not in tables:
                return
            columns = {row[1] for row in conn.execute("pragma table_info(sessions)")}
            if "tmp_auth_key" in columns:
                return
            version_row = conn.execute("select version from version").fetchone()
            version = int(version_row[0]) if version_row else 0
            if version >= 7:
                conn.execute("alter table sessions add column tmp_auth_key blob")
                conn.execute("delete from version")
                conn.execute("insert into version values (8)")

    def ensure_dirs(self) -> None:
        if self.uses_file_session:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.session_dir.chmod(0o700)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.chmod(0o700)
        self.media_download_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_download_registry_path.parent.chmod(0o700)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
