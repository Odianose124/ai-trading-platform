from fastapi import APIRouter, HTTPException, Query, status

from app.mt5.connection import mt5_connection

from app.market_data_mt5.service import (
    MT5MarketDataError,
    mt5_market_data_service,
)

from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)

from app.services.mt5_market_structure_service import (
    MT5MarketStructureError,
    mt5_market_structure_service,
)

from app.services.mt5_fvg_service import (
    MT5FVGError,
    mt5_fvg_service,
)

from app.services.mt5_liquidity_service import (
    MT5LiquidityError,
    mt5_liquidity_service,
)

from app.services.mt5_order_block_service import (
    MT5OrderBlockError,
    mt5_order_block_service,
)

from app.services.mt5_support_resistance_service import (
    MT5SupportResistanceError,
    mt5_support_resistance_service,
)

from app.services.mt5_ai_market_analysis_service import (
    MT5AIMarketAnalysisError,
    mt5_ai_market_analysis_service,
)


router = APIRouter(
    prefix="/api/mt5/market-data",
    tags=["MT5 Market Data"],
)


def ensure_mt5_connection() -> None:
    """
    Ensure the MT5 terminal is connected before
    attempting any MT5 market-data operation.
    """

    if not mt5_connection.is_connected():

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )


@router.get("/tick/{symbol}")
def get_mt5_tick(
    symbol: str,
):
    """
    Return the current MT5 bid/ask tick for a symbol.
    """

    ensure_mt5_connection()

    try:

        return mt5_market_data_service.get_tick(
            symbol
        )

    except MT5MarketDataError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/symbol/{symbol}")
def get_mt5_symbol_info(
    symbol: str,
):
    """
    Return broker-specific MT5 symbol information.
    """

    ensure_mt5_connection()

    try:

        return mt5_market_data_service.get_symbol_info(
            symbol
        )

    except MT5MarketDataError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/ticks")
def get_mt5_ticks():
    """
    Return live MT5 ticks for the primary supported symbols.
    """

    ensure_mt5_connection()

    symbols = [
        "XAUUSD",
        "BTCUSD",
        "EURUSD",
    ]

    results = {}

    for symbol in symbols:

        try:

            results[symbol] = (
                mt5_market_data_service.get_tick(
                    symbol
                )
            )

        except MT5MarketDataError as exc:

            results[symbol] = {
                "symbol": symbol,
                "error": str(exc),
            }

    return {
        "source": "MetaTrader 5",
        "prices": results,
    }


@router.get(
    "/candles/{symbol}/{timeframe}"
)
def get_mt5_candles(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
):
    """
    Return historical MT5 candles.
    """

    ensure_mt5_connection()

    try:

        candles = (
            mt5_candle_service.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        )

        return {
            "symbol": symbol.strip().upper(),
            "timeframe": timeframe.strip().lower(),
            "count": len(candles),
            "candles": candles,
            "source": "MetaTrader 5",
        }

    except MT5CandleDataError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/structure/{symbol}/{timeframe}"
)
def get_mt5_market_structure(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
    strength: int = Query(
        default=2,
        ge=1,
        le=20,
    ),
):
    """
    Analyze MT5 market structure including swing
    highs, swing lows, BOS and CHoCH events.
    """

    ensure_mt5_connection()

    try:

        return (
            mt5_market_structure_service.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                strength=strength,
            )
        )

    except MT5MarketStructureError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/fvg/{symbol}/{timeframe}"
)
def get_mt5_fvg(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
):
    """
    Analyze fair value gaps from live MT5 candle data.
    """

    ensure_mt5_connection()

    try:

        return mt5_fvg_service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

    except MT5FVGError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/liquidity/{symbol}/{timeframe}"
)
def get_mt5_liquidity(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
    strength: int = Query(
        default=2,
        ge=1,
        le=20,
    ),
):
    """
    Detect liquidity sweeps using MT5 candle data.
    """

    ensure_mt5_connection()

    try:

        return mt5_liquidity_service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            strength=strength,
        )

    except MT5LiquidityError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/order-blocks/{symbol}/{timeframe}"
)
def get_mt5_order_blocks(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
    lookback: int = Query(
        default=20,
        ge=1,
        le=500,
    ),
):
    """
    Detect active and mitigated order blocks from
    MT5 market data.
    """

    ensure_mt5_connection()

    try:

        return mt5_order_block_service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            lookback=lookback,
        )

    except MT5OrderBlockError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/support-resistance/{symbol}/{timeframe}"
)
def get_mt5_support_resistance(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
    minimum_touches: int = Query(
        default=2,
        ge=1,
        le=20,
    ),
):
    """
    Detect support and resistance levels from
    MT5 market data.
    """

    ensure_mt5_connection()

    try:

        return (
            mt5_support_resistance_service.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                minimum_touches=minimum_touches,
            )
        )

    except MT5SupportResistanceError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/analysis/ai/{symbol}/{timeframe}"
)
def get_mt5_ai_market_analysis(
    symbol: str,
    timeframe: str,
    limit: int = Query(
        default=500,
        ge=5,
        le=5000,
    ),
    strength: int = Query(
        default=2,
        ge=1,
        le=20,
    ),
    lookback: int = Query(
        default=20,
        ge=1,
        le=500,
    ),
    minimum_touches: int = Query(
        default=2,
        ge=1,
        le=20,
    ),
):
    """
    Run the complete MT5 AI market-analysis engine.

    Analysis chain:

    MT5 live price
        ↓
    MT5 candles
        ↓
    Market structure
        ↓
    Fair Value Gaps
        ↓
    Liquidity sweeps
        ↓
    Order blocks
        ↓
    Support / resistance
        ↓
    Weighted AI analysis
        ↓
    Final market bias and confidence
    """

    ensure_mt5_connection()

    try:

        analysis = (
            mt5_ai_market_analysis_service.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )
        )

        return (
            mt5_ai_market_analysis_service.serialize(
                analysis
            )
        )

    except MT5AIMarketAnalysisError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )