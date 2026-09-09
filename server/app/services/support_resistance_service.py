from dataclasses import dataclass
from decimal import Decimal

from app.models.candle import Candle


@dataclass
class PriceLevel:
    price: Decimal
    type: str
    touches: int
    strength: float
    first_seen: object
    last_seen: object
    distance_from_current: Decimal
    broken: bool


def _price_tolerance(candles: list[Candle]) -> Decimal:
    if not candles:
        return Decimal("0")

    ranges = [
        candle.high - candle.low
        for candle in candles
        if candle.high >= candle.low
    ]

    if not ranges:
        return Decimal("0")

    average_range = sum(ranges, Decimal("0")) / Decimal(len(ranges))

    # A level is considered the same level when reactions
    # occur within approximately 20% of the average candle range.
    return average_range * Decimal("0.20")


def _cluster_levels(
    prices: list[tuple[Decimal, object]],
    tolerance: Decimal,
) -> list[dict]:
    if not prices:
        return []

    sorted_prices = sorted(prices, key=lambda item: item[0])

    clusters: list[dict] = []

    for price, timestamp in sorted_prices:
        matched_cluster = None

        for cluster in clusters:
            if abs(price - cluster["price"]) <= tolerance:
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append(
                {
                    "price": price,
                    "prices": [price],
                    "timestamps": [timestamp],
                }
            )
        else:
            matched_cluster["prices"].append(price)
            matched_cluster["timestamps"].append(timestamp)

            matched_cluster["price"] = (
                sum(matched_cluster["prices"], Decimal("0"))
                / Decimal(len(matched_cluster["prices"]))
            )

    return clusters


def detect_support_resistance(
    candles: list[Candle],
    current_price: Decimal | None = None,
    minimum_touches: int = 2,
) -> list[PriceLevel]:
    if len(candles) < 5:
        return []

    if current_price is None:
        current_price = candles[-1].close

    tolerance = _price_tolerance(candles)

    if tolerance <= 0:
        return []

    support_prices: list[tuple[Decimal, object]] = []
    resistance_prices: list[tuple[Decimal, object]] = []

    # Detect local lows and highs as potential reaction levels.
    for index in range(2, len(candles) - 2):
        current = candles[index]

        surrounding_lows = [
            candles[index - 2].low,
            candles[index - 1].low,
            candles[index + 1].low,
            candles[index + 2].low,
        ]

        surrounding_highs = [
            candles[index - 2].high,
            candles[index - 1].high,
            candles[index + 1].high,
            candles[index + 2].high,
        ]

        if current.low <= min(surrounding_lows):
            support_prices.append(
                (current.low, current.open_time)
            )

        if current.high >= max(surrounding_highs):
            resistance_prices.append(
                (current.high, current.open_time)
            )

    support_clusters = _cluster_levels(
        support_prices,
        tolerance,
    )

    resistance_clusters = _cluster_levels(
        resistance_prices,
        tolerance,
    )

    levels: list[PriceLevel] = []

    for cluster in support_clusters:
        touches = len(cluster["prices"])

        if touches < minimum_touches:
            continue

        price = cluster["price"]

        broken = any(
            candle.close < price - tolerance
            for candle in candles
            if candle.open_time > cluster["timestamps"][0]
        )

        distance = current_price - price

        strength = min(
            100.0,
            touches * 20.0
        )

        levels.append(
            PriceLevel(
                price=price,
                type="support",
                touches=touches,
                strength=strength,
                first_seen=min(cluster["timestamps"]),
                last_seen=max(cluster["timestamps"]),
                distance_from_current=distance,
                broken=broken,
            )
        )

    for cluster in resistance_clusters:
        touches = len(cluster["prices"])

        if touches < minimum_touches:
            continue

        price = cluster["price"]

        broken = any(
            candle.close > price + tolerance
            for candle in candles
            if candle.open_time > cluster["timestamps"][0]
        )

        distance = price - current_price

        strength = min(
            100.0,
            touches * 20.0
        )

        levels.append(
            PriceLevel(
                price=price,
                type="resistance",
                touches=touches,
                strength=strength,
                first_seen=min(cluster["timestamps"]),
                last_seen=max(cluster["timestamps"]),
                distance_from_current=distance,
                broken=broken,
            )
        )

    levels.sort(
        key=lambda level: (
            level.broken,
            abs(level.distance_from_current),
        )
    )

    return levels


def get_nearest_support(
    levels: list[PriceLevel],
    current_price: Decimal,
) -> PriceLevel | None:
    supports = [
        level
        for level in levels
        if level.type == "support"
        and not level.broken
        and level.price <= current_price
    ]

    if not supports:
        return None

    return min(
        supports,
        key=lambda level: current_price - level.price,
    )


def get_nearest_resistance(
    levels: list[PriceLevel],
    current_price: Decimal,
) -> PriceLevel | None:
    resistances = [
        level
        for level in levels
        if level.type == "resistance"
        and not level.broken
        and level.price >= current_price
    ]

    if not resistances:
        return None

    return min(
        resistances,
        key=lambda level: level.price - current_price,
    )


def serialize_levels(
    levels: list[PriceLevel],
) -> list[dict]:
    return [
        {
            "price": level.price,
            "type": level.type,
            "touches": level.touches,
            "strength": level.strength,
            "first_seen": level.first_seen,
            "last_seen": level.last_seen,
            "distance_from_current": level.distance_from_current,
            "broken": level.broken,
        }
        for level in levels
    ]