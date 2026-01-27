import logging
import sys


def setup_logging():
    # 1. Define the format (Time | Level | Module | Message)
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    # 2. Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 3. Create a Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    # 4. Remove any existing handlers to prevent duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()

    # 5. Add the handler to the root logger
    logger.addHandler(console_handler)

    # 6. Specific overrides (Optional)
    # Set third-party libs to WARNING to keep your console clean
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger
