from datetime import datetime, timezone
from decimal import Decimal

from app.market_data_mt5.candle_adapter import (
    mt5_candle_to_model,
    mt5_candles_to_models,
)


def test_mt5_candle_to_model():
    candle_data = {
        "symbol": "XAUUSD",
        "mt5_symbol": "XAUUSDm",
        "timeframe": "15m",
        "open_time": datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc),
        "close_time": datetime(2026, 9, 3, 14, 15, tzinfo=timezone.utc),
        "open": Decimal("4500.100"),
        "high": Decimal("4502.500"),
        "low": Decimal("4498.900"),
        "close": Decimal("4501.800"),
        "volume": Decimal("2500"),
        "spread": 260,
        "real_volume": Decimal("0"),
        "source": "MetaTrader 5",
    }

    candle = mt5_candle_to_model(candle_data)

    assert candle.symbol == "XAUUSD"
    assert candle.timeframe == "15m"
    assert candle.open == Decimal("4500.100")
    assert candle.high == Decimal("4502.500")
    assert candle.low == Decimal("4498.900")
    assert candle.close == Decimal("4501.800")
    assert candle.volume == Decimal("2500")


def test_mt5_candles_to_models():
    candle_data = {
        "symbol": "EURUSD",
        "mt5_symbol": "EURUSDm",
        "timeframe": "15m",
        "open_time": datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc),
        "close_time": datetime(2026, 9, 3, 14, 15, tzinfo=timezone.utc),
        "open": Decimal("1.16200"),
        "high": Decimal("1.16280"),
        "low": Decimal("1.16170"),
        "close": Decimal("1.16250"),
        "volume": Decimal("1800"),
        "spread": 8,
        "real_volume": Decimal("0"),
        "source": "MetaTrader 5",
    }

    candles = mt5_candles_to_models(
        [candle_data, candle_data]
    )

    assert len(candles) == 2
    assert candles[0].symbol == "EURUSD"
    assert candles[1].symbol == "EURUSD"