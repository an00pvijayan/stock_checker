import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    poll_interval_seconds: int
    default_variance_percent: float
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    ollama_base_url: str
    ollama_model: str
    llm_analysis_interval_seconds: int
    llm_analysis_max_symbols: int


def load_settings() -> Settings:
    load_dotenv(Path(".env"))
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        default_variance_percent=float(os.getenv("DEFAULT_VARIANCE_PERCENT", "1.0")),
        llm_provider=os.getenv("LLM_PROVIDER", "openai").lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        llm_analysis_interval_seconds=int(os.getenv("LLM_ANALYSIS_INTERVAL_SECONDS", "3600")),
        llm_analysis_max_symbols=int(os.getenv("LLM_ANALYSIS_MAX_SYMBOLS", "500")),
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
