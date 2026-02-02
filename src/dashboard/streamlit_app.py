"""
Streamlit dashboard for monitoring the trading bot.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import desc

from src.models.database import get_database, Trade, Prediction, Performance
from src.utils.config import get_config


# Page config
st.set_page_config(
    page_title="Polymarket Trading Bot",
    page_icon="📈",
    layout="wide"
)

# Load config and database
@st.cache_resource
def init_resources():
    config = get_config()
    db = get_database(config.database_url)
    return config, db

config, db = init_resources()

# Title
st.title("📈 Polymarket Trading Bot Dashboard")
st.markdown(f"**Mode:** {'🧪 Paper Trading' if config.is_paper_trading() else '💰 Live Trading'}")

# Sidebar
st.sidebar.header("Filters")
time_range = st.sidebar.selectbox(
    "Time Range",
    ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "All Time"]
)

# Calculate time filter
now = datetime.utcnow()
if time_range == "Last 24 Hours":
    time_filter = now - timedelta(days=1)
elif time_range == "Last 7 Days":
    time_filter = now - timedelta(days=7)
elif time_range == "Last 30 Days":
    time_filter = now - timedelta(days=30)
else:
    time_filter = None

# Get database session
session = db.get_session()

# === OVERVIEW METRICS ===
st.header("📊 Overview")

col1, col2, col3, col4 = st.columns(4)

# Get all trades
all_trades = session.query(Trade).all()
closed_trades = [t for t in all_trades if t.status == 'closed']
open_trades = [t for t in all_trades if t.status == 'open']

# Calculate metrics
total_pnl = sum(t.realized_pnl or 0 for t in closed_trades) + sum(t.unrealized_pnl or 0 for t in open_trades)
realized_pnl = sum(t.realized_pnl or 0 for t in closed_trades)
winning_trades = len([t for t in closed_trades if (t.realized_pnl or 0) > 0])
total_closed = len(closed_trades)
win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0

initial_bankroll = config.trading.initial_bankroll
current_bankroll = initial_bankroll + total_pnl

col1.metric("Current Bankroll", f"${current_bankroll:.2f}", f"${total_pnl:+.2f}")
col2.metric("Total P&L", f"${total_pnl:.2f}", f"{(total_pnl/initial_bankroll)*100:+.1f}%")
col3.metric("Win Rate", f"{win_rate:.1f}%", f"{winning_trades}/{total_closed}")
col4.metric("Open Positions", len(open_trades))

# === OPEN POSITIONS ===
st.header("💼 Open Positions")

if open_trades:
    positions_data = []
    for trade in open_trades:
        pnl_pct = (trade.unrealized_pnl / trade.size * 100) if trade.size > 0 and trade.unrealized_pnl else 0
        positions_data.append({
            "ID": trade.id,
            "Market": trade.market_question[:60] + "..." if len(trade.market_question) > 60 else trade.market_question,
            "Side": f"{trade.side.upper()} {trade.outcome.upper()}",
            "Size": f"${trade.size:.2f}",
            "Entry": f"{trade.entry_price:.3f}",
            "Confidence": f"{trade.confidence_score}%",
            "Unrealized P&L": f"${trade.unrealized_pnl or 0:.2f}",
            "P&L %": f"{pnl_pct:+.1f}%",
            "Entry Time": trade.entry_time.strftime("%Y-%m-%d %H:%M")
        })
    
    df_positions = pd.DataFrame(positions_data)
    st.dataframe(df_positions, use_container_width=True, hide_index=True)
else:
    st.info("No open positions")

# === TRADE HISTORY ===
st.header("📜 Trade History")

# Filter trades by time
if time_filter:
    filtered_trades = [t for t in all_trades if t.entry_time >= time_filter]
else:
    filtered_trades = all_trades

if filtered_trades:
    trade_data = []
    for trade in sorted(filtered_trades, key=lambda x: x.entry_time, reverse=True):
        pnl = trade.realized_pnl if trade.status == 'closed' else trade.unrealized_pnl
        pnl_pct = (pnl / trade.size * 100) if trade.size > 0 and pnl else 0
        
        trade_data.append({
            "ID": trade.id,
            "Status": trade.status.upper(),
            "Market": trade.market_question[:50] + "..." if len(trade.market_question) > 50 else trade.market_question,
            "Side": f"{trade.outcome.upper()}",
            "Size": f"${trade.size:.2f}",
            "Entry": f"{trade.entry_price:.3f}",
            "Exit": f"{trade.exit_price:.3f}" if trade.exit_price else "-",
            "P&L": f"${pnl or 0:.2f}",
            "P&L %": f"{pnl_pct:+.1f}%",
            "Entry Time": trade.entry_time.strftime("%Y-%m-%d %H:%M"),
            "Close Reason": trade.close_reason or "-"
        })
    
    df_trades = pd.DataFrame(trade_data)
    st.dataframe(df_trades, use_container_width=True, hide_index=True)
else:
    st.info("No trades in selected time range")

# === PERFORMANCE CHART ===
st.header("📈 Performance")

if closed_trades:
    # Create equity curve
    equity_data = []
    running_pnl = 0
    
    for trade in sorted(closed_trades, key=lambda x: x.exit_time or x.entry_time):
        running_pnl += trade.realized_pnl or 0
        equity_data.append({
            "Date": trade.exit_time or trade.entry_time,
            "Equity": initial_bankroll + running_pnl
        })
    
    df_equity = pd.DataFrame(equity_data)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_equity["Date"],
        y=df_equity["Equity"],
        mode='lines+markers',
        name='Equity',
        line=dict(color='#00ff00', width=2)
    ))
    
    fig.add_hline(y=initial_bankroll, line_dash="dash", line_color="gray", annotation_text="Initial Bankroll")
    
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Date",
        yaxis_title="Bankroll (USDC)",
        hovermode='x unified',
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No closed trades yet")

# === RECENT PREDICTIONS ===
st.header("🤖 Recent Predictions")

predictions = session.query(Prediction).order_by(desc(Prediction.created_at)).limit(10).all()

if predictions:
    pred_data = []
    for pred in predictions:
        pred_data.append({
            "Market": pred.market_question[:60] + "..." if len(pred.market_question) > 60 else pred.market_question,
            "Prediction": pred.predicted_outcome.upper(),
            "Confidence": f"{pred.confidence}%",
            "Expected Prob": f"{pred.expected_probability:.2%}",
            "Market Price": f"{pred.current_yes_price:.3f}",
            "LLM": pred.llm_provider.title(),
            "Time": pred.created_at.strftime("%Y-%m-%d %H:%M")
        })
    
    df_predictions = pd.DataFrame(pred_data)
    st.dataframe(df_predictions, use_container_width=True, hide_index=True)
    
    # Show reasoning for latest prediction
    with st.expander("Latest Prediction Reasoning"):
        st.write(f"**Market:** {predictions[0].market_question}")
        st.write(f"**Prediction:** {predictions[0].predicted_outcome.upper()} ({predictions[0].confidence}% confidence)")
        st.write(f"**Reasoning:**")
        st.write(predictions[0].reasoning)
else:
    st.info("No predictions yet")

# === STRATEGY STATS ===
st.header("⚙️ Strategy Configuration")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Entry Criteria")
    st.write(f"- Min Confidence: {config.strategy.min_confidence}%")
    st.write(f"- Min Edge: {config.strategy.min_edge:.1%}")
    st.write(f"- Min Liquidity: ${config.strategy.min_liquidity:,.0f}")
    st.write(f"- Event Window: {config.strategy.min_hours_until_event}-{config.strategy.max_hours_until_event} hours")

with col2:
    st.subheader("Risk Management")
    st.write(f"- Kelly Fraction: {config.trading.kelly_fraction:.2f}")
    st.write(f"- Max Risk/Trade: {config.trading.max_risk_per_trade:.1%}")
    st.write(f"- Take Profit: {config.strategy.take_profit:.1%}")
    st.write(f"- Stop Loss: {config.strategy.stop_loss:.1%}")
    st.write(f"- Max Positions: {config.strategy.max_positions}")

# Close session
session.close()

# Auto-refresh
st.sidebar.markdown("---")
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
if auto_refresh:
    st.rerun()
