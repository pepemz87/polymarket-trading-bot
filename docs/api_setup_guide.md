# API Setup Guide

This guide will help you obtain all necessary API keys for the Polymarket trading bot.

## Required APIs

### 1. Gemini API (Primary LLM) - FREE ✅

**Cost:** Free tier includes 1500 requests/day

**Steps:**
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the API key
5. Add to `.env`:
   ```
   GEMINI_API_KEY=your_key_here
   ```

**Models Available:**
- `gemini-1.5-flash` (Recommended - Fast & Free)
- `gemini-1.5-pro` (More capable, 50 requests/day free)

### 2. Groq API (Backup LLM) - FREE ✅

**Cost:** Free tier includes 30 requests/minute

**Steps:**
1. Go to [Groq Console](https://console.groq.com/)
2. Sign up for an account
3. Navigate to API Keys section
4. Click "Create API Key"
5. Copy the API key
6. Add to `.env`:
   ```
   GROQ_API_KEY=your_key_here
   ```

**Models Available:**
- `llama-3.1-70b-versatile` (Recommended)
- `llama-3.1-8b-instant` (Faster, less capable)

### 3. Polymarket API - REQUIRED 🔑

**Cost:** Free (requires Polymarket account)

**Steps:**

#### A. Create Polymarket Account
1. Go to [Polymarket](https://polymarket.com)
2. Sign up and complete KYC if required
3. Fund your account with USDC (for live trading)

#### B. Get API Credentials

**Option 1: Using Polymarket Dashboard**
1. Log into Polymarket
2. Go to Settings → API
3. Generate API credentials
4. Save: API Key, Secret, Passphrase

**Option 2: Derive from Private Key**
1. Export your wallet private key from Polymarket
2. Use the derivation endpoint to get API credentials
3. See [Polymarket API Docs](https://docs.polymarket.com/) for details

#### C. Add to `.env`
```
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_API_PASSPHRASE=your_passphrase
POLYMARKET_PRIVATE_KEY=your_private_key
```

**⚠️ Security Warning:**
- Never share your private key
- Never commit `.env` to git
- Use paper trading first

## Optional APIs

### 4. NewsAPI (News Data) - FREE/PAID

**Cost:** Free tier includes 100 requests/day

**Steps:**
1. Go to [NewsAPI](https://newsapi.org/)
2. Sign up for a free account
3. Get your API key from dashboard
4. Add to `.env`:
   ```
   NEWS_API_KEY=your_key_here
   ```

**Free Tier Limits:**
- 100 requests/day
- News up to 1 month old
- Good enough for bot usage

### 5. The Odds API (Odds Comparison) - FREE/PAID

**Cost:** Free tier includes 500 requests/month

**Steps:**
1. Go to [The Odds API](https://the-odds-api.com/)
2. Sign up for free account
3. Get API key from dashboard
4. Add to `.env`:
   ```
   ODDS_API_KEY=your_key_here
   ```

**Note:** Optional but helpful for comparing Polymarket odds with traditional bookmakers.

### 6. Sports Data APIs (Optional)

For enhanced statistics:

**API-FOOTBALL (Soccer)**
- Free tier: 100 requests/day
- [RapidAPI - API-FOOTBALL](https://rapidapi.com/api-sports/api/api-football)

**NBA API (Basketball)**
- Free unofficial API
- [NBA Stats API](https://github.com/swar/nba_api)

## API Key Security Best Practices

### 1. Environment Variables
✅ Store in `.env` file
❌ Never hardcode in source code
❌ Never commit to git

### 2. Permissions
- Set `.env` file permissions: `chmod 600 .env`
- Restrict API key permissions on provider side
- Use separate keys for dev/prod

### 3. Rotation
- Rotate keys periodically (every 90 days)
- Immediately rotate if compromised
- Keep backup keys ready

### 4. Monitoring
- Monitor API usage on provider dashboards
- Set up alerts for unusual activity
- Track costs if using paid tiers

## Testing API Keys

After adding all keys to `.env`, test them:

```python
from src.utils.config import get_config

config = get_config()
validations = config.validate_api_keys()

print("API Key Validation:")
for api, is_valid in validations.items():
    status = "✅" if is_valid else "❌"
    print(f"{status} {api}: {is_valid}")
```

## API Rate Limits Summary

| API | Free Tier | Rate Limit | Notes |
|-----|-----------|------------|-------|
| Gemini | 1500 req/day | 60 req/min | Recommended primary |
| Groq | Unlimited | 30 req/min | Good backup |
| Polymarket | Unlimited | Varies | Required for trading |
| NewsAPI | 100 req/day | - | Optional |
| The Odds API | 500 req/month | - | Optional |

## Cost Estimates

### Free Tier Only
- **Monthly Cost:** $0
- **Limitations:** 
  - ~50 predictions/day (Gemini limit)
  - Limited news data
  - No odds comparison

### With Paid APIs
- **Gemini Pro:** ~$0.50/month (if exceeding free tier)
- **NewsAPI Pro:** $449/month (probably overkill)
- **The Odds API:** $10-50/month

**Recommendation:** Start with free tiers, upgrade only if needed.

## Troubleshooting

### "Invalid API Key" Error
- Double-check key in `.env`
- Ensure no extra spaces
- Verify key is active on provider dashboard

### "Rate Limit Exceeded"
- Check usage on provider dashboard
- Reduce `scan_markets_interval` in config
- Switch to backup provider

### "Insufficient Permissions"
- Check API key permissions
- Some providers require specific scopes
- Regenerate key with correct permissions

## Next Steps

1. ✅ Obtain all required API keys
2. ✅ Add to `.env` file
3. ✅ Test configuration
4. ✅ Run bot in paper trading mode
5. ✅ Monitor API usage
6. ✅ Adjust rate limits in config if needed

---

For more help, see the main [README.md](../README.md)
