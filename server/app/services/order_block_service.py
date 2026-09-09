from dataclasses import dataclass
from decimal import Decimal

from app.models.candle import Candle


@dataclass
class OrderBlock:
    type: str
    direction: str
    lower_price: Decimal
    upper_price: Decimal
    open_price: Decimal
    close_price: Decimal
    created_time: object
    created_candle_index: int
    mitigated: bool
    mitigation_time: object | None
    mitigation_price: Decimal | None


def is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def detect_order_blocks(
    candles: list[Candle],
    lookback: int = 20,
) -> list[OrderBlock]:
    if len(candles) < 5:
        return []

    order_blocks: list[OrderBlock] = []

    for index in range(2, len(candles) - 1):
        current = candles[index]
        next_candle = candles[index + 1]

        # ---------------------------------------------------------
        # Bullish Order Block
        #
        # A bearish candle followed by a strong bullish displacement
        # that closes above the bearish candle's high.
        # ---------------------------------------------------------
        if is_bearish(current) and is_bullish(next_candle):
            displacement = next_candle.close - current.open

            if displacement > (current.high - current.low):
                lower_price = current.low
                upper_price = current.high

                mitigated = False
                mitigation_time = None
                mitigation_price = None

                for future_candle in candles[index + 2:]:
                    if future_candle.low <= upper_price:
                        mitigated = True
                        mitigation_time = future_candle.close_time
                        mitigation_price = future_candle.low
                        break

                order_blocks.append(
                    OrderBlock(
                        type="bullish_order_block",
                        direction="bullish",
                        lower_price=lower_price,
                        upper_price=upper_price,
                        open_price=current.open,
                        close_price=current.close,
                        created_time=current.close_time,
                        created_candle_index=index,
                        mitigated=mitigated,
                        mitigation_time=mitigation_time,
                        mitigation_price=mitigation_price,
                    )
                )

        # ---------------------------------------------------------
        # Bearish Order Block
        #
        # A bullish candle followed by a strong bearish displacement
        # that closes below the bullish candle's low.
        # ---------------------------------------------------------
        if is_bullish(current) and is_bearish(next_candle):
            displacement = current.open - next_candle.close

            if displacement > (current.high - current.low):
                lower_price = current.low
                upper_price = current.high

                mitigated = False
                mitigation_time = None
                mitigation_price = None

                for future_candle in candles[index + 2:]:
                    if future_candle.high >= lower_price:
                        mitigated = True
                        mitigation_time = future_candle.close_time
                        mitigation_price = future_candle.high
                        break

                order_blocks.append(
                    OrderBlock(
                        type="bearish_order_block",
                        direction="bearish",
                        lower_price=lower_price,
                        upper_price=upper_price,
                        open_price=current.open,
                        close_price=current.close,
                        created_time=current.close_time,
                        created_candle_index=index,
                        mitigated=mitigated,
                        mitigation_time=mitigation_time,
                        mitigation_price=mitigation_price,
                    )
                )

    return order_blocks


def serialize_order_blocks(
    order_blocks: list[OrderBlock],
) -> list[dict]:
    return [
        {
            "type": block.type,
            "direction": block.direction,
            "lower_price": block.lower_price,
            "upper_price": block.upper_price,
            "open_price": block.open_price,
            "close_price": block.close_price,
            "created_time": block.created_time,
            "created_candle_index": block.created_candle_index,
            "mitigated": block.mitigated,
            "mitigation_time": block.mitigation_time,
            "mitigation_price": block.mitigation_price,
        }
        for block in order_blocks
    ]