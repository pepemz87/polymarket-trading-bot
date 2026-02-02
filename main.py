"""
Main trading bot orchestrator.
"""
import time
import schedule
from datetime import datetime
from typing import Optional
from loguru import logger

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.models.database import get_database
from src.core.polymarket_client import PolymarketClient
from src.core.paper_trading import PaperTradingSimulator
from src.core.bankroll_manager import BankrollManager
from src.analysis.llm_analyzer import LLMAnalyzer
from src.analysis.data_collector import DataCollector
from src.analysis.market_scanner import MarketScanner
from src.analysis.prediction_engine import PredictionEngine
from src.strategies.conservative_strategy import ConservativeStrategy


class TradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self, config_path: Optional[str] = None, env_path: Optional[str] = None):
        """
        Initialize trading bot.
        
        Args:
            config_path: Path to config.yaml
            env_path: Path to .env file
        """
        # Load configuration
        self.config = get_config(config_path, env_path)
        
        # Setup logging
        self.logger = setup_logger(self.config.log_level)
        
        logger.info("=" * 60)
        logger.info("POLYMARKET TRADING BOT STARTING")
        logger.info("=" * 60)
        
        # Validate API keys
        validations = self.config.validate_api_keys()
        logger.info(f"API Key Validation: {validations}")
        
        if not validations['gemini'] and not validations['groq']:
            logger.error("No LLM API keys configured!")
            raise ValueError("At least one LLM API key (Gemini or Groq) is required")
        
        # Initialize database
        self.db = get_database(self.config.database_url)
        self.db_session = self.db.get_session()
        
        # Initialize Polymarket client
        if self.config.is_paper_trading():
            logger.info("Running in PAPER TRADING mode")
            self.trading_client = PaperTradingSimulator(
                db_session=self.db_session,
                slippage=self.config.paper_trading.get('slippage', 0.002),
                fill_delay=self.config.paper_trading.get('fill_delay', 2.0)
            )
        else:
            logger.warning("Running in LIVE TRADING mode")
            self.polymarket_client = PolymarketClient(
                api_key=self.config.polymarket_api_key,
                api_secret=self.config.polymarket_api_secret,
                api_passphrase=self.config.polymarket_api_passphrase,
                private_key=self.config.polymarket_private_key
            )
            self.trading_client = self.polymarket_client
        
        # Initialize bankroll manager
        initial_bankroll = self.config.get('trading.initial_bankroll', 100)
        self.bankroll_manager = BankrollManager(
            db_session=self.db_session,
            initial_bankroll=initial_bankroll,
            max_positions=self.config.strategy.max_positions,
            portfolio_stop_loss=self.config.trading.portfolio_stop_loss
        )
        
        # Initialize LLM analyzer
        self.llm_analyzer = LLMAnalyzer(
            gemini_api_key=self.config.gemini_api_key,
            groq_api_key=self.config.groq_api_key,
            primary_provider=self.config.llm.primary_provider,
            gemini_model=self.config.llm.gemini.get('model', 'gemini-1.5-flash'),
            groq_model=self.config.llm.groq.get('model', 'llama-3.1-70b-versatile'),
            temperature=self.config.llm.gemini.get('temperature', 0.3)
        )
        
        # Initialize data collector
        self.data_collector = DataCollector(
            news_api_key=self.config.news_api_key,
            odds_api_key=self.config.odds_api_key
        )
        
        # Initialize prediction engine
        self.prediction_engine = PredictionEngine(
            llm_analyzer=self.llm_analyzer,
            data_collector=self.data_collector,
            db_session=self.db_session
        )
        
        # Initialize market scanner
        if not self.config.is_paper_trading():
            self.market_scanner = MarketScanner(
                polymarket_client=self.polymarket_client,
                min_liquidity=self.config.strategy.min_liquidity,
                min_volume_24h=self.config.markets.get('min_24h_volume', 5000),
                sports_filter=self.config.markets.get('sports', [])
            )
        else:
            # In paper trading, we'll use mock data
            self.market_scanner = None
        
        # Initialize strategy
        self.strategy = ConservativeStrategy(
            bankroll_manager=self.bankroll_manager,
            prediction_engine=self.prediction_engine,
            min_confidence=self.config.strategy.min_confidence,
            min_edge=self.config.strategy.min_edge,
            min_liquidity=self.config.strategy.min_liquidity,
            take_profit=self.config.strategy.take_profit,
            stop_loss=self.config.strategy.stop_loss,
            close_before_event_hours=self.config.strategy.close_before_event_hours
        )
        
        # Bot state
        self.is_running = False
        self.last_scan_time = None
        self.last_position_check = None
        
        logger.info("Trading bot initialized successfully")
    
    def scan_and_trade(self):
        """Scan markets and execute trades."""
        logger.info("Starting market scan...")
        
        try:
            # Check bankroll status
            status = self.bankroll_manager.get_status()
            logger.info(f"Bankroll: ${status.total_bankroll:.2f} (available: ${status.available_capital:.2f})")
            
            if not status.is_trading_allowed:
                logger.warning(f"Trading not allowed: stop_loss={status.stop_loss_triggered}, positions={status.open_positions}/{self.config.strategy.max_positions}")
                return
            
            # Scan markets
            if self.market_scanner:
                markets = self.market_scanner.scan_markets(
                    min_hours_until_event=self.config.strategy.min_hours_until_event,
                    max_hours_until_event=self.config.strategy.max_hours_until_event,
                    max_markets=10
                )
            else:
                # Paper trading mode: use mock market
                logger.info("Paper trading mode: using mock market data")
                markets = []
            
            logger.info(f"Found {len(markets)} potential markets")
            
            # Analyze each market
            for market in markets:
                self._analyze_and_trade(market)
            
            self.last_scan_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error in scan_and_trade: {e}", exc_info=True)
    
    def _analyze_and_trade(self, market: dict):
        """Analyze a market and potentially trade."""
        try:
            # Generate prediction
            prediction = self.prediction_engine.generate_prediction(
                market_id=market['market_id'],
                market_question=market['question'],
                yes_price=market['yes_price'],
                no_price=market['no_price'],
                sport=market.get('sport'),
                liquidity=market.get('liquidity'),
                volume_24h=market.get('volume_24h')
            )
            
            if not prediction:
                logger.warning(f"No prediction generated for {market['question']}")
                return
            
            # Generate trade signal
            bankroll = self.bankroll_manager.get_current_bankroll()
            signal = self.prediction_engine.generate_trade_signal(
                prediction=prediction,
                bankroll=bankroll,
                kelly_fraction=self.config.trading.kelly_fraction,
                max_bet_fraction=self.config.trading.max_risk_per_trade
            )
            
            if not signal or signal.action != "buy":
                logger.info(f"No trade signal for {market['question']}")
                return
            
            # Evaluate entry
            should_enter, reason = self.strategy.evaluate_entry(
                signal=signal,
                liquidity=market.get('liquidity', 0),
                volume_24h=market.get('volume_24h', 0)
            )
            
            if not should_enter:
                logger.info(f"Entry rejected: {reason}")
                return
            
            # Create and execute order
            order = self.strategy.create_order(
                signal=signal,
                market_question=market['question'],
                is_paper_trade=self.config.is_paper_trading()
            )
            
            trade_id = self.trading_client.place_order(
                order=order,
                market_question=market['question'],
                sport=market.get('sport'),
                event_time=market.get('event_time'),
                confidence=prediction.confidence,
                expected_edge=signal.expected_edge
            )
            
            if trade_id:
                logger.info(f"✅ Trade executed! ID={trade_id}, Market={market['question']}")
            else:
                logger.error("Failed to execute trade")
                
        except Exception as e:
            logger.error(f"Error analyzing market: {e}", exc_info=True)
    
    def check_positions(self):
        """Check and manage open positions."""
        logger.info("Checking open positions...")
        
        try:
            # Get current price function
            def get_price(market_id, outcome):
                if hasattr(self.trading_client, 'get_current_price'):
                    return self.trading_client.get_current_price(market_id, outcome)
                return None
            
            # Manage positions
            actions = self.strategy.manage_positions(get_price)
            
            if actions:
                logger.info(f"Position management actions: {len(actions)}")
                for action in actions:
                    logger.info(f"  {action}")
            
            self.last_position_check = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error checking positions: {e}", exc_info=True)
    
    def run_once(self):
        """Run bot once (scan and check positions)."""
        logger.info("Running bot (one-shot mode)...")
        self.scan_and_trade()
        self.check_positions()
        logger.info("One-shot run completed")
    
    def run_continuous(self):
        """Run bot continuously with scheduled tasks."""
        logger.info("Starting bot in continuous mode...")
        
        # Schedule tasks
        schedule.every(self.config.schedule.scan_markets_interval).minutes.do(self.scan_and_trade)
        schedule.every(self.config.schedule.check_positions_interval).minutes.do(self.check_positions)
        
        # Run initial scan
        self.scan_and_trade()
        
        self.is_running = True
        
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.stop()
    
    def stop(self):
        """Stop the bot."""
        logger.info("Stopping bot...")
        self.is_running = False
        self.db_session.close()
        logger.info("Bot stopped")


def main():
    """Main entry point."""
    try:
        bot = TradingBot()
        
        # Check run mode
        if bot.config.schedule.run_mode == "continuous":
            bot.run_continuous()
        else:
            bot.run_once()
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
