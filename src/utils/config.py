"""
Configuration management for the trading bot.
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator


class TradingConfig(BaseModel):
    """Trading parameters configuration."""
    initial_bankroll: float = Field(default=100, gt=0)
    max_risk_per_trade: float = Field(default=0.05, gt=0, le=1)
    kelly_fraction: float = Field(default=0.25, gt=0, le=1)
    min_bankroll: float = Field(default=20, gt=0)
    portfolio_stop_loss: float = Field(default=0.20, gt=0, le=1)


class StrategyConfig(BaseModel):
    """Strategy parameters configuration."""
    min_confidence: int = Field(default=70, ge=0, le=100)
    min_edge: float = Field(default=0.05, ge=0)
    min_liquidity: float = Field(default=10000, gt=0)
    min_hours_until_event: int = Field(default=24, ge=0)
    max_hours_until_event: int = Field(default=72, ge=0)
    take_profit: float = Field(default=0.10, gt=0)
    stop_loss: float = Field(default=0.15, gt=0)
    close_before_event_hours: int = Field(default=1, ge=0)
    max_positions: int = Field(default=5, ge=1)


class LLMConfig(BaseModel):
    """LLM configuration."""
    primary_provider: str = "gemini"
    fallback_provider: str = "groq"
    gemini: Dict[str, Any] = Field(default_factory=dict)
    groq: Dict[str, Any] = Field(default_factory=dict)
    prompt: Dict[str, Any] = Field(default_factory=dict)


class ScheduleConfig(BaseModel):
    """Scheduling configuration."""
    scan_markets_interval: int = Field(default=360, gt=0)
    check_positions_interval: int = Field(default=30, gt=0)
    update_dashboard_interval: int = Field(default=5, gt=0)
    run_mode: str = Field(default="continuous")


class Config:
    """Main configuration class."""
    
    def __init__(self, config_path: Optional[str] = None, env_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Path to config.yaml file
            env_path: Path to .env file
        """
        # Load environment variables
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
        
        # Load YAML configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        
        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)
        
        # Parse configurations
        self.trading = TradingConfig(**self._config.get('trading', {}))
        self.strategy = StrategyConfig(**self._config.get('strategy', {}))
        self.llm = LLMConfig(**self._config.get('llm', {}))
        self.schedule = ScheduleConfig(**self._config.get('schedule', {}))
        
        # Raw config sections
        self.markets = self._config.get('markets', {})
        self.data_sources = self._config.get('data_sources', {})
        self.logging = self._config.get('logging', {})
        self.notifications = self._config.get('notifications', {})
        self.paper_trading = self._config.get('paper_trading', {})
        
        # Environment variables
        self.polymarket_api_key = os.getenv('POLYMARKET_API_KEY')
        self.polymarket_api_secret = os.getenv('POLYMARKET_API_SECRET')
        self.polymarket_api_passphrase = os.getenv('POLYMARKET_API_PASSPHRASE')
        self.polymarket_private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
        
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        self.perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.odds_api_key = os.getenv('ODDS_API_KEY')
        
        self.trading_mode = os.getenv('TRADING_MODE', 'paper')
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///data/trades.db')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    def is_paper_trading(self) -> bool:
        """Check if in paper trading mode."""
        return self.trading_mode.lower() == 'paper'
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """
        Validate that required API keys are present.
        
        Returns:
            Dictionary of API key validation status
        """
        validations = {
            'polymarket': all([
                self.polymarket_api_key,
                self.polymarket_api_secret,
                self.polymarket_api_passphrase,
                self.polymarket_private_key
            ]),
            'gemini': bool(self.gemini_api_key),
            'groq': bool(self.groq_api_key),
        }
        return validations
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: Configuration key (dot notation supported)
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default


# Global config instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None, env_path: Optional[str] = None) -> Config:
    """
    Get or create the global configuration instance.
    
    Args:
        config_path: Path to config.yaml file
        env_path: Path to .env file
        
    Returns:
        Configuration instance
    """
    global _config
    if _config is None:
        _config = Config(config_path, env_path)
    return _config
