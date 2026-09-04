# engine/utils/logger.py
import datetime

class LogLevel:
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4 # Only fatal errors

class Logger:
    _instance = None
    _level = LogLevel.DEBUG  # Default level

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_level(cls, level: int):
        """Sets the minimum logging level."""
        cls._level = level

    @classmethod
    def _log(cls, level: int, source: str, message: str):
        if level >= cls._level:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            level_name = {
                LogLevel.DEBUG: "DEBUG",
                LogLevel.INFO: "INFO",
                LogLevel.WARNING: "WARN",
                LogLevel.ERROR: "ERROR",
                LogLevel.CRITICAL: "CRIT"
            }.get(level, "LOG")
            
            # Format: [TIME] [LEVEL] [Source] Message
            print(f"[{timestamp}] [{level_name:<5}] [{source}] {message}")

    @classmethod
    def debug(cls, source: str, message: str):
        cls._log(LogLevel.DEBUG, source, message)

    @classmethod
    def info(cls, source: str, message: str):
        cls._log(LogLevel.INFO, source, message)

    @classmethod
    def warning(cls, source: str, message: str):
        cls._log(LogLevel.WARNING, source, message)

    @classmethod
    def error(cls, source: str, message: str):
        cls._log(LogLevel.ERROR, source, message)

    @classmethod
    def critical(cls, source: str, message: str):
        cls._log(LogLevel.CRITICAL, source, message)

    @classmethod
    def separator(cls, level: int = LogLevel.DEBUG):
        """Prints a separator line if the level is active."""
        if level >= cls._level:
            print("-" * 60)