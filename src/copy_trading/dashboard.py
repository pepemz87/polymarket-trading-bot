"""
Streamlit dashboard for the Copy Trading Bot.

Run with:
    streamlit run src/copy_trading/dashboard.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from src.models.database import get_database, Base
from src.utils.config import get_config
from src.copy_trading.models import TrackedWallet, CopiedTrade, WalletPerformance
from src.copy_trading.analytics import CopyTradingAnalytics


# Page config
st.set_page_config(
    page_title="Polymarket Copy Trading",
    page_icon="🔄",
    layout="wide",
)


@st.cache_resource
def init_resources():
    config = get_config()
    db = get_database(config.database_url)
    Base.metadata.create_all(db.engine)
    return config, db


config, db = init_resources()
session = db.get_session()
analytics = CopyTradingAnalytics(session)

# Title
st.title("🔄 Polymarket Copy Trading Dashboard")
st.markdown(
    f"**Mode:** {'🧪 Paper Trading' if config.is_paper_trading() else '💰 Live Trading'}"
)

# Sidebar
st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Overview", "Tracked Wallets", "Trade History", "Performance", "Manage Wallets"],
)

# =====================================================================
# OVERVIEW
# =====================================================================
if page == "Overview":
    st.header("Overview")

    # Top metrics
    all_wallets = session.query(TrackedWallet).all()
    active_wallets = [w for w in all_wallets if w.is_active]

    open_trades = (
        session.query(CopiedTrade).filter(CopiedTrade.status == "executed").all()
    )
    closed_trades = (
        session.query(CopiedTrade).filter(CopiedTrade.status == "closed").all()
    )
    total_pnl = sum(t.realized_pnl or 0 for t in closed_trades)
    total_exposure = sum(t.size or 0 for t in open_trades)
    wins = sum(1 for t in closed_trades if (t.realized_pnl or 0) > 0)
    win_rate = wins / len(closed_trades) * 100 if closed_trades else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Tracked Wallets", f"{len(active_wallets)}/{len(all_wallets)}")
    col2.metric("Open Positions", len(open_trades))
    col3.metric("Total Exposure", f"${total_exposure:.2f}")
    col4.metric("Total P&L", f"${total_pnl:.2f}")
    col5.metric("Win Rate", f"{win_rate:.1f}%")

    # Recent activity feed
    st.subheader("Recent Activity")
    recent = (
        session.query(CopiedTrade)
        .order_by(CopiedTrade.detected_at.desc())
        .limit(20)
        .all()
    )
    if recent:
        data = []
        for t in recent:
            wallet = (
                session.query(TrackedWallet)
                .filter(TrackedWallet.address == t.source_wallet)
                .first()
            )
            wallet_label = wallet.label if wallet and wallet.label else t.source_wallet[:12] + "..."

            data.append({
                "Time": t.detected_at.strftime("%m/%d %H:%M") if t.detected_at else "-",
                "Wallet": wallet_label,
                "Action": f"{t.side.upper()} {t.outcome.upper()}",
                "Size": f"${t.size:.2f}" if t.size else "-",
                "Source Size": f"${t.source_trade_size:.2f}" if t.source_trade_size else "-",
                "Price": f"{t.entry_price:.4f}" if t.entry_price else "-",
                "Slippage": f"{t.slippage:.4f}" if t.slippage else "-",
                "Status": t.status.upper(),
                "Market": (t.market_question or t.market_id or "")[:50],
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.info("No activity yet. Add wallets and start the bot!")

# =====================================================================
# TRACKED WALLETS
# =====================================================================
elif page == "Tracked Wallets":
    st.header("Tracked Wallets")

    wallet_stats = analytics.get_all_wallet_stats()

    if wallet_stats:
        data = []
        for s in wallet_stats:
            data.append({
                "Address": s.address[:14] + "..." + s.address[-6:],
                "Label": s.label or "-",
                "Active": "Yes" if s.is_active else "No",
                "Total P&L": f"${s.total_pnl:.2f}",
                "Win Rate": f"{s.win_rate:.0%}",
                "Trades Copied": s.total_trades_copied,
                "Trades Skipped": s.total_trades_skipped,
                "Volume": f"${s.total_volume:.2f}",
                "Avg Size": f"${s.avg_trade_size:.2f}",
                "P&L 24h": f"${s.pnl_24h:.2f}",
                "P&L 7d": f"${s.pnl_7d:.2f}",
                "Tracking Since": s.tracking_since.strftime("%Y-%m-%d") if s.tracking_since else "-",
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

        # Per-wallet detail
        st.subheader("Wallet Detail")
        wallet_options = {
            f"{s.label or s.address[:12]}... ({s.address[:10]})": s.address
            for s in wallet_stats
        }
        selected_label = st.selectbox("Select wallet", list(wallet_options.keys()))
        if selected_label:
            selected_addr = wallet_options[selected_label]
            trades = analytics.get_recent_trades(
                limit=30, wallet_address=selected_addr
            )
            if trades:
                tdata = []
                for t in trades:
                    tdata.append({
                        "Time": t.detected_at.strftime("%m/%d %H:%M") if t.detected_at else "-",
                        "Side": f"{t.side.upper()} {t.outcome.upper()}",
                        "Size": f"${t.size:.2f}",
                        "Price": f"{t.entry_price:.4f}" if t.entry_price else "-",
                        "P&L": f"${t.realized_pnl:.2f}" if t.realized_pnl else "-",
                        "Status": t.status.upper(),
                        "Skip Reason": t.skip_reason or "-",
                        "Market": (t.market_question or "")[:40],
                    })
                st.dataframe(pd.DataFrame(tdata), use_container_width=True, hide_index=True)
    else:
        st.info("No wallets tracked yet")

# =====================================================================
# TRADE HISTORY
# =====================================================================
elif page == "Trade History":
    st.header("Trade History")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Status", ["All", "Executed", "Closed", "Skipped", "Failed"]
        )
    with col2:
        limit = st.slider("Max trades", 10, 200, 50)
    with col3:
        wallet_filter = st.text_input("Wallet address filter", "")

    status = status_filter.lower() if status_filter != "All" else None
    wallet_addr = wallet_filter.strip() if wallet_filter.strip() else None

    trades = analytics.get_recent_trades(
        limit=limit, wallet_address=wallet_addr, status=status
    )

    if trades:
        data = []
        for t in trades:
            data.append({
                "ID": t.id,
                "Time": t.detected_at.strftime("%Y-%m-%d %H:%M") if t.detected_at else "-",
                "Wallet": t.source_wallet[:12] + "...",
                "Side": f"{t.side.upper()} {t.outcome.upper()}",
                "Our Size": f"${t.size:.2f}",
                "Source Size": f"${t.source_trade_size:.2f}" if t.source_trade_size else "-",
                "Entry": f"{t.entry_price:.4f}" if t.entry_price else "-",
                "Exit": f"{t.exit_price:.4f}" if t.exit_price else "-",
                "Slippage": f"{t.slippage:.4f}" if t.slippage else "-",
                "P&L": f"${t.realized_pnl:.2f}" if t.realized_pnl else "-",
                "Status": t.status.upper(),
                "Skip/Error": t.skip_reason or t.error_message or "-",
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.info("No trades found")

    # Slippage report
    st.subheader("Slippage Analysis")
    slippage = analytics.get_slippage_report(days=7)
    if slippage.get("trades_analyzed", 0) > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Avg Slippage", f"{slippage['avg_slippage']:.4f}")
        c2.metric("Max Slippage", f"{slippage['max_slippage']:.4f}")
        c3.metric("Total Slippage Cost", f"${slippage['total_slippage_cost']:.2f}")
        c4.metric("Trades Analyzed", slippage["trades_analyzed"])
    else:
        st.info("No slippage data yet")

# =====================================================================
# PERFORMANCE
# =====================================================================
elif page == "Performance":
    st.header("Performance")

    days = st.slider("Days to show", 7, 90, 30)
    pnl_history = analytics.get_pnl_history(days=days)

    if pnl_history:
        df = pd.DataFrame(pnl_history)
        df["cumulative_pnl"] = df["total_pnl"].cumsum()

        # Equity curve
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["cumulative_pnl"],
            mode="lines+markers",
            name="Cumulative P&L",
            line=dict(color="#00ff88", width=2),
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(
            title="Cumulative P&L",
            xaxis_title="Date",
            yaxis_title="P&L (USDC)",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Daily P&L bar chart
        fig2 = go.Figure()
        colors = ["#00ff88" if v >= 0 else "#ff4444" for v in df["total_pnl"]]
        fig2.add_trace(go.Bar(
            x=df["date"],
            y=df["total_pnl"],
            marker_color=colors,
            name="Daily P&L",
        ))
        fig2.update_layout(
            title="Daily P&L",
            xaxis_title="Date",
            yaxis_title="P&L (USDC)",
            height=300,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Volume chart
        if "volume" in df.columns:
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=df["date"],
                y=df["volume"],
                marker_color="#4488ff",
                name="Volume",
            ))
            fig3.update_layout(
                title="Daily Volume Copied",
                xaxis_title="Date",
                yaxis_title="Volume (USDC)",
                height=300,
            )
            st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No performance data yet. Run the bot to generate data.")

# =====================================================================
# MANAGE WALLETS
# =====================================================================
elif page == "Manage Wallets":
    st.header("Manage Wallets")

    st.subheader("Add New Wallet")
    with st.form("add_wallet"):
        new_address = st.text_input("Wallet Address (0x...)")
        new_label = st.text_input("Label (optional)")
        new_sizing = st.selectbox(
            "Sizing Mode",
            ["proportional", "fixed", "percentage"],
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            new_fixed = st.number_input("Fixed Size ($)", value=10.0, min_value=1.0)
        with col2:
            new_factor = st.number_input("Proportional Factor", value=1.0, min_value=0.01, max_value=10.0)
        with col3:
            new_pct = st.number_input("% of Bankroll", value=5.0, min_value=0.1, max_value=50.0)
        new_delay = st.slider("Copy Delay (seconds)", 0, 60, 5)

        submitted = st.form_submit_button("Add Wallet")
        if submitted and new_address:
            try:
                addr = new_address.lower().strip()
                existing = session.query(TrackedWallet).filter(TrackedWallet.address == addr).first()
                if existing:
                    existing.is_active = True
                    existing.label = new_label or existing.label
                    existing.sizing_mode = new_sizing
                    existing.fixed_size = new_fixed
                    existing.proportional_factor = new_factor
                    existing.percentage_of_bankroll = new_pct / 100
                    existing.copy_delay_seconds = new_delay
                    session.commit()
                    st.success(f"Wallet {addr[:12]}... reactivated!")
                else:
                    wallet = TrackedWallet(
                        address=addr,
                        label=new_label or None,
                        sizing_mode=new_sizing,
                        fixed_size=new_fixed,
                        proportional_factor=new_factor,
                        percentage_of_bankroll=new_pct / 100,
                        copy_delay_seconds=new_delay,
                    )
                    session.add(wallet)
                    session.commit()
                    st.success(f"Wallet {addr[:12]}... added!")
            except Exception as e:
                st.error(f"Error: {e}")

    # List current wallets with management options
    st.subheader("Current Wallets")
    wallets = session.query(TrackedWallet).all()
    if wallets:
        for w in wallets:
            with st.expander(
                f"{'🟢' if w.is_active else '🔴'} {w.label or w.address[:14] + '...'} "
                f"({w.sizing_mode}, P&L: ${w.total_pnl:.2f})"
            ):
                st.write(f"**Address:** `{w.address}`")
                st.write(f"**Sizing:** {w.sizing_mode} (fixed=${w.fixed_size}, factor={w.proportional_factor}x, pct={w.percentage_of_bankroll:.0%})")
                st.write(f"**Delay:** {w.copy_delay_seconds}s")
                st.write(f"**Trades Copied:** {w.total_trades_copied}")
                st.write(f"**Added:** {w.added_at}")

                col1, col2 = st.columns(2)
                with col1:
                    if w.is_active:
                        if st.button(f"Deactivate", key=f"deact_{w.id}"):
                            w.is_active = False
                            session.commit()
                            st.rerun()
                    else:
                        if st.button(f"Activate", key=f"act_{w.id}"):
                            w.is_active = True
                            session.commit()
                            st.rerun()
    else:
        st.info("No wallets added yet")


# Footer
session.close()
st.sidebar.markdown("---")
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
if auto_refresh:
    import time as _time
    _time.sleep(30)
    st.rerun()
