# Polymarket Trading Bot 🤖

An autonomous trading bot for Polymarket that uses LLMs (Gemini/Groq) to analyze sports betting markets and execute trades using the Kelly Criterion for optimal position sizing.

## ✨ Features

- 🧪 **Paper Trading Mode** - Test strategies risk-free with realistic simulation
- 🤖 **LLM-Powered Analysis** - Uses Gemini 1.5 Flash or Groq for market predictions
- 📊 **Multi-Source Data** - Aggregates news, statistics, and odds for informed decisions
- 💰 **Kelly Criterion** - Optimal position sizing based on edge and confidence
- 🛡️ **Risk Management** - Automated stop-loss, take-profit, and position limits
- 📈 **Real-Time Dashboard** - Streamlit dashboard for monitoring performance
- ⚡ **Fully Autonomous** - Scheduled market scanning and position management

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
cd polymarket-trading-bot

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add:
- **Gemini API Key** (free): Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Groq API Key** (free): Get from [Groq Console](https://console.groq.com/keys)
- **Polymarket API Keys**: From your Polymarket account

### 3. Run the Bot

**Paper Trading Mode (Recommended First):**
```bash
python main.py
```

**View Dashboard:**
```bash
python run_dashboard.py
```

## 📋 Configuration

Edit `config/config.yaml` to customize:

### Trading Parameters
- `initial_bankroll`: Starting capital (default: 100 USDC)
- `kelly_fraction`: Fraction of Kelly to use (default: 0.25 for conservative)
- `max_risk_per_trade`: Maximum % of bankroll per trade (default: 5%)

### Strategy Parameters
- `min_confidence`: Minimum LLM confidence to trade (default: 70%)
- `min_edge`: Minimum expected edge (default: 5%)
- `take_profit`: Take profit threshold (default: 10%)
- `stop_loss`: Stop loss threshold (default: 15%)

### Scheduling
- `scan_markets_interval`: How often to scan markets (default: 360 minutes)
- `check_positions_interval`: How often to check positions (default: 30 minutes)

## 📊 Dashboard

The Streamlit dashboard provides:
- **Overview**: Current bankroll, P&L, win rate
- **Open Positions**: Real-time position tracking
- **Trade History**: All executed trades with P&L
- **Performance Chart**: Equity curve over time
- **Recent Predictions**: LLM analysis and reasoning
- **Strategy Stats**: Current configuration

Access at: `http://localhost:8501`

## 🔧 Project Structure

```
polymarket-trading-bot/
├── src/
│   ├── core/              # Core trading components
│   │   ├── kelly_criterion.py
│   │   ├── bankroll_manager.py
│   │   ├── paper_trading.py
│   │   └── polymarket_client.py
│   ├── analysis/          # Market analysis
│   │   ├── llm_analyzer.py
│   │   ├── data_collector.py
│   │   ├── market_scanner.py
│   │   └── prediction_engine.py
│   ├── strategies/        # Trading strategies
│   │   └── conservative_strategy.py
│   ├── models/            # Database models
│   │   ├── database.py
│   │   └── schemas.py
│   ├── utils/             # Utilities
│   │   ├── config.py
│   │   └── logger.py
│   └── dashboard/         # Streamlit dashboard
│       └── streamlit_app.py
├── config/
│   └── config.yaml        # Main configuration
├── data/                  # SQLite database
├── logs/                  # Log files
├── main.py               # Main bot entry point
├── run_dashboard.py      # Dashboard launcher
└── requirements.txt      # Python dependencies
```

## 🎯 How It Works

1. **Market Scanning**: Bot scans Polymarket for sports markets matching criteria
2. **Data Collection**: Aggregates news, statistics, and odds for each market
3. **LLM Analysis**: Sends data to Gemini/Groq for prediction and confidence score
4. **Edge Calculation**: Compares LLM probability vs market price to find edge
5. **Position Sizing**: Uses Kelly Criterion to calculate optimal bet size
6. **Entry Validation**: Checks confidence, edge, liquidity, and risk limits
7. **Trade Execution**: Places order (paper or live)
8. **Position Management**: Monitors positions for take-profit, stop-loss, or event close
9. **Logging & Tracking**: Records all trades and predictions in database

## 🔐 Security

- Never commit `.env` file (already in `.gitignore`)
- Store API keys securely
- Start with paper trading to validate strategy
- Use small amounts when switching to live trading

## 📈 Performance Tracking

All trades are logged to SQLite database (`data/trades.db`) with:
- Entry/exit prices and times
- P&L (realized and unrealized)
- LLM confidence and reasoning
- Market metadata

## ⚠️ Disclaimer

This bot is for educational purposes. Trading involves risk. Always:
- Start with paper trading
- Test thoroughly before using real money
- Only risk what you can afford to lose
- Understand the Kelly Criterion and risk management
- Monitor the bot regularly

## 📚 Resources

- [Polymarket API Docs](https://docs.polymarket.com/)
- [Kelly Criterion Explained](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Gemini API](https://ai.google.dev/)
- [Groq API](https://console.groq.com/)

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Additional data sources (player stats, weather, etc.)
- More sophisticated prediction models
- Backtesting framework
- Additional trading strategies
- Enhanced risk management

## 📝 License

MIT License - See LICENSE file for details

---

**Happy Trading! 🚀**
