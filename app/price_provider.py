import json
import re
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

    def get_quotes(self, symbols: list[str]) -> list[dict]:
        clean_symbols = [symbol.upper().strip() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            return []

        quotes: list[dict] = []
        for index in range(0, len(clean_symbols), 50):
            batch = clean_symbols[index : index + 50]
            encoded_symbols = urllib.parse.quote(",".join(batch))
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={encoded_symbols}"
            request = urllib.request.Request(url, headers={"User-Agent": "stock-alert-agent/1.0"})

            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise PriceProviderError(f"Could not fetch quote batch: {exc}") from exc

            quotes.extend(payload.get("quoteResponse", {}).get("result", []))
        return quotes


class SP500UniverseProvider:
    WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    def get_symbols(self) -> list[str]:
        request = urllib.request.Request(self.WIKIPEDIA_URL, headers={"User-Agent": "stock-alert-agent/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8")
        except Exception as exc:
            raise PriceProviderError(f"Could not fetch S&P 500 symbols: {exc}") from exc

        table_match = re.search(r'<table[^>]+id="constituents"[\s\S]*?</table>', html)
        if not table_match:
            raise PriceProviderError("Could not find S&P 500 constituents table")

        rows = re.findall(r"<tr>([\s\S]*?)</tr>", table_match.group(0))
        symbols: list[str] = []
        for row in rows[1:]:
            cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row)
            if not cells:
                continue
            text = re.sub(r"<[^>]+>", "", cells[0])
            symbol = text.strip().replace(".", "-")
            if symbol:
                symbols.append(symbol)
        return symbols
