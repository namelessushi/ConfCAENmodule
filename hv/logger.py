# hv/logger.py
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logger(
    name="HV",
    log_dir="logs",
    level=logging.INFO
):
    # Crear carpeta logs si no existe
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Evitar handlers duplicados
    if logger.handlers:
        return logger

    # Handler: archivo rotativo diario
    file_handler = TimedRotatingFileHandler(
        filename=log_path / "hv.log",
        when="midnight",
        interval=1,
        backupCount=30,   # guarda 30 días
        encoding="utf-8"
    )

    file_handler.suffix = "%Y-%m-%d"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    file_handler.setFormatter(formatter)

    # Handler consola (útil por SSH)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


