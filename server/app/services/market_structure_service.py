from dataclasses import dataclass
from decimal import Decimal

from app.models.candle import Candle


@dataclass
class SwingPoint:
    index: int
    price: Decimal
    time: object
    type: str


@dataclass
class StructureEvent:
    type: str
    direction: str
    price: Decimal
    time: object
    broken_swing_price: Decimal


def detect_swing_high(candles: list[Candle], index: int, strength: int = 2) -> bool:
    if index < strength or index + strength >= len(candles):
        return False

    current = candles[index]

    for offset in range(1, strength + 1):
        if current.high <= candles[index - offset].high:
            return False
        if current.high <= candles[index + offset].high:
            return False

    return True


def detect_swing_low(candles: list[Candle], index: int, strength: int = 2) -> bool:
    if index < strength or index + strength >= len(candles):
        return False

    current = candles[index]

    for offset in range(1, strength + 1):
        if current.low >= candles[index - offset].low:
            return False
        if current.low >= candles[index + offset].low:
            return False

    return True


def find_swing_points(
    candles: list[Candle],
    strength: int = 2,
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    swing_highs: list[SwingPoint] = []
    swing_lows: list[SwingPoint] = []

    for index in range(len(candles)):
        candle = candles[index]

        if detect_swing_high(candles, index, strength):
            swing_highs.append(
                SwingPoint(
                    index=index,
                    price=candle.high,
                    time=candle.open_time,
                    type="swing_high",
                )
            )

        if detect_swing_low(candles, index, strength):
            swing_lows.append(
                SwingPoint(
                    index=index,
                    price=candle.low,
                    time=candle.open_time,
                    type="swing_low",
                )
            )

    return swing_highs, swing_lows


def determine_market_structure(
    candles: list[Candle],
    strength: int = 2,
) -> dict:
    if len(candles) < (strength * 2) + 3:
        return {
            "trend": "neutral",
            "structure": "insufficient_data",
            "swing_highs": [],
            "swing_lows": [],
            "events": [],
        }

    swing_highs, swing_lows = find_swing_points(
        candles=candles,
        strength=strength,
    )

    events: list[StructureEvent] = []

    last_broken_high: Decimal | None = None
    last_broken_low: Decimal | None = None

    previous_trend = "neutral"

    for candle in candles:
        current_close = candle.close

        available_highs = [
            swing
            for swing in swing_highs
            if swing.time < candle.open_time
        ]

        available_lows = [
            swing
            for swing in swing_lows
            if swing.time < candle.open_time
        ]

        if available_highs:
            latest_high = available_highs[-1]

            if (
                current_close > latest_high.price
                and (
                    last_broken_high is None
                    or latest_high.price != last_broken_high
                )
            ):
                direction = "bullish"

                event_type = (
                    "BOS"
                    if previous_trend in {"bullish", "neutral"}
                    else "CHoCH"
                )

                events.append(
                    StructureEvent(
                        type=event_type,
                        direction=direction,
                        price=current_close,
                        time=candle.close_time,
                        broken_swing_price=latest_high.price,
                    )
                )

                last_broken_high = latest_high.price
                previous_trend = "bullish"

        if available_lows:
            latest_low = available_lows[-1]

            if (
                current_close < latest_low.price
                and (
                    last_broken_low is None
                    or latest_low.price != last_broken_low
                )
            ):
                direction = "bearish"

                event_type = (
                    "BOS"
                    if previous_trend in {"bearish", "neutral"}
                    else "CHoCH"
                )

                events.append(
                    StructureEvent(
                        type=event_type,
                        direction=direction,
                        price=current_close,
                        time=candle.close_time,
                        broken_swing_price=latest_low.price,
                    )
                )

                last_broken_low = latest_low.price
                previous_trend = "bearish"

    if previous_trend == "bullish":
        structure = "higher_highs_higher_lows"
    elif previous_trend == "bearish":
        structure = "lower_highs_lower_lows"
    else:
        structure = "range"

    return {
        "trend": previous_trend,
        "structure": structure,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "events": events,
    }


def serialize_swing_points(points: list[SwingPoint]) -> list[dict]:
    return [
        {
            "index": point.index,
            "price": point.price,
            "time": point.time,
            "type": point.type,
        }
        for point in points
    ]


def serialize_events(events: list[StructureEvent]) -> list[dict]:
    return [
        {
            "type": event.type,
            "direction": event.direction,
            "price": event.price,
            "time": event.time,
            "broken_swing_price": event.broken_swing_price,
        }
        for event in events
    ]