from datetime import datetime, timezone
from decimal import Decimal


class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, Decimal] = {}
        self._updated_at: dict[str, datetime] = {}

    def set_price(
        self,
        symbol: str,
        price: Decimal,
    ) -> None:
        normalized_symbol = symbol.strip().upper()

        self._prices[normalized_symbol] = price
        self._updated_at[normalized_symbol] = datetime.now(timezone.utc)

    def get_price(
        self,
        symbol: str,
    ) -> Decimal | None:
        normalized_symbol = symbol.strip().upper()
        return self._prices.get(normalized_symbol)

    def get_updated_at(
        self,
        symbol: str,
    ) -> datetime | None:
        normalized_symbol = symbol.strip().upper()
        return self._updated_at.get(normalized_symbol)

    def get_all_prices(self) -> dict[str, Decimal]:
        return self._prices.copy()

    def clear(self) -> None:
        self._prices.clear()
        self._updated_at.clear()