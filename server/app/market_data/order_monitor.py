import asyncio
import logging
from decimal import Decimal

from app.database.connection import SessionLocal
from app.services.sl_tp_service import process_open_orders


logger = logging.getLogger(__name__)


class LiveOrderMonitor:
    def __init__(
        self,
        market_data_manager,
        symbols: list[str],
        interval_seconds: float = 0.25,
    ) -> None:
        self.market_data_manager = market_data_manager
        self.symbols = symbols
        self.interval_seconds = interval_seconds

        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return

        self._running = True

        logger.info(
            "Live order monitor started for symbols: %s",
            ", ".join(self.symbols),
        )

        while self._running:
            db = SessionLocal()

            try:
                market_prices: dict[str, Decimal] = {}

                for symbol in self.symbols:
                    price = self.market_data_manager.get_price(symbol)

                    if price is not None:
                        market_prices[symbol] = price

                if market_prices:
                    closed_orders = process_open_orders(
                        db=db,
                        market_prices=market_prices,
                    )

                    for order in closed_orders:
                        logger.info(
                            "Order #%s automatically closed: %s %s at %s",
                            order.id,
                            order.side.upper(),
                            order.symbol,
                            (
                                order.stop_loss
                                if order.profit_loss < 0
                                else order.take_profit
                            ),
                        )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Error while processing live orders"
                )

            finally:
                db.close()

            await asyncio.sleep(self.interval_seconds)

    async def start_background(self) -> None:
        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.create_task(
            self.start()
        )

    async def stop(self) -> None:
        self._running = False

        if self._task is not None:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None