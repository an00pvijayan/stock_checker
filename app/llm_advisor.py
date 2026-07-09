import json
import urllib.request
from dataclasses import dataclass
from typing import Literal

from app.price_provider import SP500UniverseProvider, YahooFinancePriceProvider
from app.store import InMemoryWatchStore


Recommendation = Literal["BUY", "HOLD", "SELL"]


@dataclass
class StockRecommendation:
    symbol: str
    recommendation: Recommendation
    confidence: float
    reason: str


@dataclass
class WatchlistAnalysis:
    symbol: str
    variance: float
    baseline_price: float | None
    last_price: float | None
    recommendation: Recommendation
    confidence: float
    reason: str


class LLMClient:
    provider = "none"

    @property
    def enabled(self) -> bool:
        return False

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("No LLM provider is configured")


class OpenAILLMClient:
    provider = "openai"

    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return extract_response_text(data)


class OllamaLLMClient:
    provider = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        message = data.get("message", {})
        return str(message.get("content", "")).strip()


def build_llm_client(
    provider: str,
    openai_api_key: str | None,
    openai_model: str,
    ollama_base_url: str,
    ollama_model: str,
) -> LLMClient | OpenAILLMClient | OllamaLLMClient:
    if provider == "ollama":
        return OllamaLLMClient(ollama_base_url, ollama_model)
    if provider == "openai":
        return OpenAILLMClient(openai_api_key, openai_model)
    return LLMClient()


def extract_response_text(data: dict) -> str:
    if data.get("output_text"):
        return data["output_text"]

    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


class StockAdvisor:
    def __init__(
        self,
        llm: LLMClient | OpenAILLMClient | OllamaLLMClient,
        store: InMemoryWatchStore,
        price_provider: YahooFinancePriceProvider,
        universe_provider: SP500UniverseProvider,
        max_symbols: int,
    ) -> None:
        self.llm = llm
        self.store = store
        self.price_provider = price_provider
        self.universe_provider = universe_provider
        self.max_symbols = max_symbols

    def analyze_market(self) -> list[StockRecommendation]:
        symbols = self._analysis_symbols()
        quotes = self.price_provider.get_quotes(symbols)
        snapshot = compact_quotes(quotes)
        return self._recommend(
            snapshot,
            (
                "Analyze these S&P 500 and user-watchlist quote snapshots. "
                "Suggest BUY, HOLD, or SELL for noteworthy stocks only. Return at most 25 items."
            ),
        )

    def analyze_watchlist(self) -> list[WatchlistAnalysis]:
        records = self.store.list()
        if not records:
            return []

        quotes = self.price_provider.get_quotes([record.symbol for record in records])
        snapshot = compact_quotes(quotes)
        recommendations = self._recommend(snapshot, "Analyze only the user's monitored watchlist stocks.")
        recommendations_by_symbol = {item.symbol: item for item in recommendations}
        fallback_by_symbol = {item.symbol: item for item in fallback_recommendations(snapshot)}

        analyses: list[WatchlistAnalysis] = []
        for record in records:
            recommendation = recommendations_by_symbol.get(record.symbol) or fallback_by_symbol.get(record.symbol)
            if not recommendation:
                recommendation = StockRecommendation(
                    symbol=record.symbol,
                    recommendation="HOLD",
                    confidence=0,
                    reason="No quote data was available for analysis.",
                )
            analyses.append(
                WatchlistAnalysis(
                    symbol=record.symbol,
                    variance=record.variance,
                    baseline_price=record.baseline_price,
                    last_price=record.last_price,
                    recommendation=recommendation.recommendation,
                    confidence=recommendation.confidence,
                    reason=recommendation.reason,
                )
            )
        return analyses

    def answer_chat(self, prompt: str) -> str:
        records = self.store.list()
        quote_symbols = [record.symbol for record in records]
        quotes = self.price_provider.get_quotes(quote_symbols) if quote_symbols else []
        snapshot = compact_quotes(quotes)

        if not self.llm.enabled:
            if not records:
                return "No stocks are being monitored yet. Use ADD: SYMBOL variance to start."
            lines = ["Current monitored stocks:"]
            for record in records:
                last_price = record.last_price
                price_text = f"{last_price:.2f}" if last_price is not None else "not fetched yet"
                lines.append(f"- {record.symbol}: last={price_text}, variance={record.variance:.2f}%")
            return "\n".join(lines)

        return self.llm.complete(
            system=(
                "You answer questions about the user's monitored stocks. Be concise, "
                "mention that this is not financial advice when giving buy/sell style views, "
                "and use only the supplied watchlist and quote data."
            ),
            user=(
                f"User prompt: {prompt}\n"
                f"Watchlist: {json.dumps([record.__dict__ for record in records], default=str)}\n"
                f"Latest quotes: {json.dumps(snapshot, separators=(',', ':'))}"
            ),
        )

    def _analysis_symbols(self) -> list[str]:
        sp500 = self.universe_provider.get_symbols()
        watched = [record.symbol for record in self.store.list()]
        combined = list(dict.fromkeys(watched + sp500))
        return combined[: self.max_symbols]

    def _recommend(self, snapshot: list[dict], instruction: str) -> list[StockRecommendation]:
        if not snapshot:
            return []
        if not self.llm.enabled:
            return fallback_recommendations(snapshot)

        response = self.llm.complete(
            system=(
                "You are a cautious stock analysis assistant. This is not financial advice. "
                "Use only the supplied quote snapshot. Return strict JSON with a top-level "
                "'recommendations' array. Each item must have symbol, recommendation "
                "(BUY, HOLD, or SELL), confidence from 0 to 1, and reason. Prefer HOLD "
                "unless the supplied data gives a clear short-term momentum signal."
            ),
            user=(
                f"{instruction} "
                "Return one recommendation per supplied symbol unless quote data is unusable.\n\n"
                f"{json.dumps(snapshot, separators=(',', ':'))}"
            ),
        )
        return parse_recommendations(response)


