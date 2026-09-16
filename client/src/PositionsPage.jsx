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

function formatDate(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return date.toLocaleString();
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

function DecisionBadge({ decision }) {
  const configuration = {
    HOLD: {
      color: "#94a3b8",
      background: "rgba(148, 163, 184, 0.10)",
      icon: Clock3,
    },
    MOVE_SL: {
      color: "#38bdf8",
      background: "rgba(56, 189, 248, 0.10)",
      icon: ShieldCheck,
    },
    PARTIAL_CLOSE: {
      color: "#f59e0b",
      background: "rgba(245, 158, 11, 0.10)",
      icon: TrendingDown,
    },
    CLOSE_POSITION: {
      color: "#ef4444",
      background: "rgba(239, 68, 68, 0.10)",
      icon: XCircle,
    },
  };

  const config =
    configuration[decision] ||
    configuration.HOLD;

  const Icon = config.icon;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "7px",
        padding: "7px 11px",
        borderRadius: "999px",
        color: config.color,
        background: config.background,
        fontSize: "11px",
        fontWeight: 800,
        letterSpacing: "0.04em",
      }}
    >
      <Icon size={14} />

      {decision || "UNKNOWN"}
    </span>
  );
}

function ActionStatusBadge({ status }) {
  const configuration = {
    reconciled: {
      color: "#22c55e",
      background: "rgba(34, 197, 94, 0.10)",
      icon: CheckCircle2,
    },
    already_applied: {
      color: "#22c55e",
      background: "rgba(34, 197, 94, 0.10)",
      icon: CheckCircle2,
    },
    failed: {
      color: "#ef4444",
      background: "rgba(239, 68, 68, 0.10)",
      icon: XCircle,
    },
    sent_reconciliation_required: {
      color: "#f59e0b",
      background: "rgba(245, 158, 11, 0.10)",
      icon: AlertTriangle,
    },
    executing: {
      color: "#38bdf8",
      background: "rgba(56, 189, 248, 0.10)",
      icon: RefreshCw,
    },
    created: {
      color: "#94a3b8",
      background: "rgba(148, 163, 184, 0.10)",
      icon: Clock3,
    },
    duplicate_blocked: {
      color: "#a78bfa",
      background: "rgba(167, 139, 250, 0.10)",
      icon: ShieldCheck,
    },
  };

  const config =
    configuration[status] ||
    configuration.created;

  const Icon = config.icon;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 9px",
        borderRadius: "999px",
        color: config.color,
        background: config.background,
        fontSize: "10px",
        fontWeight: 800,
      }}
    >
      <Icon size={13} />

      {String(status || "unknown").replaceAll(
        "_",
        " ",
      )}
    </span>
  );
}

