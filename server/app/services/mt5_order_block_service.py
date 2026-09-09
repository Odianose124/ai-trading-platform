from typing import Any

from app.market_data_mt5.candle_adapter import (
    mt5_candles_to_models,
)
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.services.order_block_service import (
    detect_order_blocks,
    serialize_order_blocks,
)


class MT5OrderBlockError(RuntimeError):
    """Raised when MT5 order-block analysis cannot be completed."""


class MT5OrderBlockService:
    def analyze(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        lookback: int = 20,
    ) -> dict[str, Any]:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise MT5OrderBlockError(
                "Trading symbol cannot be empty"
            )

        if lookback < 1:
            raise MT5OrderBlockError(
                "Order block lookback must be at least 1"
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
            raise MT5OrderBlockError(
                str(exc)
            ) from exc

        if len(candles) < 5:
            raise MT5OrderBlockError(
                "Insufficient candle data for order block analysis. "
                "At least 5 candles are required."
            )

        order_blocks = detect_order_blocks(
            candles=candles,
            lookback=lookback,
        )

        serialized_blocks = serialize_order_blocks(
            order_blocks
        )

        bullish_blocks = [
            block
            for block in serialized_blocks
            if block["direction"] == "bullish"
        ]

        bearish_blocks = [
            block
            for block in serialized_blocks
            if block["direction"] == "bearish"
        ]

        active_blocks = [
            block
            for block in serialized_blocks
            if not block["mitigated"]
        ]

        mitigated_blocks = [
            block
            for block in serialized_blocks
            if block["mitigated"]
        ]

        return {
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "mt5_symbol": mt5_candles[0]["mt5_symbol"],
            "candle_count": len(candles),

            "order_blocks": serialized_blocks,

            "summary": {
                "total": len(serialized_blocks),
                "bullish": len(bullish_blocks),
                "bearish": len(bearish_blocks),
                "active": len(active_blocks),
                "mitigated": len(mitigated_blocks),
            },

            "active_order_blocks": active_blocks,

            "source": "MetaTrader 5",
        }


mt5_order_block_service = MT5OrderBlockService()