import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BrainCircuit,
  BriefcaseBusiness,
  CheckCircle2,
  Clock3,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import api from "./services/api";
import { useMT5WebSocket } from "./context/MT5WebSocketContext.jsx";

function number(value, digits = 5) {
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

function money(value) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    Number.isNaN(Number(value))
  ) {
    return "--";
  }

  const amount = Number(value);

  return `${amount < 0 ? "-" : ""}$${Math.abs(amount).toLocaleString(
    undefined,
    {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    },
  )}`;
}

function dateTime(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "--"
    : date.toLocaleString();
}

function Badge({ children, tone = "neutral" }) {
  const tones = {
    buy: {
      color: "#22c55e",
      background: "rgba(34,197,94,.12)",
    },
    sell: {
      color: "#ef4444",
      background: "rgba(239,68,68,.12)",
    },
    pending: {
      color: "#f59e0b",
      background: "rgba(245,158,11,.12)",
    },
    live: {
      color: "#38bdf8",
      background: "rgba(56,189,248,.12)",
    },
    success: {
      color: "#22c55e",
      background: "rgba(34,197,94,.12)",
    },
    neutral: {
      color: "#94a3b8",
      background: "rgba(148,163,184,.10)",
    },
  };

  const selected = tones[tone] || tones.neutral;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        borderRadius: 999,
        color: selected.color,
        background: selected.background,
        fontSize: 11,
        fontWeight: 800,
        textTransform: "uppercase",
      }}
    >
      {children}
    </span>
  );
}

function Metric({ label, value }) {
  return (
    <div
      style={{
        background: "#020617",
        border: "1px solid rgba(148,163,184,.08)",
        borderRadius: 12,
        padding: 12,
      }}
    >
      <span
        style={{
          display: "block",
          color: "#64748b",
          fontSize: 10,
          marginBottom: 6,
          textTransform: "uppercase",
          letterSpacing: ".05em",
        }}
      >
        {label}
      </span>

      <strong
        style={{
          color: "#e2e8f0",
          fontSize: 14,
        }}
      >
        {value}
      </strong>
    </div>
  );
}

function PendingOrderCard({ order }) {
  const isBuy = order.direction === "buy";

  return (
    <article
      style={{
        background: "#0f172a",
        border: "1px solid rgba(245,158,11,.18)",
        borderRadius: 18,
        padding: 18,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              marginBottom: 6,
            }}
          >
            <strong
              style={{
                color: "#f8fafc",
                fontSize: 19,
              }}
            >
              {order.broker_symbol || order.symbol}
            </strong>

            <Badge tone={isBuy ? "buy" : "sell"}>
              {isBuy ? "BUY" : "SELL"}
            </Badge>

            <Badge tone="pending">
              {order.order_type}
            </Badge>
          </div>

          <span
            style={{
              color: "#64748b",
              fontSize: 11,
            }}
          >
            MT5 Order #{order.order_ticket}
          </span>
        </div>

        <Badge tone="pending">
          {order.pending_order_status}
        </Badge>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit,minmax(130px,1fr))",
          gap: 10,
        }}
      >
        <Metric
          label="Entry"
          value={number(order.entry_price)}
        />

        <Metric
          label="Volume"
          value={number(order.volume, 2)}
        />

        <Metric
          label="Stop Loss"
          value={number(order.stop_loss)}
        />

        <Metric
          label="Take Profit"
          value={number(order.take_profit)}
        />

        <Metric
          label="Placed"
          value={dateTime(order.placed_at)}
        />

        <Metric
          label="Execution"
          value={order.execution_status}
        />
      </div>

      <div
        style={{
          marginTop: 14,
          display: "flex",
          alignItems: "center",
          gap: 8,
          color: "#64748b",
          fontSize: 11,
        }}
      >
        <Clock3 size={14} />

        Waiting for MetaTrader 5 activation
      </div>
    </article>
  );
}

