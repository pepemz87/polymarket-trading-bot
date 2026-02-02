"""
Centralized logging configuration using Loguru.
"""
import sys
from pathlib import Path
from loguru import logger
from typing import Optional


class BotLogger:
    """Centralized logger for the trading bot."""
    
    def __init__(self, log_level: str = "INFO"):
        """
        Initialize the logger.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.log_level = log_level
        self._setup_logger()
    
    def _setup_logger(self):
        """Configure loguru logger with multiple handlers."""
        # Remove default handler
        logger.remove()
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Console handler with colors
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            level=self.log_level,
            colorize=True
        )
        
        # General log file
        logger.add(
            log_dir / "bot.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=self.log_level,
            rotation="10 MB",
            retention="30 days",
            compression="zip"
        )
        
        # Trade-specific log file
        logger.add(
            log_dir / "trades.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="INFO",
            rotation="10 MB",
            retention="90 days",
            compression="zip",
            filter=lambda record: "TRADE" in record["extra"]
        )
        
        # Error log file
        logger.add(
            log_dir / "errors.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
            level="ERROR",
            rotation="10 MB",
            retention="90 days",
            compression="zip"
        )
    
    @staticmethod
    def get_logger():
        """Get the configured logger instance."""
        return logger
    
    @staticmethod
    def log_trade(message: str, **kwargs):
        """
        Log a trade-specific message.
        
        Args:
            message: Log message
            **kwargs: Additional context
        """
        logger.bind(TRADE=True).info(message, **kwargs)
    
    @staticmethod
    def log_error(message: str, exception: Optional[Exception] = None):
        """
        Log an error message.
        
        Args:
            message: Error message
            exception: Optional exception object
        """
        if exception:
            logger.exception(f"{message}: {exception}")
        else:
            logger.error(message)


# Global logger instance
def setup_logger(log_level: str = "INFO") -> logger:
    """
    Setup and return the global logger.
    
    Args:
        log_level: Logging level
        
    Returns:
        Configured logger instance
    """
    bot_logger = BotLogger(log_level)
    return bot_logger.get_logger()
