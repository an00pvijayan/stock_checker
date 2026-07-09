from dataclasses import asdict
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.price_provider import YahooFinancePriceProvider
from app.store import InMemoryWatchStore


Intent = Literal["add", "delete", "chat"]


class AgentState(TypedDict, total=False):
    prompt: str
    intent: Intent
    symbol: str
    variance: float
    response: str


def parse_add(prompt: str, default_variance: float) -> tuple[str, float]:
    body = prompt.split(":", 1)[1].strip()
    parts = body.replace(",", " ").split()
    if not parts:
        raise ValueError("ADD needs a stock symbol, for example ADD: AAPL 1.5")
    symbol = parts[0].upper()
    variance = float(parts[1]) if len(parts) > 1 else default_variance
    if variance <= 0:
        raise ValueError("Variance must be greater than zero")
    return symbol, variance


def parse_delete(prompt: str) -> str:
    body = prompt.split(":", 1)[1].strip()
    parts = body.replace(",", " ").split()
    if not parts:
        raise ValueError("DEL needs a stock symbol, for example DEL: AAPL")
    return parts[0].upper()


def build_agent(
    store: InMemoryWatchStore,
    price_provider: YahooFinancePriceProvider,
    default_variance: float,
):
    def router_node(state: AgentState) -> AgentState:
        prompt = state["prompt"].strip()
        upper_prompt = prompt.upper()
        if upper_prompt.startswith("ADD:"):
            symbol, variance = parse_add(prompt, default_variance)
            return {**state, "intent": "add", "symbol": symbol, "variance": variance}
        if upper_prompt.startswith("DEL:"):
            symbol = parse_delete(prompt)
            return {**state, "intent": "delete", "symbol": symbol}
        return {**state, "intent": "chat"}

    def add_node(state: AgentState) -> AgentState:
        symbol = state["symbol"]
        variance = state["variance"]
        price = price_provider.get_price(symbol)
        record = store.add(symbol, variance, baseline_price=price)
        return {
            **state,
            "response": (
                f"Added {record.symbol} for monitoring at {variance:.2f}% variance. "
                f"Baseline price is {price:.2f}."
            ),
        }

    def delete_node(state: AgentState) -> AgentState:
        symbol = state["symbol"]
        deleted = store.delete(symbol)
        response = f"Removed {symbol} from monitoring." if deleted else f"{symbol} was not in the watchlist."
        return {**state, "response": response}

    def chat_node(state: AgentState) -> AgentState:
        records = store.list()
        if not records:
            return {
                **state,
                "response": "No stocks are being monitored yet. Use ADD: SYMBOL variance to start.",
            }

        lines = ["Current monitored stocks:"]
        for record in records:
            data = asdict(record)
            last_price = data["last_price"]
            baseline = data["baseline_price"]
            price_text = f"{last_price:.2f}" if last_price is not None else "not fetched yet"
            baseline_text = f"{baseline:.2f}" if baseline is not None else "not set"
            lines.append(
                f"- {record.symbol}: last={price_text}, baseline={baseline_text}, variance={record.variance:.2f}%"
            )
        return {**state, "response": "\n".join(lines)}

    def route(state: AgentState) -> str:
        return state["intent"]

    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("add", add_node)
    graph.add_node("delete", delete_node)
    graph.add_node("chat", chat_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route,
        {"add": "add", "delete": "delete", "chat": "chat"},
    )
    graph.add_edge("add", END)
    graph.add_edge("delete", END)
    graph.add_edge("chat", END)
    return graph.compile()
