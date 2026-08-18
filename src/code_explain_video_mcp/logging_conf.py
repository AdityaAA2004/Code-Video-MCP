"""Logging setup.

The subtlety this module exists for: under the stdio transport, anything written
to stdout corrupts the MCP framing, so every handler must go to stderr.

Job-scoped logs are also tee'd into each job workspace, so a failed render can be
inspected afterwards without trawling the whole server log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

LOGGER_NAMESPACE = "code_explain_video_mcp"

_FORMATTER = logging.Formatter(
    "%(asctime)s %(levelname)-7s [%(name)s] %(message)s", datefmt="%H:%M:%S"
)

# Third-party chatter that would otherwise drown the pipeline trace.
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "anthropic", "asyncio", "mcp")


def configure_logging(level: LogLevel = "INFO", *, stdio_safe: bool = True) -> None:
    """Install the process-wide log handler, replacing any previous one.

    ``stdio_safe`` forces output onto stderr, which is required under the stdio
    transport. It is the default because getting it wrong produces a confusing
    failure: the host sees malformed JSON-RPC instead of a log line.
    """
    handler = logging.StreamHandler(sys.stderr if stdio_safe else sys.stdout)
    handler.setFormatter(_FORMATTER)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    quiet = max(logging.WARNING, logging.getLevelNamesMapping()[level])
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(quiet)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (``code_explain_video_mcp.<name>``)."""
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def attach_job_log_handler(job_id: str, workspace: Path) -> logging.Handler:
    """Tee records tagged with ``job_id`` into that job's own log file.

    The runner stamps ``job_id`` onto every record it emits, which is what lets
    one job's file ignore the other jobs running concurrently. The handler goes
    on the package logger, not the root one, so library noise stays out.
    """
    workspace.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(workspace / "job.log", encoding="utf-8")
    handler.setFormatter(_FORMATTER)
    handler.addFilter(lambda record: getattr(record, "job_id", None) == job_id)
    logging.getLogger(LOGGER_NAMESPACE).addHandler(handler)
    return handler


def detach_job_log_handler(handler: logging.Handler) -> None:
    """Remove and close a handler installed by :func:`attach_job_log_handler`."""
    logging.getLogger(LOGGER_NAMESPACE).removeHandler(handler)
    handler.close()
