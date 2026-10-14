"""Structured logging setup.

Configures Python's standard logging with JSON-like structured output
for production and human-readable output for development.
"""

import logging
import sys


def setup_logging(log_level: str = "info") -> None:
    """Configure root logger with the given level.

    Args:
        log_level: One of debug, info, warning, error, critical.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls
    root.handlers.clear()
    root.addHandler(handler)
