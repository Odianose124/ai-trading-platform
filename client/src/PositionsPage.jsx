import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BriefcaseBusiness,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import api from "./services/api";

function formatNumber(value, digits = 2) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatMoney(value) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  const numericValue = Number(value);

  return `${numericValue < 0 ? "-" : ""}$${Math.abs(
    numericValue,
  ).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function PositionTypeBadge({ type }) {
  const isBuy = type === "buy";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 10px",
        borderRadius: "999px",
        background: isBuy
          ? "rgba(34, 197, 94, 0.12)"
          : "rgba(239, 68, 68, 0.12)",
        color: isBuy ? "#22c55e" : "#ef4444",
        fontSize: "12px",
        fontWeight: 700,
        textTransform: "uppercase",
      }}
    >
      {isBuy ? (
        <ArrowUpRight size={14} />
      ) : (
        <ArrowDownRight size={14} />
      )}

      {isBuy ? "Buy" : "Sell"}
    </span>
  );
}

function PositionCard({ position }) {
  const profit = Number(position.profit || 0);
  const isProfitable = profit > 0;
  const isLosing = profit < 0;

  return (
    <article
      style={{
        background: "#0f172a",
        border: "1px solid rgba(148, 163, 184, 0.14)",
        borderRadius: "18px",
        padding: "20px",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "12px",
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "6px",
            }}
          >
            <strong
              style={{
                color: "#f8fafc",
                fontSize: "20px",
              }}
            >
              {position.symbol}
            </strong>

            <PositionTypeBadge type={position.type} />
          </div>

          <span
            style={{
              color: "#64748b",
              fontSize: "12px",
            }}
          >
            Ticket #{position.ticket}
          </span>
        </div>

        <div
          style={{
            textAlign: "right",
          }}
        >
          <span
            style={{
              display: "block",
              color: "#64748b",
              fontSize: "11px",
              marginBottom: "4px",
            }}
          >
            Floating P/L
          </span>

          <strong
            style={{
              color: isProfitable
                ? "#22c55e"
                : isLosing
                  ? "#ef4444"
                  : "#94a3b8",
              fontSize: "18px",
            }}
          >
            {formatMoney(profit)}
          </strong>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(120px, 1fr))",
          gap: "12px",
        }}
      >
        <Metric
          label="Volume"
          value={formatNumber(position.volume, 2)}
        />

        <Metric
          label="Entry"
          value={formatNumber(position.entry_price, 5)}
        />

        <Metric
          label="Current"
          value={formatNumber(position.current_price, 5)}
        />

        <Metric
          label="Stop Loss"
          value={
            Number(position.stop_loss || 0) > 0
              ? formatNumber(position.stop_loss, 5)
              : "Not set"
          }
        />

        <Metric
          label="Take Profit"
          value={
            Number(position.take_profit || 0) > 0
              ? formatNumber(position.take_profit, 5)
              : "Not set"
          }
        />

        <Metric
          label="Swap"
          value={formatMoney(position.swap)}
        />
      </div>

      <div
        style={{
          borderTop:
            "1px solid rgba(148, 163, 184, 0.10)",
          paddingTop: "14px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          color: "#64748b",
          fontSize: "12px",
        }}
      >
        <ShieldCheck size={15} />

        <span>
          Managed by AI Trader · Magic {position.magic}
        </span>
      </div>
    </article>
  );
}

function Metric({ label, value }) {
  return (
    <div
      style={{
        background: "#020617",
        borderRadius: "12px",
        padding: "12px",
      }}
    >
      <span
        style={{
          display: "block",
          color: "#64748b",
          fontSize: "11px",
          marginBottom: "6px",
        }}
      >
        {label}
      </span>

      <strong
        style={{
          color: "#e2e8f0",
          fontSize: "14px",
        }}
      >
        {value}
      </strong>
    </div>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  accent = "#94a3b8",
}) {
  return (
    <div
      style={{
        background: "#0f172a",
        border:
          "1px solid rgba(148, 163, 184, 0.14)",
        borderRadius: "16px",
        padding: "18px",
        display: "flex",
        alignItems: "center",
        gap: "14px",
      }}
    >
      <div
        style={{
          width: "42px",
          height: "42px",
          borderRadius: "12px",
          display: "grid",
          placeItems: "center",
          background: `${accent}18`,
          color: accent,
        }}
      >
        <Icon size={20} />
      </div>

      <div>
        <span
          style={{
            display: "block",
            color: "#64748b",
            fontSize: "11px",
            marginBottom: "4px",
          }}
        >
          {label}
        </span>

        <strong
          style={{
            color: "#f8fafc",
            fontSize: "18px",
          }}
        >
          {value}
        </strong>
      </div>
    </div>
  );
}

export default function PositionsPage() {
  const [positions, setPositions] = useState([]);
  const [summary, setSummary] = useState({
    open_trades: 0,
    total_volume: 0,
    floating_profit: 0,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadPositions = useCallback(
    async (manual = false) => {
      try {
        if (manual) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }

        setError("");

        const [positionsResponse, summaryResponse] =
          await Promise.all([
            api.get("/api/mt5/positions"),
            api.get("/api/mt5/positions/summary"),
          ]);

        setPositions(
          positionsResponse?.data?.positions || [],
        );

        setSummary({
          open_trades:
            summaryResponse?.data?.open_trades ?? 0,

          total_volume:
            summaryResponse?.data?.total_volume ?? 0,

          floating_profit:
            summaryResponse?.data?.floating_profit ?? 0,
        });
      } catch (requestError) {
        setError(
          requestError?.response?.data?.detail ||
            "Unable to load live MT5 positions.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadPositions();

    const interval = window.setInterval(() => {
      loadPositions();
    }, 5000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadPositions]);

  const floatingProfit = Number(
    summary.floating_profit || 0,
  );

  return (
    <section className="page">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "18px",
          flexWrap: "wrap",
          marginBottom: "26px",
        }}
      >
        <div>
          <div
            style={{
              color: "#22c55e",
              fontSize: "11px",
              fontWeight: 800,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginBottom: "8px",
            }}
          >
            Live MT5 positions
          </div>

          <h1
            style={{
              margin: 0,
              color: "#f8fafc",
              fontSize: "clamp(26px, 5vw, 38px)",
              lineHeight: 1.1,
            }}
          >
            Open Positions
          </h1>

          <p
            style={{
              margin: "10px 0 0",
              color: "#64748b",
              maxWidth: "680px",
              lineHeight: 1.6,
            }}
          >
            Monitor active AI-managed MetaTrader 5
            positions, exposure and live floating
            profit or loss.
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadPositions(true)}
          disabled={refreshing}
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
            border: "1px solid rgba(148, 163, 184, 0.18)",
            background: "#0f172a",
            color: "#e2e8f0",
            borderRadius: "12px",
            padding: "11px 15px",
            cursor: refreshing
              ? "not-allowed"
              : "pointer",
            opacity: refreshing ? 0.6 : 1,
          }}
        >
          <RefreshCw
            size={16}
            style={{
              animation: refreshing
                ? "spin 1s linear infinite"
                : "none",
            }}
          />

          {refreshing
            ? "Refreshing..."
            : "Refresh positions"}
        </button>
      </div>

      {error && (
        <div
          style={{
            marginBottom: "20px",
            padding: "14px 16px",
            borderRadius: "12px",
            background: "rgba(239, 68, 68, 0.10)",
            border:
              "1px solid rgba(239, 68, 68, 0.25)",
            color: "#fca5a5",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "14px",
          marginBottom: "24px",
        }}
      >
        <SummaryCard
          icon={BriefcaseBusiness}
          label="Open positions"
          value={summary.open_trades}
          accent="#38bdf8"
        />

        <SummaryCard
          icon={Activity}
          label="Total volume"
          value={formatNumber(
            summary.total_volume,
            2,
          )}
          accent="#a78bfa"
        />

        <SummaryCard
          icon={
            floatingProfit >= 0
              ? TrendingUp
              : TrendingDown
          }
          label="Floating P/L"
          value={formatMoney(floatingProfit)}
          accent={
            floatingProfit > 0
              ? "#22c55e"
              : floatingProfit < 0
                ? "#ef4444"
                : "#94a3b8"
          }
        />
      </div>

      <section
        style={{
          background: "#020617",
          border:
            "1px solid rgba(148, 163, 184, 0.12)",
          borderRadius: "20px",
          padding: "20px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "12px",
            marginBottom: "18px",
          }}
        >
          <div>
            <h2
              style={{
                margin: 0,
                color: "#f8fafc",
                fontSize: "18px",
              }}
            >
              Active positions
            </h2>

            <p
              style={{
                margin: "5px 0 0",
                color: "#64748b",
                fontSize: "12px",
              }}
            >
              Automatically refreshed from MetaTrader 5
            </p>
          </div>

          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
              color: "#22c55e",
              fontSize: "11px",
              fontWeight: 700,
            }}
          >
            <span className="live-indicator" />
            LIVE
          </span>
        </div>

        {loading ? (
          <div
            style={{
              minHeight: "180px",
              display: "grid",
              placeItems: "center",
              color: "#64748b",
            }}
          >
            Loading live MT5 positions...
          </div>
        ) : positions.length === 0 ? (
          <div
            style={{
              minHeight: "240px",
              display: "grid",
              placeItems: "center",
              textAlign: "center",
              padding: "30px",
            }}
          >
            <div>
              <div
                style={{
                  width: "56px",
                  height: "56px",
                  borderRadius: "16px",
                  display: "grid",
                  placeItems: "center",
                  margin: "0 auto 14px",
                  background:
                    "rgba(56, 189, 248, 0.08)",
                  color: "#38bdf8",
                }}
              >
                <BriefcaseBusiness size={25} />
              </div>

              <h3
                style={{
                  margin: "0 0 8px",
                  color: "#e2e8f0",
                  fontSize: "17px",
                }}
              >
                No open positions
              </h3>

              <p
                style={{
                  margin: 0,
                  color: "#64748b",
                  fontSize: "13px",
                  lineHeight: 1.6,
                  maxWidth: "440px",
                }}
              >
                There are currently no active AI-managed
                positions on MetaTrader 5. New positions
                will appear here automatically after a
                confirmed execution.
              </p>
            </div>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(300px, 1fr))",
              gap: "16px",
            }}
          >
            {positions.map((position) => (
              <PositionCard
                key={position.ticket}
                position={position}
              />
            ))}
          </div>
        )}
      </section>

      <div
        style={{
          marginTop: "18px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          color: "#64748b",
          fontSize: "11px",
        }}
      >
        <ShieldCheck size={15} />

        <span>
          Read-only monitoring phase · Live execution
          actions will require separate confirmation
          safeguards.
        </span>
      </div>

      <style>{`
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }

          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </section>
  );
}