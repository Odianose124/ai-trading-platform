import { useEffect, useState } from "react";
import {
  BarChart3,
  BriefcaseBusiness,
  CheckCircle2,
  Clock3,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import api from "./services/api";

const AI_MAGIC_NUMBER = 202609;

export default function TradeHistoryPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  async function loadHistory(manualRefresh = false) {
    try {
      if (manualRefresh) {
        setRefreshing(true);
      }

      setError("");

      const response = await api.get("/api/mt5/history");
      setData(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to load AI trade history.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadHistory();

    const interval = window.setInterval(
      () => loadHistory(false),
      10000,
    );

    return () => window.clearInterval(interval);
  }, []);

  const trades = Array.isArray(data?.trades)
    ? data.trades
    : [];

  const closedTrades = trades.filter(
    (trade) =>
      String(trade.status || "").toUpperCase() ===
        "CLOSED" ||
      trade.closed_at,
  );

  const wins = closedTrades.filter(
    (trade) =>
      String(trade.result || "").toUpperCase() ===
      "WIN",
  ).length;

  const losses = closedTrades.filter(
    (trade) =>
      String(trade.result || "").toUpperCase() ===
      "LOSS",
  ).length;

  const totalProfit = trades.reduce(
    (total, trade) =>
      total + Number(trade.profit || 0),
    0,
  );

  const winRate =
    closedTrades.length > 0
      ? (wins / closedTrades.length) * 100
      : 0;

  return (
    <section className="page">
      <div className="page-heading-row">
        <div className="page-heading">
          <span className="eyebrow">History</span>

          <h1>Trade history</h1>

          <p>
            Executed AI-managed trades and their outcomes
            recorded by the trading platform.
          </p>
        </div>

        <button
          className="secondary-button"
          onClick={() => loadHistory(true)}
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

          {refreshing
            ? "Refreshing..."
            : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <XCircle size={17} />
          <span>{error}</span>
        </div>
      )}

      <div className="live-source-banner">
        <span className="live-indicator" />

        <div>
          <strong>Live AI trade history</strong>

          <span>
            Auto-refreshing every 10 seconds · Magic{" "}
            {data?.magic || AI_MAGIC_NUMBER}
          </span>
        </div>
      </div>

      <div className="position-summary-grid">
        <HistorySummaryCard
          label="Total trades"
          value={trades.length}
          icon={BriefcaseBusiness}
        />

        <HistorySummaryCard
          label="Wins"
          value={wins}
          icon={CheckCircle2}
          positive={wins > 0}
        />

        <HistorySummaryCard
          label="Losses"
          value={losses}
          icon={XCircle}
          negative={losses > 0}
        />

        <HistorySummaryCard
          label="Total P/L"
          value={formatMoney(totalProfit)}
          icon={
            totalProfit >= 0
              ? TrendingUp
              : TrendingDown
          }
          positive={totalProfit > 0}
          negative={totalProfit < 0}
        />

        <HistorySummaryCard
          label="Win rate"
          value={`${winRate.toFixed(1)}%`}
          icon={BarChart3}
          positive={
            winRate >= 50 &&
            closedTrades.length > 0
          }
        />
      </div>

      <div className="section-title-row">
        <div>
          <span className="card-label">
            Recorded trades
          </span>

          <h3>AI execution history</h3>
        </div>
      </div>

      {loading ? (
        <div className="positions-loading">
          <span className="loading-text">
            Loading live trade history...
          </span>
        </div>
      ) : trades.length === 0 ? (
        <div className="empty-state">
          <Clock3 size={25} />

          <h3>No AI trades recorded</h3>

          <p>
            There are currently no AI-managed trades in
            the trade history database. No test or fake
            trades are displayed.
          </p>
        </div>
      ) : (
        <div className="positions-list">
          {trades.map((trade) => (
            <TradeHistoryCard
              key={
                trade.id ||
                `${trade.ticket}-${trade.deal || "trade"}`
              }
              trade={trade}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function HistorySummaryCard({
  label,
  value,
  icon: Icon,
  positive,
  negative,
}) {
  return (
    <article className="position-summary-card">
      <div className="position-summary-icon">
        <Icon size={19} />
      </div>

      <div>
        <span>{label}</span>

        <strong
          className={
            positive
              ? "profit-positive"
              : negative
                ? "profit-negative"
                : ""
          }
        >
          {value}
        </strong>
      </div>
    </article>
  );
}

function TradeHistoryCard({ trade }) {
  const direction = String(
    trade.direction || "",
  ).toUpperCase();

  const isBuy = direction === "BUY";

  const profit = Number(
    trade.profit || 0,
  );

  const status = String(
    trade.status || "UNKNOWN",
  ).toUpperCase();

  const result = String(
    trade.result || "",
  ).toUpperCase();

  return (
    <article className="live-position-card">
      <div className="position-card-top">
        <div className="position-instrument">
          <div
            className={`position-side-icon ${
              isBuy
                ? "position-buy"
                : "position-sell"
            }`}
          >
            {isBuy ? (
              <TrendingUp size={19} />
            ) : (
              <TrendingDown size={19} />
            )}
          </div>

          <div>
            <strong>
              {trade.symbol || "--"}
            </strong>

            <span>
              Ticket #{trade.ticket || "--"}

              {trade.deal
                ? ` · Deal #${trade.deal}`
                : ""}
            </span>
          </div>
        </div>

        <div
          className={`position-side-badge ${
            isBuy
              ? "position-buy"
              : "position-sell"
          }`}
        >
          {direction || "UNKNOWN"}
        </div>
      </div>

      <div className="position-details-grid">
        <HistoryDetail
          label="Volume"
          value={formatVolume(trade.volume)}
        />

        <HistoryDetail
          label="Entry"
          value={formatNumber(trade.entry_price)}
        />

        <HistoryDetail
          label="Exit"
          value={formatNumber(trade.exit_price)}
        />

        <HistoryDetail
          label="Stop Loss"
          value={formatOptionalNumber(
            trade.stop_loss,
          )}
        />

        <HistoryDetail
          label="Take Profit"
          value={formatOptionalNumber(
            trade.take_profit,
          )}
        />

        <HistoryDetail
          label="Confidence"
          value={formatPercent(
            trade.confidence,
          )}
        />

        <HistoryDetail
          label="Risk"
          value={formatPercent(
            trade.risk_percent,
          )}
        />

        <HistoryDetail
          label="Risk / Reward"
          value={
            trade.risk_reward == null
              ? "--"
              : `1:${Number(
                  trade.risk_reward,
                ).toFixed(2)}`
          }
        />

        <HistoryDetail
          label="Strategy"
          value={trade.strategy || "--"}
        />

        <HistoryDetail
          label="Setup quality"
          value={
            trade.setup_quality || "--"
          }
        />

        <HistoryDetail
          label="Opened"
          value={formatDateTime(
            trade.opened_at,
          )}
        />

        <HistoryDetail
          label="Closed"
          value={formatDateTime(
            trade.closed_at,
          )}
        />
      </div>

      <div className="position-profit-row">
        <span>
          {status}
          {result ? ` · ${result}` : ""}
        </span>

        <strong
          className={
            profit > 0
              ? "profit-positive"
              : profit < 0
                ? "profit-negative"
                : ""
          }
        >
          {formatMoney(profit)}
        </strong>
      </div>

      {trade.ai_reason && (
        <div className="reasoning-block">
          <span>AI reason</span>
          <p>{trade.ai_reason}</p>
        </div>
      )}

      <div className="position-card-footer">
        <span>MT5 · AI managed</span>

        <span>
          Magic {trade.magic || AI_MAGIC_NUMBER}
        </span>
      </div>
    </article>
  );
}

function HistoryDetail({ label, value }) {
  return (
    <div className="position-detail">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatNumber(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  return Number(value).toLocaleString(
    undefined,
    {
      minimumFractionDigits: 2,
      maximumFractionDigits: 5,
    },
  );
}

function formatOptionalNumber(value) {
  if (
    value === null ||
    value === undefined ||
    Number(value) === 0 ||
    Number.isNaN(Number(value))
  ) {
    return "Not set";
  }

  return formatNumber(value);
}

function formatMoney(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  const numericValue = Number(value);

  const sign =
    numericValue > 0 ? "+" : "";

  return `${sign}$${numericValue.toLocaleString(
    undefined,
    {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    },
  )}`;
}

function formatVolume(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  return Number(value).toLocaleString(
    undefined,
    {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    },
  );
}

function formatPercent(value) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  return `${Number(value).toFixed(1)}%`;
}

function formatDateTime(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString(
    undefined,
    {
      dateStyle: "medium",
      timeStyle: "short",
    },
  );
}
