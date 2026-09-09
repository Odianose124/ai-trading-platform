from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.candle import Candle


TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def normalize_timeframe(timeframe: str) -> str:
    normalized = timeframe.strip().lower()

    if normalized not in TIMEFRAME_MINUTES:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}"
        )

    return normalized


def get_timeframe_open_time(
    timestamp: datetime,
    timeframe: str,
) -> datetime:

    timeframe = normalize_timeframe(timeframe)

    minutes = TIMEFRAME_MINUTES[timeframe]

    timestamp = timestamp.astimezone(timezone.utc)

    total_minutes = (
        timestamp.hour * 60
        + timestamp.minute
    )

    bucket_minutes = (
        total_minutes // minutes
    ) * minutes

    hour = bucket_minutes // 60
    minute = bucket_minutes % 60

    if timeframe == "1d":
        return timestamp.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    return timestamp.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def get_timeframe_close_time(
    open_time: datetime,
    timeframe: str,
) -> datetime:

    timeframe = normalize_timeframe(timeframe)

    minutes = TIMEFRAME_MINUTES[timeframe]

    return open_time + timedelta(
        minutes=minutes,
        microseconds=-1,
    )


def aggregate_candles(
    db: Session,
    symbol: str,
    timeframe: str,
    limit: int = 100,
) -> list[Candle]:

    normalized_symbol = symbol.strip().upper()
    timeframe = normalize_timeframe(timeframe)

    if timeframe == "1m":
        candles = (
            db.query(Candle)
            .filter(
                Candle.symbol == normalized_symbol,
                Candle.timeframe == "1m",
            )
            .order_by(
                Candle.open_time.desc()
            )
            .limit(limit)
            .all()
        )

        return list(reversed(candles))

    source_minutes = TIMEFRAME_MINUTES["1m"]
    target_minutes = TIMEFRAME_MINUTES[timeframe]

    required_1m_candles = (
        limit * target_minutes // source_minutes
    )

    source_candles = (
        db.query(Candle)
        .filter(
            Candle.symbol == normalized_symbol,
            Candle.timeframe == "1m",
        )
        .order_by(
            Candle.open_time.desc()
        )
        .limit(required_1m_candles)
        .all()
    )

    source_candles.reverse()

    if not source_candles:
        return []

    grouped: dict[datetime, list[Candle]] = {}

    for candle in source_candles:

        bucket = get_timeframe_open_time(
            candle.open_time,
            timeframe,
        )

        grouped.setdefault(
            bucket,
            [],
        ).append(candle)

    aggregated: list[Candle] = []

    for open_time, candles in sorted(
        grouped.items()
    ):

        candles.sort(
            key=lambda item: item.open_time
        )

        first = candles[0]
        last = candles[-1]

        aggregated_candle = Candle(
            symbol=normalized_symbol,
            timeframe=timeframe,
            open_time=open_time,
            close_time=get_timeframe_close_time(
                open_time,
                timeframe,
            ),
            open=first.open,
            high=max(
                candle.high
                for candle in candles
            ),
            low=min(
                candle.low
                for candle in candles
            ),
            close=last.close,
            volume=sum(
                candle.volume
                for candle in candles
            ),
            trade_count=sum(
                candle.trade_count
                for candle in candles
            ),
        )

        aggregated.append(
            aggregated_candle
        )

    return aggregated[-limit:]