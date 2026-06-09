"""watchdog-driven incremental ingestion.

One handler per app log file. On `on_modified`, read from the per-file byte
offset to EOF, parse, and upsert into Chroma. Idempotent via content-hash
IDs (same line embedded twice = single Chroma doc).

The Observer threads run outside asyncio. Embedding + upsert calls are sync
HTTP — that's fine in a thread context.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from log_dashboard.config import Settings
from log_dashboard.ingest.embeddings import filter_for_ingest
from log_dashboard.ingest.reader import parse_and_fold
from log_dashboard.ingest.spec import APP_LOGS, AppLog
from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.logging_setup import get_logger

if TYPE_CHECKING:
    from langchain_chroma import Chroma

log = get_logger("ingest.watcher")


class _AppLogHandler(FileSystemEventHandler):
    """Per-app modify handler. Tracks byte offset in-process."""

    def __init__(
        self,
        app_log: AppLog,
        path: Path,
        store: Chroma,
        settings: Settings,
        *,
        initial_offset: int,
    ) -> None:
        self.app_log = app_log
        self.path = path
        self.store = store
        self.settings = settings
        self.offset = initial_offset
        self._lock = Lock()

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # watchdog yields a path string; coerce + compare against our target.
        if Path(event.src_path).resolve() != self.path.resolve():
            return
        with self._lock:
            self._read_and_upsert()

    def _read_and_upsert(self) -> None:
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        except OSError as exc:
            log.warning(
                "watcher_stat_failed",
                app=self.app_log.name,
                error_class=type(exc).__name__,
            )
            return

        if size < self.offset:
            # File truncated or rotated under us — restart from byte 0.
            log.info("watcher_file_truncated_or_rotated", app=self.app_log.name)
            self.offset = 0
        if size == self.offset:
            return

        try:
            with self.path.open("rb") as f:
                f.seek(self.offset)
                chunk = f.read(size - self.offset)
        except OSError as exc:
            log.warning(
                "watcher_read_failed",
                app=self.app_log.name,
                error_class=type(exc).__name__,
            )
            return

        text = chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # If the chunk didn't end on a newline, the last line is partial —
        # drop it and back the offset off by its length so the next tick
        # re-reads it.
        if not text.endswith("\n") and lines:
            partial_byte_len = len(lines[-1].encode("utf-8"))
            self.offset = size - partial_byte_len
            lines = lines[:-1]
        else:
            self.offset = size

        if not lines:
            return

        parsed = parse_and_fold(self.app_log, lines)
        if not parsed:
            return

        # Apply the same ingest gate as backfill — filtered entries never
        # reach the embedder even on the hot path.
        passing = filter_for_ingest(
            parsed,
            levels=self.settings.dashboard_ingest_levels,
            sources=self.settings.dashboard_ingest_sources,
        )
        if not passing:
            return

        try:
            upserted = upsert_entries(
                self.store,
                passing,
                batch_size=self.settings.embedding_batch_size,
                dry_run=self.settings.dashboard_ingest_dry_run,
            )
        except Exception as exc:  # noqa: BLE001 — surface AND swallow; never crash the watcher
            log.warning(
                "watcher_upsert_failed",
                app=self.app_log.name,
                error_class=type(exc).__name__,
            )
            return

        log.info(
            "watcher_appended",
            app=self.app_log.name,
            parsed=len(parsed),
            passed_filter=len(passing),
            embedded=upserted,
            dry_run=self.settings.dashboard_ingest_dry_run,
        )


class LogVolumeWatcher:
    """Owns the watchdog Observer and the per-app handlers. Lifecycle:
    `start()` / `stop()`. Safe to call `stop()` even if `start()` failed.
    """

    def __init__(
        self,
        settings: Settings,
        store: Chroma,
        *,
        initial_offsets: dict[str, int] | None = None,
        observer: BaseObserver | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._observer: BaseObserver = observer if observer is not None else Observer()
        self._handlers: list[_AppLogHandler] = []
        offsets = initial_offsets or {}

        for app_log in APP_LOGS:
            path = app_log.absolute_path(settings.log_volume_root)
            offset = offsets.get(app_log.name)
            if offset is None:
                # Default: start at current EOF so we don't re-process pre-existing
                # content. Caller should pass backfill sizes for safety.
                try:
                    offset = path.stat().st_size
                except (FileNotFoundError, OSError):
                    offset = 0
            handler = _AppLogHandler(app_log, path, store, settings, initial_offset=offset)
            self._handlers.append(handler)
            parent = path.parent
            if not parent.is_dir():
                log.info(
                    "watcher_skip_missing_dir",
                    app=app_log.name,
                    dir=str(parent),
                )
                continue
            self._observer.schedule(handler, str(parent), recursive=False)

    def start(self) -> None:
        self._observer.start()
        log.info(
            "watcher_started",
            apps=[h.app_log.name for h in self._handlers],
        )

    def stop(self, *, timeout: float = 5.0) -> None:
        try:
            self._observer.stop()
            self._observer.join(timeout=timeout)
        except RuntimeError:
            # Already stopped or never started — safe to swallow.
            pass
        log.info("watcher_stopped")