def compact_quotes(quotes: list[dict]) -> list[dict]:
    compact: list[dict] = []
    for quote in quotes:
        symbol = quote.get("symbol")
        price = quote.get("regularMarketPrice")
        if not symbol or price is None:
            continue
        compact.append(
            {
                "symbol": symbol,
                "price": price,
                "changePercent": quote.get("regularMarketChangePercent"),
                "marketCap": quote.get("marketCap"),
                "fiftyDayAverage": quote.get("fiftyDayAverage"),
                "twoHundredDayAverage": quote.get("twoHundredDayAverage"),
                "fiftyTwoWeekHigh": quote.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": quote.get("fiftyTwoWeekLow"),
                "volume": quote.get("regularMarketVolume"),
                "averageVolume": quote.get("averageDailyVolume3Month"),
            }
        )
    return compact


def fallback_recommendations(snapshot: list[dict]) -> list[StockRecommendation]:
    recommendations: list[StockRecommendation] = []
    for quote in snapshot:
        change = quote.get("changePercent") or 0
        price = quote.get("price") or 0
        fifty_day = quote.get("fiftyDayAverage") or price
        two_hundred_day = quote.get("twoHundredDayAverage") or price
        recommendation: Recommendation = "HOLD"
        reason = "No LLM configured; deterministic fallback sees no strong signal."
        if change > 2 and price > fifty_day > two_hundred_day:
            recommendation = "BUY"
            reason = "No LLM configured; positive momentum above 50-day and 200-day averages."
        elif change < -2 and price < fifty_day < two_hundred_day:
            recommendation = "SELL"
            reason = "No LLM configured; negative momentum below 50-day and 200-day averages."
        recommendations.append(
            StockRecommendation(
                symbol=quote["symbol"],
                recommendation=recommendation,
                confidence=0.4,
                reason=reason,
            )
        )
    return recommendations


def parse_recommendations(response: str) -> list[StockRecommendation]:
    raw = response.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).strip()

    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("recommendations", [])
    recommendations: list[StockRecommendation] = []
    for item in items:
        recommendation = str(item.get("recommendation", "HOLD")).upper()
        if recommendation not in {"BUY", "HOLD", "SELL"}:
            recommendation = "HOLD"
        recommendations.append(
            StockRecommendation(
                symbol=str(item.get("symbol", "")).upper(),
                recommendation=recommendation,  # type: ignore[arg-type]
                confidence=float(item.get("confidence", 0)),
                reason=str(item.get("reason", "")),
            )
        )
    return [item for item in recommendations if item.symbol]
