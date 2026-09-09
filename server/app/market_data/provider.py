from abc import ABC, abstractmethod
from decimal import Decimal


class MarketDataProvider(ABC):

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the market-data provider."""
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the market-data provider."""
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to market-price streams."""
        raise NotImplementedError

    @abstractmethod
    async def listen(self) -> None:
        """Listen continuously for market-data updates."""
        raise NotImplementedError

    @abstractmethod
    def get_price(self, symbol: str) -> Decimal | None:
        """Return the latest known market price."""
        raise NotImplementedError