function PositionCard({
  position,
  tick,
  management,
  onEvaluate,
  onExecute,
  onActions,
}) {
  const livePrice =
    position.type === "buy"
      ? tick?.bid ?? position.current_price
      : tick?.ask ?? position.current_price;

  const entry = Number(position.entry_price || 0);
  const current = Number(livePrice || 0);

  const profit =
    position.type === "buy"
      ? (current - entry) * Number(position.volume || 0)
      : (entry - current) * Number(position.volume || 0);

  const displayedProfit =
    Number.isFinite(profit)
      ? profit
      : Number(position.profit || 0);

  const evaluation = management?.evaluation;
  const actions = management?.actions || [];

  return (
    <article
      style={{
        background: "#0f172a",
        border: "1px solid rgba(148,163,184,.14)",
        borderRadius: 18,
        padding: 20,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 14,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
            }}
          >
            <strong
              style={{
                color: "#f8fafc",
                fontSize: 21,
              }}
            >
              {position.symbol}
            </strong>

            <Badge
              tone={
                position.type === "buy"
                  ? "buy"
                  : "sell"
              }
            >
              {position.type}
            </Badge>

            <Badge tone="live">LIVE</Badge>
          </div>

          <span
            style={{
              display: "block",
              marginTop: 6,
              color: "#64748b",
              fontSize: 11,
            }}
          >
            Position #{position.ticket}
          </span>
        </div>

        <div style={{ textAlign: "right" }}>
          <span
            style={{
              display: "block",
              color: "#64748b",
              fontSize: 10,
              textTransform: "uppercase",
            }}
          >
            Floating P/L
          </span>

          <strong
            style={{
              color:
                displayedProfit > 0
                  ? "#22c55e"
                  : displayedProfit < 0
                    ? "#ef4444"
                    : "#94a3b8",
              fontSize: 19,
            }}
          >
            {money(displayedProfit)}
          </strong>
        </div>
      </div>

      <div
        style={{
          marginTop: 18,
          padding: 16,
          borderRadius: 14,
          background: "#020617",
          border: "1px solid rgba(56,189,248,.12)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{
              color: "#64748b",
              fontSize: 10,
              textTransform: "uppercase",
            }}
          >
            Live MT5 price
          </span>

          <span
            style={{
              color: "#38bdf8",
              fontSize: 10,
            }}
          >
            {tick?.timestamp
              ? new Date(
                  tick.timestamp,
                ).toLocaleTimeString()
              : "Waiting"}
          </span>
        </div>

        <strong
          style={{
            display: "block",
            marginTop: 6,
            color: "#f8fafc",
            fontSize: 30,
            letterSpacing: ".02em",
          }}
        >
          {number(livePrice)}
        </strong>

        <div
          style={{
            display: "flex",
            gap: 20,
            marginTop: 7,
            color: "#64748b",
            fontSize: 11,
          }}
        >
          <span>
            Bid{" "}
            <strong style={{ color: "#cbd5e1" }}>
              {number(tick?.bid)}
            </strong>
          </span>

          <span>
            Ask{" "}
            <strong style={{ color: "#cbd5e1" }}>
              {number(tick?.ask)}
            </strong>
          </span>

          <span>
            Spread{" "}
            <strong style={{ color: "#cbd5e1" }}>
              {number(tick?.spread)}
            </strong>
          </span>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit,minmax(130px,1fr))",
          gap: 10,
          marginTop: 14,
        }}
      >
        <Metric
          label="Volume"
          value={number(position.volume, 2)}
        />

        <Metric
          label="Entry"
          value={number(position.entry_price)}
        />

        <Metric
          label="Stop Loss"
          value={
            Number(position.stop_loss || 0) > 0
              ? number(position.stop_loss)
              : "Not set"
          }
        />

        <Metric
          label="Take Profit"
          value={
            Number(position.take_profit || 0) > 0
              ? number(position.take_profit)
              : "Not set"
          }
        />

        <Metric
          label="Swap"
          value={money(position.swap)}
        />

        <Metric
          label="Magic"
          value={position.magic}
        />
      </div>

      <div
        style={{
          marginTop: 16,
          paddingTop: 14,
          borderTop:
            "1px solid rgba(148,163,184,.10)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <BrainCircuit
              size={17}
              color="#38bdf8"
            />

            <strong
              style={{
                color: "#e2e8f0",
                fontSize: 14,
              }}
            >
              AI Trade Management
            </strong>
          </div>

          <span
            style={{
              color: "#64748b",
              fontSize: 10,
            }}
          >
            Magic {position.magic}
          </span>
        </div>

        <div
          style={{
            display: "flex",
            gap: 9,
            flexWrap: "wrap",
            marginTop: 12,
          }}
        >
          <button
            type="button"
            onClick={() =>
              onEvaluate(position.ticket)
            }
            disabled={management?.evaluating}
            style={buttonStyle("#38bdf8")}
          >
            <BrainCircuit size={15} />
            {management?.evaluating
              ? "Evaluating..."
              : "Evaluate"}
          </button>

          <button
            type="button"
            onClick={() =>
              onActions(position.ticket)
            }
            disabled={management?.loadingActions}
            style={buttonStyle("#94a3b8")}
          >
            <Clock3 size={15} />
            {management?.loadingActions
              ? "Loading..."
              : "Action history"}
          </button>
        </div>

        {evaluation && (
          <div
            style={{
              marginTop: 12,
              padding: 14,
              borderRadius: 12,
              background: "#020617",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 10,
              }}
            >
              <strong style={{ color: "#f8fafc" }}>
                {evaluation.decision}
              </strong>

              <span
                style={{
                  color:
                    evaluation.ai_management_enabled
                      ? "#22c55e"
                      : "#ef4444",
                  fontSize: 10,
                }}
              >
                AI{" "}
                {evaluation.ai_management_enabled
                  ? "enabled"
                  : "disabled"}
              </span>
            </div>

            <p
              style={{
                color: "#94a3b8",
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              {evaluation.message}
            </p>

            {evaluation.decision !== "HOLD" &&
              evaluation.ai_management_enabled && (
                <button
                  type="button"
                  onClick={() =>
                    onExecute(
                      position.ticket,
                      evaluation,
                    )
                  }
                  disabled={management?.executing}
                  style={buttonStyle("#22c55e")}
                >
                  <ShieldCheck size={15} />
                  {management?.executing
                    ? "Executing..."
                    : `Execute ${evaluation.decision}`}
                </button>
              )}
          </div>
        )}

        {actions.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <span
              style={{
                color: "#64748b",
                fontSize: 10,
                textTransform: "uppercase",
              }}
            >
              Recent actions
            </span>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 7,
                marginTop: 7,
              }}
            >
              {actions.slice(0, 5).map((action) => (
                <div
                  key={action.id}
                  style={{
                    padding: 9,
                    borderRadius: 9,
                    background: "#0f172a",
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      color: "#cbd5e1",
                      fontSize: 10,
                    }}
                  >
                    {action.decision}
                    {" Â· "}
                    {dateTime(action.created_at)}
                  </span>

                  <span
                    style={{
                      color:
                        action.status ===
                          "reconciled" ||
                        action.status ===
                          "already_applied"
                          ? "#22c55e"
                          : action.status ===
                              "failed"
                            ? "#ef4444"
                            : "#f59e0b",
                      fontSize: 10,
                      fontWeight: 700,
                    }}
                  >
                    {action.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

function buttonStyle(color) {
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    border: `1px solid ${color}55`,
    background: `${color}12`,
    color,
    borderRadius: 10,
    padding: "9px 12px",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 11,
  };
}

export default function PositionsPage() {
  const {
    positions: livePositions,
    pendingOrders: livePendingOrders,
    summary: liveSummary,
    ticks: liveTicks,
    connected: mt5Connected,
  } = useMT5WebSocket();
  const [positions, setPositions] = useState([]);
  const [pendingOrders, setPendingOrders] =
    useState([]);

  const [summary, setSummary] = useState({
    open_trades: 0,
    total_volume: 0,
    floating_profit: 0,
  });

  const [management, setManagement] =
    useState({});

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const updateManagement = useCallback(
    (ticket, patch) => {
      setManagement((current) => ({
        ...current,
        [ticket]: {
          ...current[ticket],
          ...patch,
        },
      }));
    },
    [],
  );

  const loadPositions = useCallback(
    async (manual = false) => {
      try {
        if (manual) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }

        const [
          positionsResponse,
          summaryResponse,
          pendingResponse,
        ] = await Promise.all([
          api.get("/api/mt5/positions"),
          api.get("/api/mt5/positions/summary"),
          api.get("/api/pending-orders"),
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

        setPendingOrders(
          pendingResponse?.data?.pending_orders || [],
        );

        setError("");
      } catch (requestError) {
        setError(
          requestError?.response?.data?.detail ||
            "Unable to load live MT5 trading state.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!livePositions) {
      return;
    }

    setPositions(livePositions);

    setPendingOrders(
      livePendingOrders || [],
    );

    if (liveSummary) {
      setSummary({
        open_trades:
          liveSummary.total_positions ?? 0,
        total_volume:
          liveSummary.total_volume ?? 0,
        floating_profit:
          liveSummary.floating_profit ?? 0,
      });
    }


    setLoading(false);
    setError("");

  }, [
    livePositions,
    livePendingOrders,
    liveSummary,
    liveTicks,
  ]);
  const loadActions = useCallback(
    async (ticket) => {
      updateManagement(ticket, {
        loadingActions: true,
        error: "",
      });

      try {
        const response = await api.get(
          `/api/ai-trade-management/positions/${ticket}/actions`,
        );

        updateManagement(ticket, {
          actions: response?.data?.actions || [],
          loadingActions: false,
        });
      } catch (requestError) {
        updateManagement(ticket, {
          loadingActions: false,
          error:
            requestError?.response?.data?.detail ||
            "Unable to load action history.",
        });
      }
    },
    [updateManagement],
  );

  const evaluate = useCallback(
    async (ticket) => {
      updateManagement(ticket, {
        evaluating: true,
        error: "",
      });

      try {
        const response = await api.get(
          `/api/ai-trade-management/positions/${ticket}/evaluate`,
        );

        updateManagement(ticket, {
          evaluation: response.data,
          evaluating: false,
        });
      } catch (requestError) {
        updateManagement(ticket, {
          evaluating: false,
          error:
            requestError?.response?.data?.detail ||
            "Unable to evaluate position.",
        });
      }
    },
    [updateManagement],
  );

  const execute = useCallback(
    async (ticket, evaluation) => {
      if (!evaluation?.decision) {
        return;
      }

      if (
        !window.confirm(
          `Execute ${evaluation.decision} for position #${ticket}?`,
        )
      ) {
        return;
      }

      updateManagement(ticket, {
        executing: true,
        error: "",
      });

      try {
        const response = await api.post(
          `/api/ai-trade-management/positions/${ticket}/execute`,
        );

        updateManagement(ticket, {
          executing: false,
          lastExecution: response.data,
        });

        await loadPositions(true);
        await loadActions(ticket);
      } catch (requestError) {
        updateManagement(ticket, {
          executing: false,
          error:
            requestError?.response?.data?.detail ||
            "Management execution failed.",
        });
      }
    },
    [loadActions, loadPositions, updateManagement],
  );

  useEffect(() => {
    if (!mt5Connected) {
      setLoading(true);
    }
  }, [mt5Connected]);

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
          gap: 18,
          flexWrap: "wrap",
          marginBottom: 26,
        }}
      >
        <div>
          <div
            style={{
              color: "#22c55e",
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: ".12em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Live MT5 trading
          </div>

          <h1
            style={{
              margin: 0,
              color: "#f8fafc",
              fontSize: "clamp(26px,5vw,38px)",
            }}
          >
            Positions
          </h1>

          <p
            style={{
              margin: "10px 0 0",
              color: "#64748b",
              maxWidth: 720,
              lineHeight: 1.6,
            }}
          >
            Pending orders and live platform-owned
            MetaTrader 5 positions in one trading
            workspace.
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadPositions(true)}
          disabled={refreshing}
          style={buttonStyle("#cbd5e1")}
        >
          <RefreshCw size={16} />
          {refreshing
            ? "Refreshing..."
            : "Refresh trading state"}
        </button>
      </div>

      {error && (
        <div
          style={{
            marginBottom: 18,
            padding: 14,
            borderRadius: 12,
            background: "rgba(239,68,68,.10)",
            border:
              "1px solid rgba(239,68,68,.25)",
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
            "repeat(auto-fit,minmax(180px,1fr))",
          gap: 14,
          marginBottom: 24,
        }}
      >
        <Metric
          label="Open positions"
          value={summary.open_trades}
        />

        <Metric
          label="Pending orders"
          value={pendingOrders.length}
        />

        <Metric
          label="Total volume"
          value={number(summary.total_volume, 2)}
        />

        <Metric
          label="Floating P/L"
          value={money(floatingProfit)}
        />
      </div>

      <section
        style={{
          background: "#020617",
          border:
            "1px solid rgba(245,158,11,.18)",
          borderRadius: 20,
          padding: 20,
          marginBottom: 20,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 18,
          }}
        >
          <div>
            <span
              style={{
                color: "#f59e0b",
                fontSize: 10,
                textTransform: "uppercase",
                fontWeight: 800,
              }}
            >
              Execution queue
            </span>

            <h2
              style={{
                margin: "5px 0 0",
                color: "#f8fafc",
                fontSize: 18,
              }}
            >
              Pending Orders
            </h2>
          </div>

          <Badge tone="pending">
            {pendingOrders.length} ACTIVE
          </Badge>
        </div>

        {pendingOrders.length === 0 ? (
          <div
            style={{
              padding: 20,
              color: "#64748b",
              fontSize: 12,
              textAlign: "center",
            }}
          >
            No active pending orders.
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(300px,1fr))",
              gap: 14,
            }}
          >
            {pendingOrders.map((order) => (
              <div
                key={order.intent_id}
                style={{
                  background: "#0f172a",
                  border:
                    "1px solid rgba(245,158,11,.14)",
                  borderRadius: 14,
                  padding: 15,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                  }}
                >
                  <strong
                    style={{
                      color: "#f8fafc",
                      fontSize: 16,
                    }}
                  >
                    {order.broker_symbol ||
                      order.symbol}
                  </strong>

                  <Badge tone="pending">
                    {order.order_type}
                  </Badge>
                </div>

                <div
                  style={{
                    color: "#64748b",
                    fontSize: 10,
                    marginTop: 5,
                  }}
                >
                  Order #{order.order_ticket}
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(2,minmax(0,1fr))",
                    gap: 8,
                    marginTop: 13,
                  }}
                >
                  <Metric
                    label="Entry"
                    value={number(
                      order.entry_price,
                    )}
                  />

                  <Metric
                    label="Volume"
                    value={number(
                      order.volume,
                      2,
                    )}
                  />

                  <Metric
                    label="SL"
                    value={number(
                      order.stop_loss,
                    )}
                  />

                  <Metric
                    label="TP"
                    value={number(
                      order.take_profit,
                    )}
                  />
                </div>

                <div
                  style={{
                    marginTop: 12,
                    color: "#fbbf24",
                    fontSize: 10,
                  }}
                >
                  Waiting for MT5 activation Â·{" "}
                  {dateTime(order.placed_at)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section
        style={{
          background: "#020617",
          border:
            "1px solid rgba(148,163,184,.12)",
          borderRadius: 20,
          padding: 20,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 18,
          }}
        >
          <div>
            <span
              style={{
                color: "#38bdf8",
                fontSize: 10,
                textTransform: "uppercase",
                fontWeight: 800,
              }}
            >
              Broker positions
            </span>

            <h2
              style={{
                margin: "5px 0 0",
                color: "#f8fafc",
                fontSize: 18,
              }}
            >
              Open Positions
            </h2>
          </div>

          <Badge tone="live">
            LIVE MT5
          </Badge>
        </div>

        {loading ? (
          <div
            style={{
              padding: 30,
              textAlign: "center",
              color: "#64748b",
            }}
          >
            Loading live MT5 positions...
          </div>
        ) : positions.length === 0 ? (
          <div
            style={{
              padding: 30,
              textAlign: "center",
              color: "#64748b",
            }}
          >
            No open platform-owned positions.
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(320px,1fr))",
              gap: 16,
            }}
          >
            {positions.map((position) => (
              <PositionCard
                key={position.ticket}
                position={position}
                tick={liveTicks[position.symbol]}
                management={
                  management[position.ticket]
                }
                onEvaluate={evaluate}
                onExecute={execute}
                onActions={loadActions}
              />
            ))}
          </div>
        )}
      </section>

      <div
        style={{
          marginTop: 18,
          display: "flex",
          gap: 8,
          color: "#64748b",
          fontSize: 11,
          lineHeight: 1.5,
        }}
      >
        <ShieldCheck
          size={15}
          style={{ flexShrink: 0 }}
        />

        <span>
          Live prices are read directly from the
          existing MT5 tick endpoint every 250ms.
          Position state remains broker-authoritative
          and is reconciled independently.
        </span>
      </div>
    </section>
  );
}











