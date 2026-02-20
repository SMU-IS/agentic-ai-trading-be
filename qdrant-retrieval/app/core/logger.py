import logging
import sys


def setup_logging(name: str = "app", level: int = logging.INFO) -> logging.Logger:
    """
    Centralised logging configuration utility
    """

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level, format=log_format, handlers=[logging.StreamHandler(sys.stdout)]
    )

    return logging.getLogger(name)


logger = setup_logging()
