from datetime import datetime
from decimal import Decimal

from app.models.candle import Candle


class MT5CandleAdapterError(RuntimeError):
    """Raised when MT5 candle data cannot be converted."""


def mt5_candle_to_model(candle_data: dict) -> Candle:
    required_fields = {
        "symbol",
        "timeframe",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing_fields = required_fields - candle_data.keys()

    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise MT5CandleAdapterError(
            f"MT5 candle is missing required fields: {missing}"
        )

    try:
        open_time = candle_data["open_time"]
        close_time = candle_data["close_time"]

        if not isinstance(open_time, datetime):
            raise ValueError("open_time must be a datetime")

        if not isinstance(close_time, datetime):
            raise ValueError("close_time must be a datetime")

        return Candle(
            symbol=str(candle_data["symbol"]).strip().upper(),
            timeframe=str(candle_data["timeframe"]).strip().lower(),
            open_time=open_time,
            close_time=close_time,
            open=Decimal(str(candle_data["open"])),
            high=Decimal(str(candle_data["high"])),
            low=Decimal(str(candle_data["low"])),
            close=Decimal(str(candle_data["close"])),
            volume=Decimal(str(candle_data["volume"])),
        )

    except (KeyError, TypeError, ValueError) as exc:
        raise MT5CandleAdapterError(
            f"Unable to convert MT5 candle to Candle model: {exc}"
        ) from exc


def mt5_candles_to_models(
    candles: list[dict],
) -> list[Candle]:
    return [
        mt5_candle_to_model(candle_data)
        for candle_data in candles
    ]