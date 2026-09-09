from typing import Any

from app.market_data_mt5.candle_adapter import (
    mt5_candles_to_models,
)
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.services.liquidity_service import (
    detect_liquidity_sweeps,
    serialize_liquidity_sweeps,
)


class MT5LiquidityError(RuntimeError):
    """Raised when MT5 liquidity analysis cannot be completed."""


class MT5LiquidityService:
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
            raise MT5LiquidityError(
                "Trading symbol cannot be empty"
            )

        if strength < 1:
            raise MT5LiquidityError(
                "Liquidity sweep strength must be at least 1"
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
            raise MT5LiquidityError(
                str(exc)
            ) from exc

        minimum_candles = (strength * 2) + 3

        if len(candles) < minimum_candles:
            raise MT5LiquidityError(
                "Insufficient candle data for liquidity sweep analysis. "
                f"At least {minimum_candles} candles are required."
            )

        liquidity_sweeps = detect_liquidity_sweeps(
            candles=candles,
            strength=strength,
        )

        serialized_sweeps = serialize_liquidity_sweeps(
            liquidity_sweeps
        )

        bullish_sweeps = [
            sweep
            for sweep in serialized_sweeps
            if sweep["direction"] == "bullish"
        ]

        bearish_sweeps = [
            sweep
            for sweep in serialized_sweeps
            if sweep["direction"] == "bearish"
        ]

        return {
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "mt5_symbol": mt5_candles[0]["mt5_symbol"],
            "candle_count": len(candles),

            "liquidity_sweeps": serialized_sweeps,

            "summary": {
                "total": len(serialized_sweeps),
                "bullish": len(bullish_sweeps),
                "bearish": len(bearish_sweeps),
            },

            "source": "MetaTrader 5",
        }


mt5_liquidity_service = MT5LiquidityService()