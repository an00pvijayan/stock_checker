from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.config import load_settings
from app.container import ApplicationContainer
from app.models import PromptRequest, WatchItem, WatchRequest, WatchlistStatusResponse
from app.price_provider import PriceProviderError


settings = load_settings()
container = ApplicationContainer(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container.send_startup_health_report()
    container.monitor.start()
    yield
    await container.monitor.stop()


app = FastAPI(
    title="LangGraph Stock Alert Agent",
    description="Local stock monitor with REST, intent routing, in-memory DB, and Telegram alerts.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return container.health_payload()


@app.post("/watch", response_model=WatchItem)
def add_watch(request: WatchRequest) -> WatchItem:
    symbol = request.symbol.upper().strip()
    try:
        price = container.price_provider.get_price(symbol)
    except PriceProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = container.store.add(symbol, request.variance, baseline_price=price)
    return container.to_watch_item(record)


@app.get("/watch", response_model=list[WatchItem])
def list_watch() -> list[WatchItem]:
    return [container.to_watch_item(record) for record in container.store.list()]


@app.delete("/watch/{symbol}")
def delete_watch(symbol: str) -> dict:
    deleted = container.store.delete(symbol)
    return {"symbol": symbol.upper(), "deleted": deleted}


@app.get("/status", response_model=WatchlistStatusResponse)
def watchlist_status() -> WatchlistStatusResponse:
    return container.watchlist_status()


@app.post("/prompt")
def route_prompt(request: PromptRequest) -> dict:
    try:
        result = container.agent.invoke({"prompt": request.prompt})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "intent": result.get("intent"),
        "symbol": result.get("symbol"),
        "response": result.get("response"),
    }


@app.post("/monitor/check")
async def check_now() -> dict:
    alerts = await container.monitor.check_once()
    return {"alerts": alerts}


@app.post("/analysis/run")
async def run_analysis_now() -> dict:
    recommendations = await container.monitor.run_llm_analysis()
    return {"recommendations": [item.__dict__ for item in recommendations]}
