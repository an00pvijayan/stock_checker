from dataclasses import dataclass
from threading import RLock


@dataclass
class WatchRecord:
    symbol: str
    variance: float
    baseline_price: float | None = None
    last_price: float | None = None
    last_alert_price: float | None = None


class InMemoryWatchStore:
    def __init__(self) -> None:
        self._records: dict[str, WatchRecord] = {}
        self._lock = RLock()

    def add(self, symbol: str, variance: float, baseline_price: float | None = None) -> WatchRecord:
        normalized = symbol.upper().strip()
        with self._lock:
            existing = self._records.get(normalized)
            if existing:
                existing.variance = variance
                if baseline_price is not None:
                    existing.baseline_price = baseline_price
                    existing.last_price = baseline_price
                return existing

            record = WatchRecord(
                symbol=normalized,
                variance=variance,
                baseline_price=baseline_price,
                last_price=baseline_price,
            )
            self._records[normalized] = record
            return record

    def delete(self, symbol: str) -> bool:
        normalized = symbol.upper().strip()
        with self._lock:
            return self._records.pop(normalized, None) is not None

    def get(self, symbol: str) -> WatchRecord | None:
        normalized = symbol.upper().strip()
        with self._lock:
            return self._records.get(normalized)

    def list(self) -> list[WatchRecord]:
        with self._lock:
            return list(self._records.values())

    def update_price(self, symbol: str, price: float) -> WatchRecord | None:
        normalized = symbol.upper().strip()
        with self._lock:
            record = self._records.get(normalized)
            if not record:
                return None
            record.last_price = price
            if record.baseline_price is None:
                record.baseline_price = price
            return record

    def mark_alerted(self, symbol: str, price: float) -> None:
        normalized = symbol.upper().strip()
        with self._lock:
            record = self._records.get(normalized)
            if record:
                record.last_alert_price = price
                record.baseline_price = price
