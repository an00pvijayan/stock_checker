from dataclasses import asdict

from app.agent import build_agent
from app.config import Settings
from app.llm_advisor import StockAdvisor, build_llm_client
from app.models import WatchItem, WatchlistAnalysisItem, WatchlistStatusResponse
from app.monitor import StockMonitor
from app.price_provider import SP500UniverseProvider, YahooFinancePriceProvider
from app.store import InMemoryWatchStore
from app.telegram import TelegramNotifier


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = InMemoryWatchStore()
        self.price_provider = YahooFinancePriceProvider()
        self.universe_provider = SP500UniverseProvider()
        self.notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
        self.llm_client = build_llm_client(
            settings.llm_provider,
            settings.openai_api_key,
            settings.openai_model,
            settings.ollama_base_url,
            settings.ollama_model,
        )
        self.advisor = StockAdvisor(
            self.llm_client,
            self.store,
            self.price_provider,
            self.universe_provider,
            settings.llm_analysis_max_symbols,
        )
        self.monitor = StockMonitor(
            self.store,
            self.price_provider,
            self.notifier,
            settings.poll_interval_seconds,
            advisor=self.advisor,
            llm_analysis_interval_seconds=settings.llm_analysis_interval_seconds,
        )
        self.agent = build_agent(
            self.store,
            self.price_provider,
            settings.default_variance_percent,
            advisor=self.advisor,
        )

    def health_payload(self) -> dict:
        return {
            "status": "ok",
            "telegram_enabled": self.notifier.enabled,
            "llm_enabled": self.llm_client.enabled,
            "llm_provider": self.llm_client.provider,
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "llm_analysis_interval_seconds": self.settings.llm_analysis_interval_seconds,
            "watch_count": len(self.store.list()),
        }

    def send_startup_health_report(self) -> None:
        health = self.health_payload()
        message = (
            "<b>Stock checker started</b>\n"
            f"Status: {health['status']}\n"
            f"Telegram: {'enabled' if health['telegram_enabled'] else 'disabled'}\n"
            f"LLM: {health['llm_provider']} "
            f"({'enabled' if health['llm_enabled'] else 'disabled'})\n"
            f"Price poll interval: {health['poll_interval_seconds']}s\n"
            f"LLM analysis interval: {health['llm_analysis_interval_seconds']}s\n"
            f"Watchlist size: {health['watch_count']}"
        )
        try:
            self.notifier.send(message)
        except Exception as exc:
            print(f"[startup-health] Telegram notification failed: {exc}")

    def to_watch_item(self, record) -> WatchItem:
        return WatchItem(**asdict(record))

    def watchlist_status(self) -> WatchlistStatusResponse:
        analyses = self.advisor.analyze_watchlist()
        items = [WatchlistAnalysisItem(**asdict(item)) for item in analyses]
        return WatchlistStatusResponse(
            count=len(items),
            llm_provider=self.llm_client.provider,
            llm_enabled=self.llm_client.enabled,
            items=items,
        )
