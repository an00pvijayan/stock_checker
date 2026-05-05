# Free morning stock alert agent

This is a lightweight local stock-checking agent you can run for free on your Mac.

## What it does

- checks stock prices from Yahoo Finance
- compares them against price targets you choose
- shows a macOS notification when a target is hit
- can be scheduled every morning with `cron`

## Setup

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create your config:

```bash
cp watchlist.example.json watchlist.json
```

3. Edit `watchlist.json` with your own symbols and target prices.

Examples:

- US stocks: `AAPL`, `MSFT`, `NVDA`
- NSE India: `RELIANCE.NS`, `TCS.NS`, `INFY.NS`
- BSE India: `RELIANCE.BO`

## Run it

```bash
python3 stock_agent.py --config watchlist.json
```

If you want a notification even when no target is hit:

```bash
python3 stock_agent.py --config watchlist.json --always-notify
```

## Schedule it every morning

Open your crontab:

```bash
crontab -e
```

Add a line like this for 9:00 AM every day:

```cron
0 9 * * * cd "/Users/anoop/Documents/New project" && /usr/bin/python3 stock_agent.py --config watchlist.json --always-notify >> stock_agent.log 2>&1
```

## Notes

- The script uses the latest daily close from Yahoo Finance data.
- If you want intraday alerts during market hours, the agent can be upgraded to use a shorter interval and run more often.
- For completely free alerts, local notifications are the simplest option. Email, Telegram, or Slack can be added later.
