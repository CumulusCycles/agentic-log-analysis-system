import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import structlog


def configure_logging(log_file_path: str = "/app/logs/fnol-app.log") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *pre_chain,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Don't cache the bound logger on the lazy proxy — module-level
        # `log = get_logger(__name__)` calls would otherwise lock in whatever
        # config existed at first use, defeating reconfigure (and breaking
        # structlog.testing.capture_logs in tests).
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    try:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        file_handler = RotatingFileHandler(log_file_path, maxBytes=10_000_000, backupCount=5)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # If the volume isn't mounted (eg. local tests), stdout is sufficient.
        pass

    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str = "fnol") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
