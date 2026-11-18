"""Console and file logging."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def configure_logging(config):
    logger = logging.getLogger("VKLivePointsMiner")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setLevel(config.get("console_level", "INFO"))
    handlers = [console]
    if config.get("save_to_file", True):
        Path("logs").mkdir(exist_ok=True)
        file = TimedRotatingFileHandler(
            "logs/miner.log", when="midnight", backupCount=config.get("rotation_days", 7),
            encoding="utf-8",
        )
        file.setLevel(config.get("file_level", "DEBUG"))
        handlers.append(file)
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
