# Deploying to PythonAnywhere

This guide will help you deploy your Polymarket trading bot to PythonAnywhere, a budget-friendly Python hosting platform.

## Prerequisites

- PythonAnywhere account (free tier available at [pythonanywhere.com](https://www.pythonanywhere.com))
- Your bot code ready
- API keys configured

## Step 1: Create PythonAnywhere Account

1. Go to [pythonanywhere.com](https://www.pythonanywhere.com)
2. Sign up for a free account (or paid for more resources)
3. Verify your email

## Step 2: Upload Your Code

### Option A: Using Git (Recommended)

1. Open a Bash console from PythonAnywhere dashboard
2. Clone your repository:
```bash
git clone https://github.com/yourusername/polymarket-trading-bot.git
cd polymarket-trading-bot
```

### Option B: Manual Upload

1. Click "Files" in PythonAnywhere dashboard
2. Navigate to your home directory
3. Create a new directory: `polymarket-trading-bot`
4. Upload all your files

## Step 3: Install Dependencies

1. Open a Bash console
2. Create a virtual environment:
```bash
cd polymarket-trading-bot
python3.10 -m venv venv
source venv/bin/activate
```

3. Install requirements:
```bash
pip install -r requirements.txt
```

## Step 4: Configure Environment Variables

1. Create `.env` file:
```bash
nano .env
```

2. Add your API keys (copy from your local `.env.example`):
```
POLYMARKET_API_KEY=your_key_here
POLYMARKET_API_SECRET=your_secret_here
# ... etc
```

3. Save and exit (Ctrl+X, then Y, then Enter)

## Step 5: Test the Bot

Run the bot once to ensure everything works:

```bash
source venv/bin/activate
python main.py
```

Check for any errors. If successful, proceed to scheduling.

## Step 6: Schedule the Bot

PythonAnywhere allows scheduled tasks on paid plans. For free accounts, you'll need to run manually or upgrade.

### For Paid Accounts:

1. Go to "Tasks" tab in dashboard
2. Click "Create a new scheduled task"
3. Set the command:
```bash
/home/yourusername/polymarket-trading-bot/venv/bin/python /home/yourusername/polymarket-trading-bot/main.py
```
4. Set frequency (e.g., every 6 hours)
5. Save

### For Free Accounts:

You can run the bot manually or keep a console open (not recommended for long-term).

## Step 7: Set Up Dashboard (Optional)

To run the Streamlit dashboard on PythonAnywhere:

1. Go to "Web" tab
2. Click "Add a new web app"
3. Choose "Manual configuration"
4. Select Python 3.10

5. Edit the WSGI configuration file to point to your Streamlit app:
```python
import sys
import os

path = '/home/yourusername/polymarket-trading-bot'
if path not in sys.path:
    sys.path.append(path)

os.environ['STREAMLIT_SERVER_PORT'] = '8000'
os.environ['STREAMLIT_SERVER_ADDRESS'] = '0.0.0.0'

from streamlit.web import cli as stcli
import sys

sys.argv = ["streamlit", "run", "/home/yourusername/polymarket-trading-bot/src/dashboard/streamlit_app.py"]
stcli.main()
```

**Note:** Streamlit on PythonAnywhere can be tricky. Consider using the bot without dashboard or viewing logs instead.

## Step 8: Monitor Logs

View logs to monitor bot activity:

```bash
cd polymarket-trading-bot
tail -f logs/bot.log
tail -f logs/trades.log
tail -f logs/errors.log
```

## Alternative: Railway.app (Recommended)

Railway offers better support for long-running processes:

1. Sign up at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables in Railway dashboard
4. Deploy automatically

Railway's free tier includes:
- $5 free credit per month
- Automatic deployments
- Better for 24/7 bots

## Alternative: Google Cloud Run

For more advanced users:

1. Containerize your app with Docker
2. Deploy to Cloud Run
3. Use Cloud Scheduler for periodic execution

## Troubleshooting

### "Module not found" errors
- Ensure virtual environment is activated
- Reinstall requirements: `pip install -r requirements.txt`

### Database errors
- Check that `data/` directory exists
- Ensure write permissions: `chmod 755 data/`

### API connection errors
- Verify API keys in `.env`
- Check internet connectivity
- Ensure no firewall blocking

### Out of memory
- Reduce `max_positions` in config
- Use lighter LLM model
- Upgrade to paid PythonAnywhere plan

## Cost Comparison

| Platform | Free Tier | Paid Tier | Best For |
|----------|-----------|-----------|----------|
| PythonAnywhere | Limited | $5/month | Simple bots |
| Railway | $5 credit | Pay-as-you-go | 24/7 bots |
| Google Cloud | $300 credit | Pay-as-you-go | Advanced users |
| Heroku | Deprecated | - | - |

## Security Checklist

- [ ] `.env` file is not committed to git
- [ ] API keys are stored securely
- [ ] Database file has proper permissions
- [ ] Logs don't contain sensitive data
- [ ] Paper trading tested thoroughly
- [ ] Monitoring alerts configured

## Next Steps

1. Monitor bot for 24-48 hours in paper trading
2. Review trade logs and performance
3. Adjust configuration as needed
4. Consider upgrading to paid hosting for reliability
5. Set up monitoring alerts (email/Telegram)

---

For issues, check the logs first, then consult the main README.md
