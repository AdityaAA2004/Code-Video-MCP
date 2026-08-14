"""Logging setup.

One subtlety this module exists to handle: under the stdio transport, anything
written to stdout corrupts the MCP framing. All logging must go to stderr (or a
file), and third-party libraries that default to stdout must be re-pointed.

Job-scoped logs are also written per job workspace so a failed render can be
inspected after the fact without trawling the whole server log.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

LOGGER_NAMESPACE = "code_explain_video_mcp"


def configure_logging(level: LogLevel = "INFO", *, stdio_safe: bool = True) -> None:
    """Install the root handler for the server process.

    ``stdio_safe`` forces every handler onto stderr, which is required whenever
    the server runs over the stdio transport.
    """
    raise NotImplementedError


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (``code_explain_video_mcp.<name>``)."""
    raise NotImplementedError


def job_log_path(workspace: Path) -> Path:
    """Return the per-job log file path inside a job workspace."""
    raise NotImplementedError


def attach_job_log_handler(job_id: str, workspace: Path) -> logging.Handler:
    """Tee records tagged with ``job_id`` into the job's own log file."""
    raise NotImplementedError


def detach_job_log_handler(handler: logging.Handler) -> None:
    """Remove and close a handler installed by :func:`attach_job_log_handler`."""
    raise NotImplementedError
