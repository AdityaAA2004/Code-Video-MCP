"""Logging setup.

One subtlety this module exists to handle: under the stdio transport, anything
written to stdout corrupts the MCP framing. All logging must go to stderr (or a
file), and third-party libraries that default to stdout must be re-pointed.

Job-scoped logs are also written per job workspace so a failed render can be
inspected after the fact without trawling the whole server log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

LOGGER_NAMESPACE = "code_explain_video_mcp"

JOB_LOG_FILENAME = "job.log"

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


class _JobFilter(logging.Filter):
    """Pass only records tagged with a matching ``job_id`` attribute.

    The runner stamps ``job_id`` onto every record it emits (via a
    :class:`logging.LoggerAdapter`), which is what lets one job's file handler
    ignore the other jobs running concurrently.
    """

    def __init__(self, job_id: str) -> None:
        super().__init__()
        self.job_id = job_id

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "job_id", None) == self.job_id


def configure_logging(level: LogLevel = "INFO", *, stdio_safe: bool = True) -> None:
    """Install the root handler for the server process.

    ``stdio_safe`` forces every handler onto stderr, which is required whenever
    the server runs over the stdio transport. It is the default because getting
    it wrong produces a confusing failure: the host sees malformed JSON-RPC
    rather than a log line.

    Idempotent — calling it twice does not stack duplicate handlers.
    """
    global _configured

    stream = sys.stderr if stdio_safe else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    if _configured:
        for existing in list(root.handlers):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level))

    # Third-party chatter that would otherwise drown the pipeline trace.
    for noisy in ("httpx", "httpcore", "urllib3", "anthropic", "asyncio", "mcp"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, getattr(logging, level)))

    logging.getLogger(LOGGER_NAMESPACE).setLevel(getattr(logging, level))
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (``code_explain_video_mcp.<name>``)."""
    if name.startswith(LOGGER_NAMESPACE):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def job_log_path(workspace: Path) -> Path:
    """Return the per-job log file path inside a job workspace."""
    return Path(workspace) / JOB_LOG_FILENAME


def attach_job_log_handler(job_id: str, workspace: Path) -> logging.Handler:
    """Tee records tagged with ``job_id`` into the job's own log file.

    The handler is attached to the package logger rather than the root logger so
    that library noise never lands in a job log.
    """
    path = job_log_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_JobFilter(job_id))
    logging.getLogger(LOGGER_NAMESPACE).addHandler(handler)
    return handler


def detach_job_log_handler(handler: logging.Handler) -> None:
    """Remove and close a handler installed by :func:`attach_job_log_handler`."""
    logging.getLogger(LOGGER_NAMESPACE).removeHandler(handler)
    handler.close()
