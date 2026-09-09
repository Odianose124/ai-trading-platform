from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import MetaTrader5 as mt5

from app.market_data_mt5.service import (
    MT5MarketDataError,
    mt5_market_data_service,
)


TIMEFRAME_MAP = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "30m": mt5.TIMEFRAME_M30,
    "1h": mt5.TIMEFRAME_H1,
    "4h": mt5.TIMEFRAME_H4,
    "1d": mt5.TIMEFRAME_D1,
}


TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class MT5CandleDataError(RuntimeError):
    """Raised when MT5 candle data cannot be retrieved."""


class MT5CandleService:
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise MT5CandleDataError(
                "Trading symbol cannot be empty"
            )

        if normalized_timeframe not in TIMEFRAME_MAP:
            raise MT5CandleDataError(
                f"Unsupported timeframe: {timeframe}"
            )

        if limit < 1 or limit > 5000:
            raise MT5CandleDataError(
                "Candle limit must be between 1 and 5000"
            )

        try:
            mt5_symbol = mt5_market_data_service.discover_symbol(
                normalized_symbol
            )
        except MT5MarketDataError as exc:
            raise MT5CandleDataError(str(exc)) from exc

        if not mt5.symbol_select(mt5_symbol, True):
            raise MT5CandleDataError(
                f"Unable to select MT5 symbol {mt5_symbol}: "
                f"{mt5.last_error()}"
            )

        rates = mt5.copy_rates_from_pos(
            mt5_symbol,
            TIMEFRAME_MAP[normalized_timeframe],
            0,
            limit,
        )

        if rates is None:
            raise MT5CandleDataError(
                f"Unable to retrieve candles for {mt5_symbol}: "
                f"{mt5.last_error()}"
            )

        if len(rates) == 0:
            raise MT5CandleDataError(
                f"MT5 returned no candles for {mt5_symbol}"
            )

        timeframe_delta = timedelta(
            minutes=TIMEFRAME_MINUTES[normalized_timeframe]
        )

        candles: list[dict[str, Any]] = []

        for rate in rates:
            open_time = datetime.fromtimestamp(
                int(rate["time"]),
                tz=timezone.utc,
            )

            close_time = open_time + timeframe_delta

            candles.append(
                {
                    "symbol": normalized_symbol,
                    "mt5_symbol": mt5_symbol,
                    "timeframe": normalized_timeframe,
                    "open_time": open_time,
                    "close_time": close_time,
                    "open": Decimal(str(rate["open"])),
                    "high": Decimal(str(rate["high"])),
                    "low": Decimal(str(rate["low"])),
                    "close": Decimal(str(rate["close"])),
                    "volume": Decimal(str(rate["tick_volume"])),
                    "spread": int(rate["spread"]),
                    "real_volume": Decimal(
                        str(rate["real_volume"])
                    ),
                    "source": "MetaTrader 5",
                }
            )

        return candles


mt5_candle_service = MT5CandleService()