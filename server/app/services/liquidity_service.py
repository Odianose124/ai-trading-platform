from dataclasses import dataclass
from decimal import Decimal

from app.models.candle import Candle
from app.services.market_structure_service import find_swing_points


@dataclass
class LiquiditySweep:
    type: str
    direction: str
    liquidity_level: Decimal
    sweep_price: Decimal
    close_price: Decimal
    time: object
    swing_time: object


def detect_liquidity_sweeps(
    candles: list[Candle],
    strength: int = 2,
) -> list[LiquiditySweep]:
    if len(candles) < (strength * 2) + 3:
        return []

    swing_highs, swing_lows = find_swing_points(
        candles=candles,
        strength=strength,
    )

    sweeps: list[LiquiditySweep] = []

    for candle in candles:
        previous_highs = [
            swing
            for swing in swing_highs
            if swing.time < candle.open_time
        ]

        previous_lows = [
            swing
            for swing in swing_lows
            if swing.time < candle.open_time
        ]

        # Buy-side liquidity sweep:
        # Price trades above a previous swing high
        # but closes back below that level.
        if previous_highs:
            latest_high = previous_highs[-1]

            if (
                candle.high > latest_high.price
                and candle.close < latest_high.price
            ):
                sweeps.append(
                    LiquiditySweep(
                        type="buy_side_liquidity_sweep",
                        direction="bearish",
                        liquidity_level=latest_high.price,
                        sweep_price=candle.high,
                        close_price=candle.close,
                        time=candle.close_time,
                        swing_time=latest_high.time,
                    )
                )

        # Sell-side liquidity sweep:
        # Price trades below a previous swing low
        # but closes back above that level.
        if previous_lows:
            latest_low = previous_lows[-1]

            if (
                candle.low < latest_low.price
                and candle.close > latest_low.price
            ):
                sweeps.append(
                    LiquiditySweep(
                        type="sell_side_liquidity_sweep",
                        direction="bullish",
                        liquidity_level=latest_low.price,
                        sweep_price=candle.low,
                        close_price=candle.close,
                        time=candle.close_time,
                        swing_time=latest_low.time,
                    )
                )

    return sweeps


def serialize_liquidity_sweeps(
    sweeps: list[LiquiditySweep],
) -> list[dict]:
    return [
        {
            "type": sweep.type,
            "direction": sweep.direction,
            "liquidity_level": sweep.liquidity_level,
            "sweep_price": sweep.sweep_price,
            "close_price": sweep.close_price,
            "time": sweep.time,
            "swing_time": sweep.swing_time,
        }
        for sweep in sweeps
    ]