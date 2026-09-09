from dataclasses import dataclass
from decimal import Decimal

from app.models.candle import Candle


@dataclass
class FairValueGap:
    type: str
    direction: str
    lower_price: Decimal
    upper_price: Decimal
    size: Decimal
    created_time: object
    created_candle_index: int
    mitigated: bool
    mitigation_time: object | None
    mitigation_price: Decimal | None


def detect_fair_value_gaps(
    candles: list[Candle],
) -> list[FairValueGap]:
    if len(candles) < 3:
        return []

    gaps: list[FairValueGap] = []

    for index in range(2, len(candles)):
        first = candles[index - 2]
        middle = candles[index - 1]
        third = candles[index]

        # Bullish FVG:
        # The current candle's low is above the high
        # of the candle two positions earlier.
        if third.low > first.high:
            lower_price = first.high
            upper_price = third.low
            size = upper_price - lower_price

            mitigation_time = None
            mitigation_price = None
            mitigated = False

            for future_candle in candles[index + 1:]:
                if future_candle.low <= lower_price:
                    mitigated = True
                    mitigation_time = future_candle.close_time
                    mitigation_price = future_candle.low
                    break

            gaps.append(
                FairValueGap(
                    type="bullish_fvg",
                    direction="bullish",
                    lower_price=lower_price,
                    upper_price=upper_price,
                    size=size,
                    created_time=middle.close_time,
                    created_candle_index=index,
                    mitigated=mitigated,
                    mitigation_time=mitigation_time,
                    mitigation_price=mitigation_price,
                )
            )

        # Bearish FVG:
        # The current candle's high is below the low
        # of the candle two positions earlier.
        if third.high < first.low:
            lower_price = third.high
            upper_price = first.low
            size = upper_price - lower_price

            mitigation_time = None
            mitigation_price = None
            mitigated = False

            for future_candle in candles[index + 1:]:
                if future_candle.high >= upper_price:
                    mitigated = True
                    mitigation_time = future_candle.close_time
                    mitigation_price = future_candle.high
                    break

            gaps.append(
                FairValueGap(
                    type="bearish_fvg",
                    direction="bearish",
                    lower_price=lower_price,
                    upper_price=upper_price,
                    size=size,
                    created_time=middle.close_time,
                    created_candle_index=index,
                    mitigated=mitigated,
                    mitigation_time=mitigation_time,
                    mitigation_price=mitigation_price,
                )
            )

    return gaps


def serialize_fair_value_gaps(
    gaps: list[FairValueGap],
) -> list[dict]:
    return [
        {
            "type": gap.type,
            "direction": gap.direction,
            "lower_price": gap.lower_price,
            "upper_price": gap.upper_price,
            "size": gap.size,
            "created_time": gap.created_time,
            "created_candle_index": gap.created_candle_index,
            "mitigated": gap.mitigated,
            "mitigation_time": gap.mitigation_time,
            "mitigation_price": gap.mitigation_price,
        }
        for gap in gaps
    ]