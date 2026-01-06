import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from consumer.config import ConsumerConfig


def setup_logger() -> logging.Logger:
    """Setup logger for consumer process.

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("consumer")
    logger.setLevel(getattr(logging, ConsumerConfig.LOG_LEVEL))

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create logs directory if not exists
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "consumer.log"

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    # File handler with daily rotation
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - [%(levelname)s] - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
