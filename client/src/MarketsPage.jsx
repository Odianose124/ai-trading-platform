import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import api from "./services/api";
import { useMT5WebSocket } from "./context/MT5WebSocketContext";
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

function normalizeSymbol(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

function findRealtimeTick(ticks, requestedSymbol) {
  if (
    !ticks ||
    typeof ticks !== "object" ||
    !requestedSymbol
  ) {
    return null;
  }

  const requested = normalizeSymbol(
    requestedSymbol,
  );

  if (!requested) {
    return null;
  }

  const entries = Object.entries(ticks);

  const exactMatch = entries.find(
    ([key, tick]) => {
      const candidates = [
        key,
        tick?.symbol,
        tick?.name,
        tick?.mt5_symbol,
        tick?.broker_symbol,
        tick?.brokerSymbol,
        tick?.requested_symbol,
      ];

      return candidates.some(
        (candidate) =>
          normalizeSymbol(candidate) ===
          requested,
      );
    },
  );

  if (exactMatch) {
    return normalizeTick(
      exactMatch[1],
      requestedSymbol,
    );
  }

  const relatedMatch = entries.find(
    ([key, tick]) => {
      const candidates = [
        key,
        tick?.symbol,
        tick?.name,
        tick?.mt5_symbol,
        tick?.broker_symbol,
        tick?.brokerSymbol,
      ];

      return candidates.some((candidate) => {
        const normalizedCandidate =
          normalizeSymbol(candidate);

        return (
          normalizedCandidate &&
          (normalizedCandidate.startsWith(
            requested,
          ) ||
            normalizedCandidate.endsWith(
              requested,
            ))
        );
      });
    },
  );

  if (!relatedMatch) {
    return null;
  }

  return normalizeTick(
    relatedMatch[1],
    requestedSymbol,
  );
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
      aria-label="Market candlestick chart"
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
  live,
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

          {live ? "LIVE" : "OFFLINE"}
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
  const {
    connected: websocketConnected,
    ticks: realtimeTicks,
    timestamp: realtimeTimestamp,
    error: websocketError,
  } = useMT5WebSocket();

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

  const [
    candleLastUpdated,
    setCandleLastUpdated,
  ] = useState(null);

  const ticks = useMemo(() => {
    return SYMBOLS.reduce(
      (result, symbol) => {
        const tick = findRealtimeTick(
          realtimeTicks,
          symbol,
        );

        if (tick) {
          result[symbol] = tick;
        }

        return result;
      },
      {},
    );
  }, [realtimeTicks]);

  const selectedTick = useMemo(
    () =>
      ticks[selectedSymbol] || null,
    [ticks, selectedSymbol],
  );

  const latestCandle =
    candles[candles.length - 1] ||
    null;

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

        const candleResponse =
          await api.get(
            `/api/mt5/market-data/candles/${selectedSymbol}/${timeframe}`,
            {
              params: {
                limit: 500,
              },
            },
          );

        const normalizedCandles =
          extractCandles(
            candleResponse?.data,
          );

        setCandles(normalizedCandles);

        setCandleLastUpdated(
          new Date(),
        );
      } catch (requestError) {
        console.error(
          "Unable to load MT5 candle data:",
          requestError,
        );

        const message =
          requestError?.response?.data
            ?.detail ||
          requestError?.message ||
          "Unable to load market candle data.";

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

    return () => {};
  }, [loadMarketData]);

  const liveFeedTime =
    realtimeTimestamp ||
    selectedTick?.timestamp ||
    null;

  const feedError =
    websocketError ||
    error;

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
            Bid/ask prices are received from
            the connected account-isolated
            MT5 live feed.
          </span>
        </div>

        <span className="live-source-time">
          {websocketConnected &&
          liveFeedTime
            ? `Updated ${formatTime(
                liveFeedTime,
              )}`
            : websocketConnected
              ? "Live feed connected"
              : "Connecting..."}
        </span>
      </div>

      {feedError && (
        <div className="error-banner">
          <strong>
            Market data connection
          </strong>

          <span>{feedError}</span>
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
              live={
                websocketConnected &&
                Boolean(
                  ticks[symbol],
                )
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
                Loading market candles...
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

        {candleLastUpdated && (
          <div className="market-terminal-time">
            Candle history updated{" "}
            {formatTime(
              candleLastUpdated,
            )}
          </div>
        )}
      </div>
    </section>
  );
}
