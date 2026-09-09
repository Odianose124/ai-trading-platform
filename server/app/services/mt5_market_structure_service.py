from typing import Any

from app.market_data_mt5.candle_adapter import (
    mt5_candles_to_models,
)
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.services.market_structure_service import (
    determine_market_structure,
    find_swing_points,
    serialize_events,
    serialize_swing_points,
)


class MT5MarketStructureError(RuntimeError):
    """Raised when MT5 market structure analysis cannot be completed."""


class MT5MarketStructureService:
    def analyze(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        strength: int = 2,
    ) -> dict[str, Any]:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise MT5MarketStructureError(
                "Trading symbol cannot be empty"
            )

        if strength < 1:
            raise MT5MarketStructureError(
                "Swing strength must be at least 1"
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
            raise MT5MarketStructureError(
                str(exc)
            ) from exc

        minimum_candles = (strength * 2) + 3

        if len(candles) < minimum_candles:
            raise MT5MarketStructureError(
                "Insufficient candle data for market structure analysis. "
                f"At least {minimum_candles} candles are required."
            )

        # find_swing_points() returns:
        #
        # (
        #     swing_highs,
        #     swing_lows
        # )
        #
        # These must be unpacked before serialization.
        swing_highs, swing_lows = find_swing_points(
            candles=candles,
            strength=strength,
        )

        structure_result = determine_market_structure(
            candles=candles,
            strength=strength,
        )

        return {
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "mt5_symbol": mt5_candles[0]["mt5_symbol"],
            "candle_count": len(candles),

            "swing_points": {
                "highs": serialize_swing_points(
                    swing_highs
                ),
                "lows": serialize_swing_points(
                    swing_lows
                ),
            },

            "structure": serialize_events(
                structure_result.get(
                    "events",
                    [],
                )
            ),

            "trend": structure_result.get(
                "trend"
            ),

            "market_structure": structure_result.get(
                "structure"
            ),

            "source": "MetaTrader 5",
        }


mt5_market_structure_service = MT5MarketStructureService()