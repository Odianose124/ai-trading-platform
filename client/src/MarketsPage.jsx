import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import api from "./services/api";
import "./markets.css";

const SYMBOLS = ["XAUUSD", "BTCUSD", "EURUSD"];

const TIMEFRAMES = [
  { value: "1m", label: "1m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "1D" },
];

function toNumber(value) {
  const number = Number(value);

  return Number.isFinite(number) ? number : null;
}

function formatPrice(value) {
  const number = toNumber(value);

  if (number === null) {
    return "--";
  }

  if (number >= 1000) {
    return number.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  if (number >= 10) {
    return number.toLocaleString(undefined, {
      minimumFractionDigits: 3,
      maximumFractionDigits: 3,
    });
  }

  return number.toLocaleString(undefined, {
    minimumFractionDigits: 5,
    maximumFractionDigits: 5,
  });
}

function formatSpread(value) {
  const number = toNumber(value);

  if (number === null) {
    return "--";
  }

  return number.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 5,
  });
}

function formatTime(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function normalizeTick(tick, requestedSymbol = "") {
  const symbol =
    requestedSymbol ||
    tick?.requested_symbol ||
    tick?.symbol ||
    tick?.name ||
    "";

  const bid = toNumber(
    tick?.bid ??
      tick?.Bid ??
      tick?.price_bid ??
      tick?.bid_price,
  );

  const ask = toNumber(
    tick?.ask ??
      tick?.Ask ??
      tick?.price_ask ??
      tick?.ask_price,
  );

  const spread =
    toNumber(
      tick?.spread ??
        tick?.Spread ??
        tick?.price_spread,
    ) ??
    (bid !== null && ask !== null
      ? ask - bid
      : null);

  return {
    symbol,
    mt5Symbol:
      tick?.mt5_symbol ||
      tick?.broker_symbol ||
      tick?.brokerSymbol ||
      tick?.name ||
      tick?.symbol ||
      requestedSymbol ||
      "--",
    bid,
    ask,
    spread,
    timestamp:
      tick?.timestamp ||
      tick?.time ||
      tick?.updated_at ||
      tick?.datetime ||
      null,
  };
}

function extractTicks(data) {
  /*
   * Backend response:
   *
   * {
   *   source: "MetaTrader 5",
   *   prices: {
   *     XAUUSD: {...},
   *     BTCUSD: {...},
   *     EURUSD: {...}
   *   }
   * }
   *
   * The frontend therefore converts prices into:
   *
   * {
   *   XAUUSD: {...},
   *   BTCUSD: {...},
   *   EURUSD: {...}
   * }
   */

  const prices = data?.prices;

  if (
    prices &&
    typeof prices === "object" &&
    !Array.isArray(prices)
  ) {
    return Object.entries(prices).reduce(
      (result, [requestedSymbol, tick]) => {
        result[requestedSymbol] = normalizeTick(
          tick,
          requestedSymbol,
        );

        return result;
      },
      {},
    );
  }

  if (Array.isArray(data)) {
    return data.reduce((result, tick) => {
      const normalized = normalizeTick(tick);

      if (normalized.symbol) {
        result[normalized.symbol] = normalized;
      }

      return result;
    }, {});
  }

  if (Array.isArray(data?.ticks)) {
    return data.ticks.reduce(
      (result, tick) => {
        const normalized = normalizeTick(tick);

        if (normalized.symbol) {
          result[normalized.symbol] =
            normalized;
        }

        return result;
      },
      {},
    );
  }

  if (Array.isArray(data?.data)) {
    return data.data.reduce(
      (result, tick) => {
        const normalized = normalizeTick(tick);

        if (normalized.symbol) {
          result[normalized.symbol] =
            normalized;
        }

        return result;
      },
      {},
    );
  }

  return {};
}

function normalizeCandle(candle) {
  const open = toNumber(candle?.open);
  const high = toNumber(candle?.high);
  const low = toNumber(candle?.low);
  const close = toNumber(candle?.close);

  if (
    open === null ||
    high === null ||
    low === null ||
    close === null
  ) {
    return null;
  }

  return {
    time:
      candle?.open_time ||
      candle?.time ||
      candle?.timestamp ||
      null,
    open,
    high,
    low,
    close,
    volume: toNumber(
      candle?.volume ??
        candle?.tick_volume ??
        candle?.real_volume,
    ),
  };
}

function extractCandles(data) {
  const source = Array.isArray(data)
    ? data
    : Array.isArray(data?.candles)
      ? data.candles
      : Array.isArray(data?.data)
        ? data.data
        : [];

  return source
    .map(normalizeCandle)
    .filter(Boolean);
}

function CandleChart({ candles }) {
  const visibleCandles = useMemo(
    () => candles.slice(-80),
    [candles],
  );

  if (!visibleCandles.length) {
    return (
      <div className="market-chart-empty">
        <Activity size={22} />

        <span>
          Waiting for live candle data...
        </span>
      </div>
    );
  }

  const width = 1200;
  const height = 460;

  const padding = {
    top: 20,
    right: 18,
    bottom: 28,
    left: 18,
  };

  const highs = visibleCandles.map(
    (candle) => candle.high,
  );

  const lows = visibleCandles.map(
    (candle) => candle.low,
  );

  const highest = Math.max(...highs);
  const lowest = Math.min(...lows);
  const range = highest - lowest || 1;

  const chartWidth =
    width -
    padding.left -
    padding.right;

  const chartHeight =
    height -
    padding.top -
    padding.bottom;

  const slotWidth =
    chartWidth / visibleCandles.length;

  const candleWidth = Math.max(
    3,
    Math.min(12, slotWidth * 0.62),
  );

  const priceToY = (price) =>
    padding.top +
    ((highest - price) / range) *
      chartHeight;

  const getX = (index) =>
    padding.left +
    index * slotWidth +
    slotWidth / 2;

  return (
    <svg
      className="market-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Live candlestick market chart"
    >
      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={padding.top}
        y2={padding.top}
        className="chart-grid-line"
      />

      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={height / 2}
        y2={height / 2}
        className="chart-grid-line"
      />

      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={height - padding.bottom}
        y2={height - padding.bottom}
        className="chart-grid-line"
      />

      {visibleCandles.map(
        (candle, index) => {
          const x = getX(index);

          const openY = priceToY(
            candle.open,
          );

          const closeY = priceToY(
            candle.close,
          );

          const highY = priceToY(
            candle.high,
          );

          const lowY = priceToY(
            candle.low,
          );

          const bullish =
            candle.close >= candle.open;

          const bodyTop = Math.min(
            openY,
            closeY,
          );

          const bodyHeight = Math.max(
            1,
            Math.abs(openY - closeY),
          );

          return (
            <g
              key={`${candle.time}-${index}`}
            >
              <line
                x1={x}
                x2={x}
                y1={highY}
                y2={lowY}
                className={
                  bullish
                    ? "candle-wick candle-up"
                    : "candle-wick candle-down"
                }
              />

              <rect
                x={
                  x -
                  candleWidth / 2
                }
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                rx="1"
                className={
                  bullish
                    ? "candle-body candle-up"
                    : "candle-body candle-down"
                }
              />
            </g>
          );
        },
      )}
    </svg>
  );
}

function MarketTickerCard({
  symbol,
  tick,
  selected,
  onSelect,
}) {
  return (
    <button
      type="button"
      className={`market-terminal-card ${
        selected
          ? "market-terminal-card-selected"
          : ""
      }`}
      onClick={() => onSelect(symbol)}
    >
      <div className="market-terminal-card-top">
        <div>
          <strong>{symbol}</strong>

          <span>
            {tick?.mt5Symbol || "--"}
          </span>
        </div>

        <span className="live-pill">
          <span />
          LIVE
        </span>
      </div>

      <div className="market-terminal-price">
        {formatPrice(tick?.bid)}
      </div>

      <div className="market-terminal-meta">
        <span>
          Bid{" "}
          <strong>
            {formatPrice(tick?.bid)}
          </strong>
        </span>

        <span>
          Ask{" "}
          <strong>
            {formatPrice(tick?.ask)}
          </strong>
        </span>

        <span>
          Spread{" "}
          <strong>
            {formatSpread(
              tick?.spread,
            )}
          </strong>
        </span>
      </div>

      <div className="market-terminal-time">
        {formatTime(
          tick?.timestamp,
        )}
      </div>
    </button>
  );
}

function MarketStat({
  label,
  value,
}) {
  return (
    <div className="market-stat">
      <span>{label}</span>

      <strong>{value}</strong>
    </div>
  );
}

export default function MarketsPage() {
  const [ticks, setTicks] = useState({});
  const [candles, setCandles] =
    useState([]);

  const [selectedSymbol, setSelectedSymbol] =
    useState("XAUUSD");

  const [timeframe, setTimeframe] =
    useState("15m");

  const [loading, setLoading] =
    useState(true);

  const [refreshing, setRefreshing] =
    useState(false);

  const [error, setError] =
    useState("");

  const [lastUpdated, setLastUpdated] =
    useState(null);

  const selectedTick = useMemo(
    () => ticks[selectedSymbol] || null,
    [ticks, selectedSymbol],
  );

  const latestCandle =
    candles[candles.length - 1] || null;

  const previousCandle =
    candles.length > 1
      ? candles[candles.length - 2]
      : null;

  const candleDirection =
    latestCandle &&
    previousCandle
      ? latestCandle.close >=
        previousCandle.close
        ? "Bullish"
        : "Bearish"
      : "--";

  const loadMarketData = useCallback(
    async (manual = false) => {
      if (manual) {
        setRefreshing(true);
      }

      try {
        setError("");

        const [
          tickResponse,
          candleResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),

          api.get(
            `/api/mt5/market-data/candles/${selectedSymbol}/${timeframe}`,
            {
              params: {
                limit: 500,
              },
            },
          ),
        ]);

        const normalizedTicks =
          extractTicks(
            tickResponse?.data,
          );

        const normalizedCandles =
          extractCandles(
            candleResponse?.data,
          );

        setTicks(normalizedTicks);

        setCandles(normalizedCandles);

        setLastUpdated(new Date());
      } catch (requestError) {
        console.error(
          "Unable to load MT5 market data:",
          requestError,
        );

        const message =
          requestError?.response?.data
            ?.detail ||
          requestError?.message ||
          "Unable to load live market data.";

        setError(message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [selectedSymbol, timeframe],
  );

  useEffect(() => {
    loadMarketData();

    const interval =
      window.setInterval(() => {
        loadMarketData();
      }, 5000);

    return () =>
      window.clearInterval(interval);
  }, [loadMarketData]);

  return (
    <section className="page">
      <div className="page-heading-row">
        <div>
          <span className="eyebrow">
            LIVE MARKET DATA
          </span>

          <h1>Markets</h1>

          <p>
            Monitor live prices and market
            candles directly from MetaTrader 5.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          onClick={() =>
            loadMarketData(true)
          }
          disabled={refreshing}
        >
          <RefreshCw
            size={17}
            className={
              refreshing
                ? "spin-animation"
                : ""
            }
          />

          Refresh
        </button>
      </div>

      <div className="live-source-banner">
        <div className="live-source-dot" />

        <div>
          <strong>
            Live MetaTrader 5 market feed
          </strong>

          <span>
            Real-time bid/ask and candle data
            from the connected trading terminal.
          </span>
        </div>

        <span className="live-source-time">
          {lastUpdated
            ? `Updated ${formatTime(
                lastUpdated,
              )}`
            : "Connecting..."}
        </span>
      </div>

      {error && (
        <div className="error-banner">
          <strong>
            Market data error
          </strong>

          <span>{error}</span>
        </div>
      )}

      <div className="market-terminal-grid">
        {SYMBOLS.map((symbol) => {
          const tick =
            ticks[symbol] || {
              symbol,
              mt5Symbol: null,
              bid: null,
              ask: null,
              spread: null,
              timestamp: null,
            };

          return (
            <MarketTickerCard
              key={symbol}
              symbol={symbol}
              tick={tick}
              selected={
                selectedSymbol === symbol
              }
              onSelect={
                setSelectedSymbol
              }
            />
          );
        })}
      </div>

      <div className="market-chart-panel">
        <div className="market-chart-header">
          <div>
            <span className="eyebrow">
              PRICE ACTION
            </span>

            <h2>
              {selectedSymbol}

              <span>
                {" "}
                / {timeframe}
              </span>
            </h2>
          </div>

          <div className="market-price-highlight">
            <span>Live bid</span>

            <strong>
              {formatPrice(
                selectedTick?.bid,
              )}
            </strong>

            <small>
              Ask{" "}
              {formatPrice(
                selectedTick?.ask,
              )}
            </small>
          </div>
        </div>

        <div className="timeframe-tabs">
          {TIMEFRAMES.map((item) => (
            <button
              key={item.value}
              type="button"
              className={
                timeframe === item.value
                  ? "active"
                  : ""
              }
              onClick={() =>
                setTimeframe(
                  item.value,
                )
              }
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="market-chart-wrap">
          {loading &&
          !candles.length ? (
            <div className="market-chart-empty">
              <RefreshCw
                size={22}
                className="spin-animation"
              />

              <span>
                Loading live candles...
              </span>
            </div>
          ) : (
            <CandleChart
              candles={candles}
            />
          )}
        </div>

        <div className="market-stats-grid">
          <MarketStat
            label="Latest open"
            value={formatPrice(
              latestCandle?.open,
            )}
          />

          <MarketStat
            label="Latest high"
            value={formatPrice(
              latestCandle?.high,
            )}
          />

          <MarketStat
            label="Latest low"
            value={formatPrice(
              latestCandle?.low,
            )}
          />

          <MarketStat
            label="Latest close"
            value={formatPrice(
              latestCandle?.close,
            )}
          />

          <MarketStat
            label="Candle direction"
            value={candleDirection}
          />

          <MarketStat
            label="Candles loaded"
            value={candles.length}
          />
        </div>
      </div>
    </section>
  );
}