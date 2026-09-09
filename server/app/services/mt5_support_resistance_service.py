from typing import Any

from app.market_data_mt5.candle_adapter import (
    mt5_candles_to_models,
)
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.services.support_resistance_service import (
    detect_support_resistance,
    get_nearest_resistance,
    get_nearest_support,
    serialize_levels,
)


class MT5SupportResistanceError(RuntimeError):
    """Raised when MT5 support and resistance analysis cannot be completed."""


class MT5SupportResistanceService:
    def analyze(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        minimum_touches: int = 2,
    ) -> dict[str, Any]:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise MT5SupportResistanceError(
                "Trading symbol cannot be empty"
            )

        if minimum_touches < 1:
            raise MT5SupportResistanceError(
                "Minimum touches must be at least 1"
            )

        try:
            mt5_candles = mt5_candle_service.get_candles(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                limit=limit,
            )

            candles = mt5_candles_to_models(
                mt5_candles
            )

        except MT5CandleDataError as exc:
            raise MT5SupportResistanceError(
                str(exc)
            ) from exc

        if len(candles) < 5:
            raise MT5SupportResistanceError(
                "Insufficient candle data for support and resistance analysis. "
                "At least 5 candles are required."
            )

        current_price = candles[-1].close

        levels = detect_support_resistance(
            candles=candles,
            current_price=current_price,
            minimum_touches=minimum_touches,
        )

        serialized_levels = serialize_levels(
            levels
        )

        support_levels = [
            level
            for level in serialized_levels
            if level["type"] == "support"
        ]

        resistance_levels = [
            level
            for level in serialized_levels
            if level["type"] == "resistance"
        ]

        active_support_levels = [
            level
            for level in support_levels
            if not level["broken"]
        ]

        active_resistance_levels = [
            level
            for level in resistance_levels
            if not level["broken"]
        ]

        nearest_support = get_nearest_support(
            levels=levels,
            current_price=current_price,
        )

        nearest_resistance = get_nearest_resistance(
            levels=levels,
            current_price=current_price,
        )

        return {
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "mt5_symbol": mt5_candles[0]["mt5_symbol"],
            "candle_count": len(candles),
            "current_price": current_price,

            "levels": serialized_levels,

            "support": support_levels,
            "resistance": resistance_levels,

            "active_support": active_support_levels,
            "active_resistance": active_resistance_levels,

            "nearest_support": (
                serialize_levels([nearest_support])[0]
                if nearest_support is not None
                else None
            ),

            "nearest_resistance": (
                serialize_levels([nearest_resistance])[0]
                if nearest_resistance is not None
                else None
            ),

            "summary": {
                "total": len(serialized_levels),
                "support": len(support_levels),
                "resistance": len(resistance_levels),
                "active_support": len(active_support_levels),
                "active_resistance": len(active_resistance_levels),
                "broken": len(
                    [
                        level
                        for level in serialized_levels
                        if level["broken"]
                    ]
                ),
            },

            "source": "MetaTrader 5",
        }


mt5_support_resistance_service = MT5SupportResistanceService()