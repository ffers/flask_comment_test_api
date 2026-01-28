
import logging
import os
from pathlib import Path
import requests
from datetime import datetime
import pytz
from logging.handlers import RotatingFileHandler

class OC_logger:
    _loggers = {}

    class TelegramHandler(logging.Handler):
        def __init__(self, token: str, chat_id: str):
            super().__init__(level=logging.ERROR)
            self.token = token
            self.chat_id = chat_id
            self.url = f"https://api.telegram.org/bot{token}/sendMessage"

        def emit(self, record):
            log_entry = self.format(record)
            try:
                requests.post(self.url, data={
                    "chat_id": self.chat_id,
                    "text": f"🛑 {log_entry}"
                }, timeout=5)
            except Exception:
                pass

    class ColorFormatter(logging.Formatter):
        COLORS = {
            "DEBUG": "\033[90m",
            "INFO": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "CRITICAL": "\033[97;41m"
        }
        RESET = "\033[0m"

        def format(self, record):
            color = self.COLORS.get(record.levelname, "")
            message = super().format(record)
            return f"{color}{message}{self.RESET}"

    class DutchFormatter(logging.Formatter):
        def __init__(self, fmt=None, datefmt=None, timezone='Europe/Amsterdam'):
            super().__init__(fmt, datefmt)
            self.timezone = pytz.timezone(timezone)
            self.months_nl = {
                1: 'januari', 2: 'februari', 3: 'maart', 4: 'april',
                5: 'mei', 6: 'juni', 7: 'juli', 8: 'augustus',
                9: 'september', 10: 'oktober', 11: 'november', 12: 'december'
            }
        
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=self.timezone)
            return f"{dt.day} {self.months_nl[dt.month]} {dt.year} {dt.strftime('%H:%M:%S')}"

    @staticmethod
    def oc_log(name_log: str = "app_asx", timezone: str = "Europe/Amsterdam") -> logging.Logger:
        file_path = "log/logs.log"
        error_path = "log/error.log"

        if name_log in OC_logger._loggers:
            return OC_logger._loggers[name_log]

        Path("log").mkdir(exist_ok=True)

        logger = logging.getLogger(name_log)
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.setLevel(OC_logger._get_level())
        logger.propagate = False

    
        formatter = OC_logger.DutchFormatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            timezone=timezone
        )

        # RotatingFileHandler для logs.log
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=2,          # 2 backup файли
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # RotatingFileHandler для error.log
        error_handler = RotatingFileHandler(
            error_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=2,          # 2 backup файли
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            tg_handler = OC_logger.TelegramHandler(bot_token, chat_id)
            tg_handler.setFormatter(formatter)
            logger.addHandler(tg_handler)

        OC_logger._loggers[name_log] = logger
        return logger

    @staticmethod
    def _get_level() -> int:
        return logging.DEBUG if OC_logger._is_dev() else logging.INFO

    @staticmethod
    def _is_dev() -> bool:
        return os.getenv("ENV", "prod").lower() == "dev"