function ManagementPanel({
  position,
  management,
  onEvaluate,
  onExecute,
  onLoadActions,
}) {
  const evaluation = management?.evaluation;
  const actions = management?.actions || [];

  const evaluating = management?.evaluating === true;
  const executing = management?.executing === true;
  const loadingActions =
    management?.loadingActions === true;

  const error = management?.error || "";

  const canExecute =
    evaluation &&
    evaluation.decision &&
    evaluation.decision !== "HOLD" &&
    evaluation.ai_management_enabled === true;

  return (
    <div
      style={{
        borderTop:
          "1px solid rgba(148, 163, 184, 0.10)",
        paddingTop: "18px",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <BrainCircuit
            size={17}
            color="#38bdf8"
          />

          <strong
            style={{
              color: "#e2e8f0",
              fontSize: "14px",
            }}
          >
            AI Trade Management
          </strong>
        </div>

        <span
          style={{
            color: "#64748b",
            fontSize: "11px",
          }}
        >
          Ticket #{position.ticket}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          gap: "9px",
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={() => onEvaluate(position.ticket)}
          disabled={evaluating || executing}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "7px",
            border:
              "1px solid rgba(56, 189, 248, 0.25)",
            background:
              "rgba(56, 189, 248, 0.08)",
            color: "#7dd3fc",
            borderRadius: "10px",
            padding: "9px 12px",
            cursor:
              evaluating || executing
                ? "not-allowed"
                : "pointer",
            opacity:
              evaluating || executing ? 0.6 : 1,
          }}
        >
          <BrainCircuit size={15} />

          {evaluating
            ? "Evaluating..."
            : "Evaluate AI management"}
        </button>

        <button
          type="button"
          onClick={() =>
            onLoadActions(position.ticket)
          }
          disabled={
            loadingActions ||
            evaluating ||
            executing
          }
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "7px",
            border:
              "1px solid rgba(148, 163, 184, 0.18)",
            background: "#0f172a",
            color: "#cbd5e1",
            borderRadius: "10px",
            padding: "9px 12px",
            cursor:
              loadingActions ||
              evaluating ||
              executing
                ? "not-allowed"
                : "pointer",
            opacity:
              loadingActions ||
              evaluating ||
              executing
                ? 0.6
                : 1,
          }}
        >
          <Clock3 size={15} />

          {loadingActions
            ? "Loading..."
            : "Action history"}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: "10px 12px",
            borderRadius: "10px",
            background:
              "rgba(239, 68, 68, 0.08)",
            border:
              "1px solid rgba(239, 68, 68, 0.20)",
            color: "#fca5a5",
            fontSize: "12px",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}

      {evaluation && (
        <div
          style={{
            background: "#020617",
            border:
              "1px solid rgba(148, 163, 184, 0.12)",
            borderRadius: "14px",
            padding: "14px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            <DecisionBadge
              decision={evaluation.decision}
            />

            <span
              style={{
                color:
                  evaluation.ai_management_enabled
                    ? "#22c55e"
                    : "#ef4444",
                fontSize: "11px",
                fontWeight: 700,
              }}
            >
              AI management{" "}
              {evaluation.ai_management_enabled
                ? "enabled"
                : "disabled"}
            </span>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(125px, 1fr))",
              gap: "9px",
            }}
          >
            <Metric
              label="Current R"
              value={
                evaluation.current_r !== null &&
                evaluation.current_r !== undefined
                  ? `${formatNumber(
                      evaluation.current_r,
                      2,
                    )}R`
                  : "--"
              }
            />

            <Metric
              label="Proposed SL"
              value={
                evaluation.proposed_stop_loss !==
                  null &&
                evaluation.proposed_stop_loss !==
                  undefined
                  ? formatNumber(
                      evaluation.proposed_stop_loss,
                      5,
                    )
                  : "--"
              }
            />

            <Metric
              label="Partial close"
              value={
                evaluation.partial_close_percent !==
                  null &&
                evaluation.partial_close_percent !==
                  undefined
                  ? `${formatNumber(
                      evaluation.partial_close_percent,
                      2,
                    )}%`
                  : "--"
              }
            />

            <Metric
              label="Profile"
              value={
                evaluation.profile_name || "--"
              }
            />
          </div>

          <div
            style={{
              color: "#94a3b8",
              fontSize: "12px",
              lineHeight: 1.55,
            }}
          >
            {evaluation.message}
          </div>

          {evaluation.warnings?.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "5px",
                color: "#fbbf24",
                fontSize: "11px",
              }}
            >
              {evaluation.warnings.map(
                (warning, index) => (
                  <span key={index}>
                    • {warning}
                  </span>
                ),
              )}
            </div>
          )}

          {evaluation.errors?.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "5px",
                color: "#fca5a5",
                fontSize: "11px",
              }}
            >
              {evaluation.errors.map(
                (item, index) => (
                  <span key={index}>
                    • {item}
                  </span>
                ),
              )}
            </div>
          )}

          {canExecute && (
            <button
              type="button"
              onClick={() =>
                onExecute(
                  position.ticket,
                  evaluation,
                )
              }
              disabled={executing}
              style={{
                width: "100%",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                border:
                  evaluation.decision ===
                  "CLOSE_POSITION"
                    ? "1px solid rgba(239, 68, 68, 0.35)"
                    : "1px solid rgba(34, 197, 94, 0.30)",
                background:
                  evaluation.decision ===
                  "CLOSE_POSITION"
                    ? "rgba(239, 68, 68, 0.10)"
                    : "rgba(34, 197, 94, 0.10)",
                color:
                  evaluation.decision ===
                  "CLOSE_POSITION"
                    ? "#fca5a5"
                    : "#86efac",
                borderRadius: "10px",
                padding: "11px 13px",
                cursor: executing
                  ? "not-allowed"
                  : "pointer",
                opacity: executing ? 0.6 : 1,
                fontWeight: 800,
              }}
            >
              <ShieldCheck size={16} />

              {executing
                ? "Executing through protected pipeline..."
                : `Execute ${evaluation.decision}`}
            </button>
          )}

          {evaluation.decision ===
            "HOLD" && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                color: "#64748b",
                fontSize: "11px",
              }}
            >
              <ShieldCheck size={14} />

              No broker action is currently
              recommended.
            </div>
          )}
        </div>
      )}

      {actions.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <div
            style={{
              color: "#64748b",
              fontSize: "10px",
              fontWeight: 800,
              letterSpacing: "0.10em",
              textTransform: "uppercase",
            }}
          >
            Recent management actions
          </div>

          {actions.slice(0, 5).map((action) => (
            <div
              key={action.id}
              style={{
                display: "grid",
                gridTemplateColumns:
                  "minmax(100px, auto) minmax(0, 1fr) auto",
                alignItems: "center",
                gap: "10px",
                padding: "10px",
                borderRadius: "10px",
                background: "#0f172a",
                border:
                  "1px solid rgba(148, 163, 184, 0.08)",
              }}
            >
              <DecisionBadge
                decision={action.decision}
              />

              <div
                style={{
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    color: "#cbd5e1",
                    fontSize: "11px",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {action.message ||
                    "No action message recorded."}
                </div>

                <div
                  style={{
                    color: "#475569",
                    fontSize: "10px",
                    marginTop: "3px",
                  }}
                >
                  {formatDate(
                    action.created_at,
                  )}
                </div>
              </div>

              <ActionStatusBadge
                status={action.status}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PositionCard({
  position,
  management,
  onEvaluate,
  onExecute,
  onLoadActions,
}) {
  const profit = Number(position.profit || 0);
  const isProfitable = profit > 0;
  const isLosing = profit < 0;

  return (
    <article
      style={{
        background: "#0f172a",
        border:
          "1px solid rgba(148, 163, 184, 0.14)",
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

            <PositionTypeBadge
              type={position.type}
            />
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
          value={formatNumber(
            position.entry_price,
            5,
          )}
        />

        <Metric
          label="Current"
          value={formatNumber(
            position.current_price,
            5,
          )}
        />

        <Metric
          label="Stop Loss"
          value={
            Number(position.stop_loss || 0) > 0
              ? formatNumber(
                  position.stop_loss,
                  5,
                )
              : "Not set"
          }
        />

        <Metric
          label="Take Profit"
          value={
            Number(position.take_profit || 0) > 0
              ? formatNumber(
                  position.take_profit,
                  5,
                )
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

      <ManagementPanel
        position={position}
        management={management}
        onEvaluate={onEvaluate}
        onExecute={onExecute}
        onLoadActions={onLoadActions}
      />
    </article>
  );
}

export default function PositionsPage() {
  const [positions, setPositions] = useState([]);
  const [summary, setSummary] = useState({
    open_trades: 0,
    total_volume: 0,
    floating_profit: 0,
  });

  const [managementByTicket, setManagementByTicket] =
    useState({});

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const updateManagement = useCallback(
    (ticket, patch) => {
      setManagementByTicket((current) => ({
        ...current,
        [ticket]: {
          ...current[ticket],
          ...patch,
        },
      }));
    },
    [],
  );

  const loadActions = useCallback(
    async (positionTicket) => {
      updateManagement(positionTicket, {
        loadingActions: true,
        error: "",
      });

      try {
        const response = await api.get(
          `/api/ai-trade-management/positions/${positionTicket}/actions`,
        );

        updateManagement(positionTicket, {
          actions:
            response?.data?.actions || [],
          loadingActions: false,
        });
      } catch (requestError) {
        updateManagement(positionTicket, {
          loadingActions: false,
          error:
            requestError?.response?.data?.detail ||
            "Unable to load AI management action history.",
        });
      }
    },
    [updateManagement],
  );

  const loadPositions = useCallback(
    async (manual = false) => {
      try {
        if (manual) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }

        setError("");

        const [
          positionsResponse,
          summaryResponse,
        ] = await Promise.all([
          api.get("/api/mt5/positions"),
          api.get("/api/mt5/positions/summary"),
        ]);

        const livePositions =
          positionsResponse?.data?.positions || [];

        setPositions(livePositions);

        setSummary({
          open_trades:
            summaryResponse?.data?.open_trades ?? 0,

          total_volume:
            summaryResponse?.data?.total_volume ?? 0,

          floating_profit:
            summaryResponse?.data?.floating_profit ?? 0,
        });

        const actionResults =
          await Promise.all(
            livePositions.map(async (position) => {
              try {
                const response =
                  await api.get(
                    `/api/ai-trade-management/positions/${position.ticket}/actions`,
                  );

                return {
                  ticket: position.ticket,
                  actions:
                    response?.data?.actions || [],
                };
              } catch {
                return {
                  ticket: position.ticket,
                  actions: [],
                };
              }
            }),
          );

        setManagementByTicket((current) => {
          const next = {
            ...current,
          };

          for (const item of actionResults) {
            next[item.ticket] = {
              ...next[item.ticket],
              actions: item.actions,
              loadingActions: false,
            };
          }

          return next;
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

  const evaluatePosition = useCallback(
    async (positionTicket) => {
      updateManagement(positionTicket, {
        evaluating: true,
        error: "",
      });

      try {
        const response = await api.get(
          `/api/ai-trade-management/positions/${positionTicket}/evaluate`,
        );

        updateManagement(positionTicket, {
          evaluation: response.data,
          evaluating: false,
        });

        await loadActions(positionTicket);
      } catch (requestError) {
        updateManagement(positionTicket, {
          evaluating: false,
          error:
            requestError?.response?.data?.detail ||
            "Unable to evaluate AI trade management.",
        });
      }
    },
    [loadActions, updateManagement],
  );

  const executePosition = useCallback(
    async (positionTicket, evaluation) => {
      const decision = evaluation?.decision;

      if (
        !decision ||
        decision === "HOLD"
      ) {
        return;
      }

      const confirmationMessage =
        decision === "CLOSE_POSITION"
          ? `AI management recommends CLOSE_POSITION for ticket #${positionTicket}. This can close the live MT5 position. Continue?`
          : `AI management recommends ${decision} for ticket #${positionTicket}. The backend will re-evaluate the live position immediately before execution. Continue?`;

      const confirmed = window.confirm(
        confirmationMessage,
      );

      if (!confirmed) {
        return;
      }

      updateManagement(positionTicket, {
        executing: true,
        error: "",
      });

      try {
        const response = await api.post(
          `/api/ai-trade-management/positions/${positionTicket}/execute`,
        );

        updateManagement(positionTicket, {
          executing: false,
          lastExecution: response.data,
          evaluation:
            response?.data?.evaluation ||
            evaluation,
        });

        await loadPositions(true);
        await loadActions(positionTicket);
      } catch (requestError) {
        updateManagement(positionTicket, {
          executing: false,
          error:
            requestError?.response?.data?.detail ||
            "AI management execution failed.",
        });

        await loadActions(positionTicket);
      }
    },
    [
      loadActions,
      loadPositions,
      updateManagement,
    ],
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
              fontSize:
                "clamp(26px, 5vw, 38px)",
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
            positions, evaluate the live management
            state, review previous actions and explicitly
            authorize controlled management execution.
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
            border:
              "1px solid rgba(148, 163, 184, 0.18)",
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
            background:
              "rgba(239, 68, 68, 0.10)",
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
                There are currently no active
                AI-managed positions on MetaTrader 5.
                New positions will appear here
                automatically after a confirmed
                execution.
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
                management={
                  managementByTicket[
                    position.ticket
                  ]
                }
                onEvaluate={evaluatePosition}
                onExecute={executePosition}
                onLoadActions={loadActions}
              />
            ))}
          </div>
        )}
      </section>

      <div
        style={{
          marginTop: "18px",
          display: "flex",
          alignItems: "flex-start",
          gap: "8px",
          color: "#64748b",
          fontSize: "11px",
          lineHeight: 1.5,
        }}
      >
        <ShieldCheck
          size={15}
          style={{
            flexShrink: 0,
            marginTop: "1px",
          }}
        />

        <span>
          AI management execution remains behind the
          protected backend orchestration boundary. The
          frontend never sends MT5 orders directly. Every
          execution request is re-evaluated against live
          broker state before the backend can send the
          approved management action.
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