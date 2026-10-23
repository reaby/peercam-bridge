import logging
import sys

LOGGER_NAME = "obswebrtc"


def setup_logging(level=logging.INFO):
    """Route package logs to stdout, which OBS shows in the script log."""
    logger = logging.getLogger(LOGGER_NAME)
    # Replace handlers so script reloads don't stack duplicates.
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def get_logger(suffix=None):
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)
