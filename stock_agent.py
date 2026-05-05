#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yfinance as yf


@dataclass
class StockRule:
    ticker: str
    above: float | None = None
    below: float | None = None


def load_config(path: Path) -> list[StockRule]:
    data = json.loads(path.read_text())
    rules = []
    for item in data.get("symbols", []):
        rules.append(
            StockRule(
                ticker=item["ticker"],
                above=item.get("above"),
                below=item.get("below"),
            )
        )
    return rules


def fetch_last_price(ticker: str) -> float:
    history = yf.Ticker(ticker).history(period="2d", interval="1d", auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price data returned for {ticker}")
    close_price = history["Close"].dropna()
    if close_price.empty:
        raise ValueError(f"No close price available for {ticker}")
    return float(close_price.iloc[-1])


def evaluate_rule(rule: StockRule, price: float) -> str | None:
    if rule.above is not None and price >= rule.above:
        return f"{rule.ticker} is at {price:.2f}, above your target of {rule.above:.2f}"
    if rule.below is not None and price <= rule.below:
        return f"{rule.ticker} is at {price:.2f}, below your target of {rule.below:.2f}"
    return None


def send_notification(title: str, message: str) -> None:
    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script], check=False)


def print_report(lines: list[str]) -> None:
    for line in lines:
        print(line)


def run_agent(config_path: Path, always_notify: bool) -> int:
    rules = load_config(config_path)
    if not rules:
        print("No symbols found in config.", file=sys.stderr)
        return 1

    triggered: list[str] = []
    summary: list[str] = []

    for rule in rules:
        try:
            price = fetch_last_price(rule.ticker)
            summary.append(f"{rule.ticker}: {price:.2f}")
            alert = evaluate_rule(rule, price)
            if alert:
                triggered.append(alert)
        except Exception as exc:
            summary.append(f"{rule.ticker}: error - {exc}")

    print_report(summary)

    if triggered:
        message = "\n".join(triggered[:5])
        send_notification("Stock alert", message)
        print("\nAlerts:")
        print_report(triggered)
        return 0

    if always_notify:
        send_notification("Stock check complete", ", ".join(summary[:4]))

    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Morning stock price alert agent")
    parser.add_argument(
        "--config",
        default="watchlist.json",
        help="Path to watchlist JSON file",
    )
    parser.add_argument(
        "--always-notify",
        action="store_true",
        help="Send a notification even when no alert thresholds are hit",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    return run_agent(Path(args.config), args.always_notify)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
