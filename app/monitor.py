import asyncio
import time
from dataclasses import asdict

from app.llm_advisor import StockAdvisor, StockRecommendation
from app.price_provider import YahooFinancePriceProvider
from app.store import InMemoryWatchStore, WatchRecord
from app.telegram import TelegramNotifier


def variance_percent(record: WatchRecord, price: float) -> float:
    if not record.baseline_price:
        return 0.0
    return ((price - record.baseline_price) / record.baseline_price) * 100


def build_alert(record: WatchRecord, price: float, movement: float) -> str:
    direction = "up" if movement > 0 else "down"
    return (
        f"<b>Stock alert</b>\n"
        f"{record.symbol} moved {direction} {abs(movement):.2f}%\n"
        f"Current price: {price:.2f}\n"
        f"Alert variance: {record.variance:.2f}%"
    )


class StockMonitor:
    def __init__(
        self,
        store: InMemoryWatchStore,
        price_provider: YahooFinancePriceProvider,
        notifier: TelegramNotifier,
        poll_interval_seconds: int,
        advisor: StockAdvisor | None = None,
        llm_analysis_interval_seconds: int = 3600,
    ) -> None:
        self.store = store
        self.price_provider = price_provider
        self.notifier = notifier
        self.poll_interval_seconds = poll_interval_seconds
        self.advisor = advisor
        self.llm_analysis_interval_seconds = llm_analysis_interval_seconds
        self._last_analysis_at = 0.0
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stopped.is_set():
            await self.check_once()
            await self.analyze_if_due()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def check_once(self) -> list[dict]:
        alerts = []
        for record in self.store.list():
            try:
                price = await asyncio.to_thread(self.price_provider.get_price, record.symbol)
                updated = self.store.update_price(record.symbol, price)
                if not updated:
                    continue
                movement = variance_percent(updated, price)
                if abs(movement) >= updated.variance:
                    message = build_alert(updated, price, movement)
                    await asyncio.to_thread(self.notifier.send, message)
                    self.store.mark_alerted(updated.symbol, price)
                    alerts.append({**asdict(updated), "movement": movement})
            except Exception as exc:
                print(f"[monitor] {record.symbol}: {exc}")
        return alerts

    async def analyze_if_due(self) -> list[StockRecommendation]:
        if not self.advisor:
            return []
        now = time.monotonic()
        if now - self._last_analysis_at < self.llm_analysis_interval_seconds:
            return []
        self._last_analysis_at = now
        return await self.run_llm_analysis()

    async def run_llm_analysis(self) -> list[StockRecommendation]:
        if not self.advisor:
            return []
        try:
            recommendations = await asyncio.to_thread(self.advisor.analyze_market)
            actionable = [
                item
                for item in recommendations
                if item.recommendation in {"BUY", "SELL"} and item.confidence >= 0.55
            ]
            if actionable:
                await asyncio.to_thread(self.notifier.send, build_llm_alert(actionable))
            return recommendations
        except Exception as exc:
            print(f"[llm-analysis] {exc}")
            return []


def build_llm_alert(recommendations: list[StockRecommendation]) -> str:
    lines = ["<b>LLM stock recommendations</b>", "Not financial advice."]
    for item in recommendations[:10]:
        lines.append(
            f"{item.symbol}: {item.recommendation} "
            f"({item.confidence:.0%}) - {item.reason}"
        )
    return "\n".join(lines)
