from pydantic import BaseModel, Field


class WatchRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["AAPL"])
    variance: float = Field(..., gt=0, description="Percentage movement needed to alert")


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, examples=["ADD: AAPL 1.5"])


class WatchItem(BaseModel):
    symbol: str
    variance: float
    baseline_price: float | None = None
    last_price: float | None = None
    last_alert_price: float | None = None


class WatchlistAnalysisItem(BaseModel):
    symbol: str
    variance: float
    baseline_price: float | None = None
    last_price: float | None = None
    recommendation: str
    confidence: float
    reason: str


class WatchlistStatusResponse(BaseModel):
    count: int
    llm_provider: str
    llm_enabled: bool
    items: list[WatchlistAnalysisItem]
