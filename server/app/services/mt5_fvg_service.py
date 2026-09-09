from typing import Any

from app.market_data_mt5.candle_adapter import (
    mt5_candles_to_models,
)
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.services.fvg_service import (
    detect_fair_value_gaps,
    serialize_fair_value_gaps,
)


class MT5FVGError(RuntimeError):
    """Raised when MT5 FVG analysis cannot be completed."""


class MT5FVGService:
    def analyze(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> dict[str, Any]:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise MT5FVGError(
                "Trading symbol cannot be empty"
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
            raise MT5FVGError(
                str(exc)
            ) from exc

        if len(candles) < 3:
            raise MT5FVGError(
                "Insufficient candle data for FVG analysis. "
                "At least 3 candles are required."
            )

        fair_value_gaps = detect_fair_value_gaps(
            candles=candles
        )

        serialized_gaps = serialize_fair_value_gaps(
            fair_value_gaps
        )

        bullish_gaps = [
            gap
            for gap in serialized_gaps
            if gap["direction"] == "bullish"
        ]

        bearish_gaps = [
            gap
            for gap in serialized_gaps
            if gap["direction"] == "bearish"
        ]

        active_gaps = [
            gap
            for gap in serialized_gaps
            if not gap["mitigated"]
        ]

        mitigated_gaps = [
            gap
            for gap in serialized_gaps
            if gap["mitigated"]
        ]

        return {
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "mt5_symbol": mt5_candles[0]["mt5_symbol"],
            "candle_count": len(candles),

            "fvg": serialized_gaps,

            "summary": {
                "total": len(serialized_gaps),
                "bullish": len(bullish_gaps),
                "bearish": len(bearish_gaps),
                "active": len(active_gaps),
                "mitigated": len(mitigated_gaps),
            },

            "active_fvg": active_gaps,

            "source": "MetaTrader 5",
        }


mt5_fvg_service = MT5FVGService()