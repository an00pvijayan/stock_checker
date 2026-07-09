import json
import urllib.parse
import urllib.request


class PriceProviderError(RuntimeError):
    pass


class YahooFinancePriceProvider:
    def get_price(self, symbol: str) -> float:
        encoded_symbol = urllib.parse.quote(symbol.upper().strip())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=1d&interval=1m"
        request = urllib.request.Request(url, headers={"User-Agent": "stock-alert-agent/1.0"})

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise PriceProviderError(f"Could not fetch price for {symbol}: {exc}") from exc

        result = payload.get("chart", {}).get("result") or []
        if not result:
            raise PriceProviderError(f"No price data returned for {symbol}")

        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if price is None:
            raise PriceProviderError(f"No usable price in Yahoo response for {symbol}")

        return float(price)
