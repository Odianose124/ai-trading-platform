from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models.candle import Candle

logger = logging.getLogger(__name__)


BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"

SYMBOL_MAPPING = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "BNBUSD": "BNBUSDT",
    "SOLUSD": "SOLUSDT",
    "XRPUSD": "XRPUSDT",
}

BINANCE_INTERVAL = "1m"
BINANCE_MAX_LIMIT = 1000


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()

    if normalized not in SYMBOL_MAPPING:
        raise ValueError(
            f"Unsupported historical-data symbol: {normalized}. "
            f"Supported symbols: {', '.join(SYMBOL_MAPPING.keys())}"
        )

    return normalized


def timestamp_to_datetime(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    )


async def fetch_binance_klines(
    client: httpx.AsyncClient,
    binance_symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = BINANCE_MAX_LIMIT,
) -> list[list]:
    params = {
        "symbol": binance_symbol,
        "interval": BINANCE_INTERVAL,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": min(limit, BINANCE_MAX_LIMIT),
    }

    response = await client.get(
        BINANCE_KLINES_URL,
        params=params,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected Binance kline response for {binance_symbol}"
        )

    return data


def save_historical_klines(
    db: Session,
    symbol: str,
    klines: list[list],
) -> int:
    normalized_symbol = normalize_symbol(symbol)

    inserted_or_updated = 0

    for kline in klines:
        if len(kline) < 9:
            continue

        open_time_ms = int(kline[0])
        open_price = Decimal(str(kline[1]))
        high_price = Decimal(str(kline[2]))
        low_price = Decimal(str(kline[3]))
        close_price = Decimal(str(kline[4]))
        volume = Decimal(str(kline[5]))
        close_time_ms = int(kline[6])
        trade_count = int(kline[8])

        open_time = timestamp_to_datetime(open_time_ms)
        close_time = timestamp_to_datetime(close_time_ms)

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
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                trade_count=trade_count,
            )

            db.add(candle)

        else:
            candle.close_time = close_time
            candle.open = open_price
            candle.high = high_price
            candle.low = low_price
            candle.close = close_price
            candle.volume = volume
            candle.trade_count = trade_count

        inserted_or_updated += 1

    db.commit()

    return inserted_or_updated


async def backfill_symbol(
    db: Session,
    symbol: str,
    hours: int = 72,
) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    binance_symbol = SYMBOL_MAPPING[normalized_symbol]

    if hours < 1:
        raise ValueError("Hours must be at least 1")

    if hours > 168:
        raise ValueError("Hours cannot exceed 168")

    end_time = datetime.now(timezone.utc)

    start_time = end_time - timedelta(hours=hours)

    current_start_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    total_saved = 0
    request_count = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0)
    ) as client:

        while current_start_ms < end_time_ms:
            request_count += 1

            klines = await fetch_binance_klines(
                client=client,
                binance_symbol=binance_symbol,
                start_time_ms=current_start_ms,
                end_time_ms=end_time_ms,
                limit=BINANCE_MAX_LIMIT,
            )

            if not klines:
                break

            saved = save_historical_klines(
                db=db,
                symbol=normalized_symbol,
                klines=klines,
            )

            total_saved += saved

            last_open_time_ms = int(klines[-1][0])

            next_start_ms = last_open_time_ms + 60_000

            if next_start_ms <= current_start_ms:
                break

            current_start_ms = next_start_ms

            if len(klines) < BINANCE_MAX_LIMIT:
                break

            await asyncio.sleep(0.15)

    first_candle = (
        db.query(Candle)
        .filter(
            Candle.symbol == normalized_symbol,
            Candle.timeframe == "1m",
        )
        .order_by(Candle.open_time.asc())
        .first()
    )

    last_candle = (
        db.query(Candle)
        .filter(
            Candle.symbol == normalized_symbol,
            Candle.timeframe == "1m",
        )
        .order_by(Candle.open_time.desc())
        .first()
    )

    logger.info(
        "Historical backfill completed: %s | requests=%s | candles=%s",
        normalized_symbol,
        request_count,
        total_saved,
    )

    return {
        "symbol": normalized_symbol,
        "binance_symbol": binance_symbol,
        "timeframe": "1m",
        "requested_hours": hours,
        "requests": request_count,
        "candles_saved": total_saved,
        "first_candle": first_candle.open_time if first_candle else None,
        "last_candle": last_candle.open_time if last_candle else None,
    }


async def backfill_symbols(
    db: Session,
    symbols: list[str],
    hours: int = 72,
) -> list[dict]:
    results = []

    for symbol in symbols:
        result = await backfill_symbol(
            db=db,
            symbol=symbol,
            hours=hours,
        )

        results.append(result)

    return results