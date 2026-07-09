from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from app.agent import build_agent
from app.config import load_settings
from app.models import PromptRequest, WatchItem, WatchRequest
from app.monitor import StockMonitor
from app.price_provider import PriceProviderError, YahooFinancePriceProvider
from app.store import InMemoryWatchStore
from app.telegram import TelegramNotifier


settings = load_settings()
store = InMemoryWatchStore()
price_provider = YahooFinancePriceProvider()
notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
monitor = StockMonitor(store, price_provider, notifier, settings.poll_interval_seconds)
agent = build_agent(store, price_provider, settings.default_variance_percent)


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    yield
    await monitor.stop()


app = FastAPI(
    title="LangGraph Stock Alert Agent",
    description="Local stock monitor with REST, intent routing, in-memory DB, and Telegram alerts.",
    version="0.1.0",
    lifespan=lifespan,
)


def to_watch_item(record) -> WatchItem:
    return WatchItem(**asdict(record))


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "telegram_enabled": notifier.enabled,
        "poll_interval_seconds": settings.poll_interval_seconds,
    }


@app.post("/watch", response_model=WatchItem)
def add_watch(request: WatchRequest) -> WatchItem:
    symbol = request.symbol.upper().strip()
    try:
        price = price_provider.get_price(symbol)
    except PriceProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = store.add(symbol, request.variance, baseline_price=price)
    return to_watch_item(record)


@app.get("/watch", response_model=list[WatchItem])
def list_watch() -> list[WatchItem]:
    return [to_watch_item(record) for record in store.list()]


@app.delete("/watch/{symbol}")
def delete_watch(symbol: str) -> dict:
    deleted = store.delete(symbol)
    return {"symbol": symbol.upper(), "deleted": deleted}


@app.post("/prompt")
def route_prompt(request: PromptRequest) -> dict:
    try:
        result = agent.invoke({"prompt": request.prompt})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "intent": result.get("intent"),
        "symbol": result.get("symbol"),
        "response": result.get("response"),
    }


@app.post("/monitor/check")
async def check_now() -> dict:
    alerts = await monitor.check_once()
    return {"alerts": alerts}
