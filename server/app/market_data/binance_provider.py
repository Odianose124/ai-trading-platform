import asyncio
import json
import logging
from decimal import Decimal

import websockets

from app.database.connection import SessionLocal
from app.market_data.price_cache import PriceCache
from app.models.candle import Candle
from app.services.candle_service import (
    get_candle_close_time,
    get_candle_open_time,
    update_candle_from_trade,
)
from config.settings import settings


logger = logging.getLogger(__name__)


class BinanceMarketDataProvider:

    def __init__(self):
        self.websocket = None
        self.price_cache = PriceCache()
        self._running = False
        self._symbols = set()

        # Active 1-minute candles held in memory.
        #
        # Key:
        #     Internal symbol, e.g. BTCUSD
        #
        # Value:
        #     Detached Candle object containing the
        #     current minute's OHLCV data.
        self._active_candles: dict[str, Candle] = {}

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        symbol_mapping = {
            "BTCUSD": "BTCUSDT",
            "ETHUSD": "ETHUSDT",
            "BNBUSD": "BNBUSDT",
            "SOLUSD": "SOLUSDT",
            "XRPUSD": "XRPUSDT",
            "ADAUSD": "ADAUSDT",
            "DOGEUSD": "DOGEUSDT",
        }

        return symbol_mapping.get(
            normalized,
            normalized,
        )

    @staticmethod
    def provider_to_internal_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        symbol_mapping = {
            "BTCUSDT": "BTCUSD",
            "ETHUSDT": "ETHUSD",
            "BNBUSDT": "BNBUSD",
            "SOLUSDT": "SOLUSD",
            "XRPUSDT": "XRPUSD",
            "ADAUSDT": "ADAUSD",
            "DOGEUSDT": "DOGEUSD",
        }

        return symbol_mapping.get(
            normalized,
            normalized,
        )

    async def connect(self):
        self.websocket = await websockets.connect(
            settings.BINANCE_SPOT_WS_URL,
            ping_interval=20,
            ping_timeout=20,
        )

        logger.info(
            "Connected to Binance market-data WebSocket"
        )

    async def disconnect(self):
        self._running = False

        await self._flush_active_candles()

        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

        logger.info(
            "Disconnected from Binance market-data WebSocket"
        )

    async def subscribe(self, symbols: list[str]):
        if self.websocket is None:
            raise RuntimeError(
                "Binance WebSocket is not connected"
            )

        normalized_symbols = [
            self.normalize_symbol(symbol).lower()
            for symbol in symbols
        ]

        self._symbols.update(
            normalized_symbols
        )

        streams = [
            f"{symbol}@trade"
            for symbol in normalized_symbols
        ]

        message = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1,
        }

        await self.websocket.send(
            json.dumps(message)
        )

        logger.info(
            "Subscribed to Binance streams: %s",
            ", ".join(normalized_symbols),
        )

    async def listen(self):
        if self.websocket is None:
            raise RuntimeError(
                "Binance WebSocket is not connected"
            )

        self._running = True

        while self._running:

            try:
                message = await self.websocket.recv()

                if isinstance(message, bytes):
                    message = message.decode(
                        "utf-8"
                    )

                data = json.loads(message)

                self._process_message(data)

            except websockets.ConnectionClosed:
                logger.warning(
                    "Binance WebSocket connection closed"
                )

                self._running = False

            except asyncio.CancelledError:
                self._running = False
                raise

            except Exception:
                logger.exception(
                    "Error processing Binance "
                    "market-data message"
                )

    def _process_message(self, data: dict):

        # Binance subscription response.
        if "result" in data and "id" in data:
            logger.info(
                "Binance subscription response: %s",
                data,
            )
            return

        event_type = data.get("e")

        # We currently consume Binance trade events.
        if event_type != "trade":
            return

        provider_symbol = data.get("s")
        price = data.get("p")
        quantity = data.get("q")
        trade_timestamp = data.get("T")

        if (
            not provider_symbol
            or price is None
            or quantity is None
            or trade_timestamp is None
        ):
            return

        internal_symbol = (
            self.provider_to_internal_symbol(
                provider_symbol
            )
        )

        decimal_price = Decimal(
            str(price)
        )

        decimal_quantity = Decimal(
            str(quantity)
        )

        # Always update the live price immediately.
        self.price_cache.set_price(
            internal_symbol,
            decimal_price,
        )

        # Update the current 1-minute candle.
        self._update_active_candle(
            symbol=internal_symbol,
            trade_price=decimal_price,
            trade_quantity=decimal_quantity,
            trade_timestamp_ms=int(
                trade_timestamp
            ),
        )

    def _update_active_candle(
        self,
        symbol: str,
        trade_price: Decimal,
        trade_quantity: Decimal,
        trade_timestamp_ms: int,
    ):

        open_time = get_candle_open_time(
            trade_timestamp_ms
        )

        close_time = get_candle_close_time(
            open_time
        )

        active_candle = (
            self._active_candles.get(symbol)
        )

        # -------------------------------------------------
        # FIRST TRADE FOR THIS SYMBOL
        # -------------------------------------------------
        if active_candle is None:

            db = SessionLocal()

            try:
                existing_candle = (
                    db.query(Candle)
                    .filter(
                        Candle.symbol == symbol,
                        Candle.timeframe == "1m",
                        Candle.open_time == open_time,
                    )
                    .first()
                )

                if existing_candle is not None:

                    # A candle may already exist if the
                    # application was restarted during the
                    # same minute.
                    active_candle = Candle(
                        symbol=existing_candle.symbol,
                        timeframe=existing_candle.timeframe,
                        open_time=existing_candle.open_time,
                        close_time=existing_candle.close_time,
                        open=existing_candle.open,
                        high=existing_candle.high,
                        low=existing_candle.low,
                        close=existing_candle.close,
                        volume=existing_candle.volume,
                        trade_count=existing_candle.trade_count,
                    )

                    # Add the current trade.
                    if trade_price > active_candle.high:
                        active_candle.high = trade_price

                    if trade_price < active_candle.low:
                        active_candle.low = trade_price

                    active_candle.close = trade_price
                    active_candle.volume += trade_quantity
                    active_candle.trade_count += 1
                    active_candle.close_time = close_time

                else:

                    # Create a completely new candle
                    # without committing it yet.
                    active_candle = Candle(
                        symbol=symbol,
                        timeframe="1m",
                        open_time=open_time,
                        close_time=close_time,
                        open=trade_price,
                        high=trade_price,
                        low=trade_price,
                        close=trade_price,
                        volume=trade_quantity,
                        trade_count=1,
                    )

                self._active_candles[symbol] = (
                    active_candle
                )

            except Exception:

                db.rollback()

                logger.exception(
                    "Error creating active candle "
                    "for %s",
                    symbol,
                )

            finally:
                db.close()

            return

        # -------------------------------------------------
        # NEW MINUTE
        # -------------------------------------------------
        if active_candle.open_time != open_time:

            # The previous minute is complete.
            self._persist_candle(
                active_candle
            )

            # Start the new candle in memory.
            new_candle = Candle(
                symbol=symbol,
                timeframe="1m",
                open_time=open_time,
                close_time=close_time,
                open=trade_price,
                high=trade_price,
                low=trade_price,
                close=trade_price,
                volume=trade_quantity,
                trade_count=1,
            )

            self._active_candles[symbol] = (
                new_candle
            )

            return

        # -------------------------------------------------
        # SAME MINUTE
        # -------------------------------------------------

        if trade_price > active_candle.high:
            active_candle.high = trade_price

        if trade_price < active_candle.low:
            active_candle.low = trade_price

        active_candle.close = trade_price

        active_candle.volume += (
            trade_quantity
        )

        active_candle.trade_count += 1

        active_candle.close_time = close_time

    def _persist_candle(
        self,
        candle: Candle,
    ):

        db = SessionLocal()

        try:

            existing_candle = (
                db.query(Candle)
                .filter(
                    Candle.symbol == candle.symbol,
                    Candle.timeframe == candle.timeframe,
                    Candle.open_time == candle.open_time,
                )
                .first()
            )

            if existing_candle is None:

                # IMPORTANT:
                # Never attach the detached in-memory
                # SQLAlchemy object directly.
                #
                # Create a fresh database object instead.
                new_candle = Candle(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    open_time=candle.open_time,
                    close_time=candle.close_time,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    trade_count=candle.trade_count,
                )

                db.add(new_candle)

            else:

                # Update the existing database candle.
                existing_candle.open = candle.open
                existing_candle.high = candle.high
                existing_candle.low = candle.low
                existing_candle.close = candle.close
                existing_candle.volume = candle.volume
                existing_candle.trade_count = (
                    candle.trade_count
                )
                existing_candle.close_time = (
                    candle.close_time
                )

            db.commit()

            logger.info(
                "Persisted %s 1m candle: "
                "open=%s high=%s low=%s close=%s "
                "volume=%s trades=%s",
                candle.symbol,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.trade_count,
            )

        except Exception:

            db.rollback()

            logger.exception(
                "Error persisting candle for %s",
                candle.symbol,
            )

        finally:
            db.close()

    async def _flush_active_candles(self):

        if not self._active_candles:
            return

        candles = list(
            self._active_candles.values()
        )

        self._active_candles.clear()

        for candle in candles:
            self._persist_candle(candle)

    def get_price(
        self,
        symbol: str,
    ) -> Decimal | None:

        internal_symbol = (
            symbol.strip().upper()
        )

        return self.price_cache.get_price(
            internal_symbol
        )

    def get_all_prices(self):

        return self.price_cache.get_all_prices()

    def get_price_updated_at(
        self,
        symbol: str,
    ):

        internal_symbol = (
            symbol.strip().upper()
        )

        return self.price_cache.get_updated_at(
            internal_symbol
        )