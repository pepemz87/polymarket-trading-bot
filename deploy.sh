#!/bin/bash
# =============================================================
# Polymarket Copy Trading Bot - Deployment Script
# =============================================================
# Usage:
#   1. Clone the repo on your server
#   2. Run: chmod +x deploy.sh && ./deploy.sh
#   3. Edit .env with your API keys
#   4. Run: ./deploy.sh start
# =============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="polymarket-copy-trading"
LOG_DIR="$PROJECT_DIR/logs"
DATA_DIR="$PROJECT_DIR/data"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ----- SETUP -----
setup() {
    info "Setting up Polymarket Copy Trading Bot..."

    # Create directories
    mkdir -p "$LOG_DIR" "$DATA_DIR"

    # Create virtual environment
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating Python virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    # Activate and install dependencies
    source "$VENV_DIR/bin/activate"
    info "Installing dependencies..."
    pip install --upgrade pip
    pip install -r "$PROJECT_DIR/requirements.txt"

    # Create .env if it doesn't exist
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        warn ".env created from template - EDIT IT WITH YOUR API KEYS!"
        warn "Run: nano $PROJECT_DIR/.env"
    fi

    info "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Edit your API keys:  nano $PROJECT_DIR/.env"
    echo "  2. Add wallets:         ./deploy.sh add-wallet 0xABC... MyTrader"
    echo "  3. Start the bot:       ./deploy.sh start"
    echo "  4. View logs:           ./deploy.sh logs"
}

# ----- START -----
start() {
    source "$VENV_DIR/bin/activate"

    # Check .env exists
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        error ".env file not found! Run: ./deploy.sh setup"
        exit 1
    fi

    info "Starting copy trading bot..."

    # Run with nohup so it survives terminal close
    cd "$PROJECT_DIR"
    nohup python -u run_copy_trading.py \
        >> "$LOG_DIR/copy_trading.log" 2>&1 &

    echo $! > "$DATA_DIR/bot.pid"
    info "Bot started (PID: $(cat $DATA_DIR/bot.pid))"
    info "Logs: tail -f $LOG_DIR/copy_trading.log"
}

# ----- STOP -----
stop() {
    if [ -f "$DATA_DIR/bot.pid" ]; then
        PID=$(cat "$DATA_DIR/bot.pid")
        if kill -0 "$PID" 2>/dev/null; then
            info "Stopping bot (PID: $PID)..."
            kill "$PID"
            rm "$DATA_DIR/bot.pid"
            info "Bot stopped"
        else
            warn "Bot not running (stale PID file)"
            rm "$DATA_DIR/bot.pid"
        fi
    else
        warn "No PID file found. Bot may not be running."
        # Try to find and kill anyway
        pkill -f "run_copy_trading.py" 2>/dev/null && info "Bot stopped" || warn "No process found"
    fi
}

# ----- RESTART -----
restart() {
    stop
    sleep 2
    start
}

# ----- STATUS -----
status() {
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"

    if [ -f "$DATA_DIR/bot.pid" ]; then
        PID=$(cat "$DATA_DIR/bot.pid")
        if kill -0 "$PID" 2>/dev/null; then
            info "Bot is RUNNING (PID: $PID)"
        else
            warn "Bot is NOT RUNNING (stale PID)"
        fi
    else
        warn "Bot is NOT RUNNING"
    fi

    python run_copy_trading.py --status
}

# ----- LOGS -----
logs() {
    tail -f "$LOG_DIR/copy_trading.log"
}

# ----- ADD WALLET -----
add_wallet() {
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"

    ADDRESS="$1"
    LABEL="${2:-}"

    if [ -z "$ADDRESS" ]; then
        error "Usage: ./deploy.sh add-wallet 0xADDRESS [label]"
        exit 1
    fi

    CMD="python run_copy_trading.py --add-wallet $ADDRESS"
    [ -n "$LABEL" ] && CMD="$CMD --label $LABEL"

    $CMD
}

# ----- LIST WALLETS -----
list_wallets() {
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"
    python run_copy_trading.py --list-wallets
}

# ----- DISCOVER -----
discover() {
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"
    python run_copy_trading.py --discover
}

# ----- DASHBOARD -----
dashboard() {
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"
    info "Starting dashboard on http://localhost:8501"
    streamlit run src/copy_trading/dashboard.py --server.port 8501
}

# ----- TEST CONNECTION -----
test_connection() {
    info "Testing API connectivity..."
    source "$VENV_DIR/bin/activate"
    python -c "
import requests
import sys

apis = {
    'Gamma API': 'https://gamma-api.polymarket.com/markets?limit=1',
    'CLOB API': 'https://clob.polymarket.com/time',
}

all_ok = True
for name, url in apis.items():
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            print(f'  [OK] {name} ({url})')
        else:
            print(f'  [FAIL] {name}: HTTP {r.status_code}')
            all_ok = False
    except Exception as e:
        print(f'  [FAIL] {name}: {e}')
        all_ok = False

if all_ok:
    print('\nAll APIs reachable!')
else:
    print('\nSome APIs failed. Check your network/firewall.')
    sys.exit(1)
"
}

# ----- SYSTEMD SERVICE -----
install_service() {
    info "Installing systemd service..."
    sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null <<SERVICEFILE
[Unit]
Description=Polymarket Copy Trading Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_DIR/bin/python -u run_copy_trading.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/copy_trading.log
StandardError=append:$LOG_DIR/copy_trading_error.log

[Install]
WantedBy=multi-user.target
SERVICEFILE

    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    info "Service installed! Use:"
    echo "  sudo systemctl start $SERVICE_NAME"
    echo "  sudo systemctl stop $SERVICE_NAME"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo "  journalctl -u $SERVICE_NAME -f"
}

# ----- MAIN -----
case "${1:-setup}" in
    setup)          setup ;;
    start)          start ;;
    stop)           stop ;;
    restart)        restart ;;
    status)         status ;;
    logs)           logs ;;
    add-wallet)     add_wallet "$2" "$3" ;;
    list-wallets)   list_wallets ;;
    discover)       discover ;;
    dashboard)      dashboard ;;
    test)           test_connection ;;
    install-service) install_service ;;
    *)
        echo "Usage: ./deploy.sh {setup|start|stop|restart|status|logs|add-wallet|list-wallets|discover|dashboard|test|install-service}"
        exit 1
        ;;
esac
