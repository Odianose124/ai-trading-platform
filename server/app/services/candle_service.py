from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.candle import Candle


def get_candle_open_time(timestamp_ms: int) -> datetime:
    timestamp_seconds = timestamp_ms / 1000
    timestamp = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)

    return timestamp.replace(
        second=0,
        microsecond=0,
    )


def get_candle_close_time(open_time: datetime) -> datetime:
    return open_time.replace(
        second=59,
        microsecond=999999,
    )


def update_candle_from_trade(
    db: Session,
    symbol: str,
    trade_price: Decimal,
    trade_quantity: Decimal,
    trade_timestamp_ms: int,
) -> Candle:

    normalized_symbol = symbol.strip().upper()

    open_time = get_candle_open_time(trade_timestamp_ms)
    close_time = get_candle_close_time(open_time)

    candle = (
        db.query(Candle)
        .filter(
            Candle.symbol == normalized_symbol,
            Candle.timeframe == "1m",
            Candle.open_time == open_time,
        )
        .first()
    )

    if candle is None:
        candle = Candle(
            symbol=normalized_symbol,
            timeframe="1m",
            open_time=open_time,
            close_time=close_time,
            open=trade_price,
            high=trade_price,
            low=trade_price,
            close=trade_price,
            volume=trade_quantity,
            trade_count=1,
        )

        db.add(candle)

    else:
        if trade_price > candle.high:
            candle.high = trade_price

        if trade_price < candle.low:
            candle.low = trade_price

        candle.close = trade_price
        candle.volume += trade_quantity
        candle.trade_count += 1

    return candle


def save_candle(
    db: Session,
    candle: Candle,
) -> Candle:

    db.add(candle)
    db.commit()
    db.refresh(candle)

    return candle


def get_recent_candles(
    db: Session,
    symbol: str,
    timeframe: str = "1m",
    limit: int = 100,
) -> list[Candle]:

    normalized_symbol = symbol.strip().upper()

    candles = (
        db.query(Candle)
        .filter(
            Candle.symbol == normalized_symbol,
            Candle.timeframe == timeframe,
        )
        .order_by(Candle.open_time.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(candles))