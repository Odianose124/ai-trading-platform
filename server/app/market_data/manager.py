import asyncio
import logging

from app.market_data.binance_provider import (
    BinanceMarketDataProvider,
)
from config.settings import settings


logger = logging.getLogger(__name__)


class MarketDataManager:
    def __init__(self) -> None:
        self.provider = BinanceMarketDataProvider()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(
        self,
        symbols: list[str],
    ) -> None:
        if self._running:
            return

        self._running = True

        while self._running:
            try:
                await self.provider.connect()

                await self.provider.subscribe(
                    symbols
                )

                await self.provider.listen()

            except asyncio.CancelledError:
                self._running = False
                raise

            except Exception:
                logger.exception(
                    "Market-data connection failed"
                )

            finally:
                await self.provider.disconnect()

            if self._running:
                logger.info(
                    "Reconnecting to market-data provider in %s seconds",
                    settings.MARKET_DATA_RECONNECT_DELAY_SECONDS,
                )

                await asyncio.sleep(
                    settings.MARKET_DATA_RECONNECT_DELAY_SECONDS
                )

    async def start_background(
        self,
        symbols: list[str],
    ) -> None:
        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.create_task(
            self.start(symbols)
        )

    async def stop(self) -> None:
        self._running = False

        await self.provider.disconnect()

        if self._task is not None:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None

    def get_price(self, symbol: str):
        return self.provider.get_price(symbol)

    def get_all_prices(self):
        return self.provider.get_all_prices()

    def get_price_updated_at(self, symbol: str):
        return self.provider.get_price_updated_at(symbol)