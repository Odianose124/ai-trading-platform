import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Clock3,
  RefreshCw,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import api from "./services/api";
import TradeReviewPanel from "./TradeReviewPanel";
import "./trading.css";

const SYMBOL = "XAUUSD";
const TIMEFRAME = "15m";

const setupParams = {
  timeframe: TIMEFRAME,
  limit: 500,
  strength: 2,
  lookback: 20,
  minimum_touches: 2,
};

function TradingPage() {
  const [setup, setSetup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadSetup = useCallback(async (manual = false) => {
    try {
      if (manual) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError("");

      const response = await api.get(
        `/api/mt5/trade-setup/${SYMBOL}`,
        {
          params: setupParams,
        },
      );

      setSetup(response.data);
      setLastUpdated(new Date());
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          requestError?.response?.data?.message ||
          "Unable to load the live trading setup.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    async function initialLoad() {
      if (!mounted) {
        return;
      }

      await loadSetup(false);
    }

    initialLoad();

    const interval = window.setInterval(() => {
      if (mounted) {
        loadSetup(false);
      }
    }, 10000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [loadSetup]);

  const setupStatus = String(
    setup?.setup_status ||
      setup?.signal ||
      "loading",
  ).toLowerCase();

  const isTradeReady = useMemo(() => {
    return (
      setupStatus === "ready" ||
      setupStatus === "valid" ||
      setupStatus === "executable" ||
      setupStatus === "trade_ready"
    );
  }, [setupStatus]);

  const isNoTrade = useMemo(() => {
    return (
      setupStatus === "no_trade" ||
      setup?.signal === "no_trade"
    );
  }, [setupStatus, setup]);

  const direction = String(
    setup?.direction ||
      setup?.execution_direction ||
      setup?.trade_direction ||
      "neutral",
  ).toLowerCase();

  const marketCondition =
    setup?.market_condition || "unknown";

  const confidence =
    setup?.confidence ?? null;

  const setupQuality =
    setup?.setup_quality || "unknown";

  const currentPrice =
    setup?.market?.current_price ??
    setup?.market?.ask ??
    setup?.market?.bid ??
    null;

  const entryPrice =
    setup?.entry_price ?? null;

  const stopLoss =
    setup?.stop_loss ?? null;

  const takeProfit1 =
    setup?.take_profit_1 ?? null;

  const takeProfit2 =
    setup?.take_profit_2 ?? null;

  const rr1 =
    setup?.risk_reward_1 ??
    setup?.risk_reward_tp1 ??
    setup?.rr_tp1 ??
    null;

  const rr2 =
    setup?.risk_reward_2 ??
    setup?.risk_reward_tp2 ??
    setup?.rr_tp2 ??
    null;

  const warnings = Array.isArray(setup?.warnings)
    ? setup.warnings
    : [];

  const reasons = Array.isArray(setup?.reasons)
    ? setup.reasons
    : [];

  const confirmations =
    setup?.confirmations &&
    typeof setup.confirmations === "object"
      ? setup.confirmations
      : {};

  const evidence =
    setup?.evidence &&
    typeof setup.evidence === "object"
      ? setup.evidence
      : {};

  const executionZone =
    setup?.execution_zone_analysis &&
    typeof setup.execution_zone_analysis === "object"
      ? setup.execution_zone_analysis
      : {};

  return (
    <section className="page trading-page">
      <div className="trading-page-header">
        <div>
          <div className="trading-eyebrow">
            <Activity size={15} />
            Trading intelligence
          </div>

          <h1>Trade Setup Monitor</h1>

          <p>
            Live AI setup validation for {SYMBOL} on the{" "}
            {TIMEFRAME} execution timeframe.
          </p>
        </div>

        <button
          className="trading-refresh-button"
          onClick={() => loadSetup(true)}
          disabled={refreshing}
        >
          <RefreshCw
            size={17}
            className={refreshing ? "spin" : ""}
          />

          {refreshing ? "Refreshing..." : "Refresh setup"}
        </button>
      </div>

      <div className="trading-safety-banner">
        <ShieldCheck size={20} />

        <div>
          <strong>Execution locked</strong>

          <span>
            This screen monitors and validates setups only.
            No MT5 order can be placed from this page.
          </span>
        </div>
      </div>

      {error && (
        <div className="trading-error">
          <AlertTriangle size={19} />

          <div>
            <strong>Unable to load setup</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      <div className="trading-status-grid">
        <StatusCard
          title="Setup status"
          value={
            loading
              ? "Loading..."
              : formatSetupStatus(setupStatus)
          }
          icon={
            isTradeReady
              ? CheckCircle2
              : isNoTrade
                ? XCircle
                : Activity
          }
          tone={
            isTradeReady
              ? "success"
              : isNoTrade
                ? "danger"
                : "neutral"
          }
        />

        <StatusCard
          title="Direction"
          value={formatDirection(direction)}
          icon={
            direction === "bullish"
              ? ArrowUp
              : direction === "bearish"
                ? ArrowDown
                : Activity
          }
          tone={
            direction === "bullish"
              ? "success"
              : direction === "bearish"
                ? "danger"
                : "neutral"
          }
        />

        <StatusCard
          title="Setup quality"
          value={formatValue(setupQuality)}
          icon={Target}
          tone={
            setupQuality === "excellent" ||
            setupQuality === "good"
              ? "success"
              : setupQuality === "poor"
                ? "danger"
                : "neutral"
          }
        />

        <StatusCard
          title="AI confidence"
          value={
            confidence === null
              ? "--"
              : `${Number(confidence).toFixed(1)}%`
          }
          icon={Activity}
          tone={
            Number(confidence) >= 70
              ? "success"
              : Number(confidence) >= 50
                ? "warning"
                : "danger"
          }
        />
      </div>

      <div
        className={`trading-decision-panel ${
          isNoTrade
            ? "decision-no-trade"
            : isTradeReady
              ? "decision-ready"
              : "decision-neutral"
        }`}
      >
        <div className="decision-icon">
          {isNoTrade ? (
            <XCircle size={30} />
          ) : isTradeReady ? (
            <CheckCircle2 size={30} />
          ) : (
            <Activity size={30} />
          )}
        </div>

        <div className="decision-copy">
          <span>AI execution decision</span>

          <strong>
            {loading
              ? "ANALYZING SETUP"
              : isNoTrade
                ? "NO TRADE"
                : isTradeReady
                  ? "VALID SETUP"
                  : formatSetupStatus(setupStatus)}
          </strong>

          <p>
            {loading
              ? "The platform is reading the live MT5 setup engine."
              : isNoTrade
                ? "The strategy rejected the current market conditions. No trade should be opened."
                : isTradeReady
                  ? "The strategy has produced a setup that can proceed to the next safety-review stage."
                  : "The setup is still being evaluated and is not executable."}
          </p>
        </div>

        <div className="decision-market">
          <span>Market condition</span>
          <strong>
            {formatValue(marketCondition)}
          </strong>
        </div>
      </div>

      <div className="trading-section-heading">
        <div>
          <span>Price structure</span>
          <h2>Setup levels</h2>
        </div>
      </div>

      <div className="trading-levels-grid">
        <LevelCard
          label="Current price"
          value={currentPrice}
        />

        <LevelCard
          label="Entry"
          value={entryPrice}
          highlight={isTradeReady}
        />

        <LevelCard
          label="Stop loss"
          value={stopLoss}
          danger
        />

        <LevelCard
          label="Take profit 1"
          value={takeProfit1}
          success
        />

        <LevelCard
          label="Take profit 2"
          value={takeProfit2}
          success
        />

        <LevelCard
          label="R:R to TP1"
          value={
            rr1 === null
              ? null
              : `${Number(rr1).toFixed(2)}R`
          }
        />

        <LevelCard
          label="R:R to TP2"
          value={
            rr2 === null
              ? null
              : `${Number(rr2).toFixed(2)}R`
          }
        />

        <LevelCard
          label="MT5 symbol"
          value={setup?.mt5_symbol || "--"}
          textValue
        />
      </div>

      <div className="trading-two-column">
        <section className="trading-panel">
          <div className="trading-panel-header">
            <div>
              <span>Validation</span>
              <h2>Why this setup was accepted or rejected</h2>
            </div>
          </div>

          {reasons.length > 0 ? (
            <div className="trading-list">
              {reasons.map((reason, index) => (
                <div
                  className="trading-list-item danger-item"
                  key={`${reason}-${index}`}
                >
                  <XCircle size={17} />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="trading-empty">
              <CheckCircle2 size={18} />
              <span>
                No rejection reason was returned by the
                strategy engine.
              </span>
            </div>
          )}
        </section>

        <section className="trading-panel">
          <div className="trading-panel-header">
            <div>
              <span>Warnings</span>
              <h2>Risk and market warnings</h2>
            </div>
          </div>

          {warnings.length > 0 ? (
            <div className="trading-list">
              {warnings.map((warning, index) => (
                <div
                  className="trading-list-item warning-item"
                  key={`${warning}-${index}`}
                >
                  <AlertTriangle size={17} />
                  <span>{warning}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="trading-empty">
              <CheckCircle2 size={18} />
              <span>
                No additional warnings were returned.
              </span>
            </div>
          )}
        </section>
      </div>

      <div className="trading-two-column">
        <section className="trading-panel">
          <div className="trading-panel-header">
            <div>
              <span>Evidence</span>
              <h2>Market evidence</h2>
            </div>
          </div>

          <div className="evidence-grid">
            <EvidenceItem
              label="Active FVGs"
              value={evidence.active_fvg_count}
            />

            <EvidenceItem
              label="Order blocks"
              value={
                evidence.active_order_block_count
              }
            />

            <EvidenceItem
              label="Liquidity sweeps"
              value={evidence.liquidity_sweep_count}
            />

            <EvidenceItem
              label="Support levels"
              value={evidence.support_count}
            />

            <EvidenceItem
              label="Resistance levels"
              value={evidence.resistance_count}
            />
          </div>
        </section>

        <section className="trading-panel">
          <div className="trading-panel-header">
            <div>
              <span>Confirmations</span>
              <h2>Strategy confirmations</h2>
            </div>
          </div>

          {Object.keys(confirmations).length > 0 ? (
            <div className="confirmation-list">
              {Object.entries(confirmations).map(
                ([key, value]) => (
                  <div
                    className="confirmation-row"
                    key={key}
                  >
                    <span>
                      {formatKey(key)}
                    </span>

                    <strong>
                      {formatConfirmation(value)}
                    </strong>
                  </div>
                ),
              )}
            </div>
          ) : (
            <div className="trading-empty">
              <Activity size={18} />
              <span>
                No confirmation details returned.
              </span>
            </div>
          )}
        </section>
      </div>

      <section className="trading-panel execution-analysis-panel">
        <div className="trading-panel-header">
          <div>
            <span>Execution analysis</span>
            <h2>Entry-zone validation</h2>
          </div>
        </div>

        <div className="execution-analysis-grid">
          <AnalysisMetric
            label="Volatility"
            value={
              executionZone.volatility !== undefined
                ? formatNumber(
                    executionZone.volatility,
                  )
                : null
            }
          />

          <AnalysisMetric
            label="Volatility %"
            value={
              executionZone.volatility_percent !==
              undefined
                ? `${formatNumber(
                    executionZone.volatility_percent,
                  )}%`
                : null
            }
          />

          <AnalysisMetric
            label="Entry distance"
            value={
              executionZone.entry_distance_percent !==
              undefined
                ? `${formatNumber(
                    executionZone.entry_distance_percent,
                  )}%`
                : null
            }
          />

          <AnalysisMetric
            label="Stop distance"
            value={
              executionZone.stop_distance !==
              undefined
                ? formatNumber(
                    executionZone.stop_distance,
                  )
                : null
            }
          />

          <AnalysisMetric
            label="Stop distance %"
            value={
              executionZone.stop_distance_percent !==
              undefined
                ? `${formatNumber(
                    executionZone.stop_distance_percent,
                  )}%`
                : null
            }
          />

          <AnalysisMetric
            label="Zone status"
            value={
              executionZone.selection_status ||
              null
            }
          />

          <AnalysisMetric
            label="Zone combination"
            value={
              executionZone.combination_status ||
              null
            }
          />

          <AnalysisMetric
            label="Waiting status"
            value={
              executionZone.waiting_status ||
              null
            }
          />
        </div>
      </section>

      <TradeReviewPanel
        setup={setup}
        isTradeReady={isTradeReady}
      />
      <div className="trading-bottom-safety">
        <ShieldCheck size={19} />

        <div>
          <strong>
            No live order has been requested
          </strong>

          <span>
            The current Trading milestone only monitors
            the strategy output. MT5 execution remains
            behind the separate preview, confirmation,
            broker-validation and order_check safety
            pipeline.
          </span>
        </div>
      </div>

      <div className="trading-last-updated">
        <Clock3 size={15} />

        Last updated:{" "}
        {lastUpdated
          ? lastUpdated.toLocaleTimeString()
          : "Waiting for data"}
      </div>
    </section>
  );
}

function StatusCard({
  title,
  value,
  icon: Icon,
  tone = "neutral",
}) {
  return (
    <div className={`trading-status-card ${tone}`}>
      <div className="status-card-icon">
        <Icon size={20} />
      </div>

      <div>
        <span>{title}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function LevelCard({
  label,
  value,
  highlight = false,
  danger = false,
  success = false,
  textValue = false,
}) {
  const classNames = [
    "level-card",
    highlight ? "highlight" : "",
    danger ? "danger" : "",
    success ? "success" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classNames}>
      <span>{label}</span>

      <strong>
        {textValue
          ? value || "--"
          : value === null ||
              value === undefined ||
              Number(value) === 0
            ? "--"
            : formatNumber(value)}
      </strong>
    </div>
  );
}

function EvidenceItem({ label, value }) {
  return (
    <div className="evidence-item">
      <span>{label}</span>
      <strong>
        {value === undefined ||
        value === null
          ? "--"
          : value}
      </strong>
    </div>
  );
}

function AnalysisMetric({ label, value }) {
  return (
    <div className="analysis-metric">
      <span>{label}</span>
      <strong>
        {value === null ||
        value === undefined ||
        value === ""
          ? "--"
          : formatValue(value)}
      </strong>
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

function formatValue(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "--";
  }

  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    );
}

function formatDirection(direction) {
  if (direction === "bullish") {
    return "Bullish";
  }

  if (direction === "bearish") {
    return "Bearish";
  }

  return "Neutral";
}

function formatSetupStatus(status) {
  return formatValue(status)
    .replace(/\bNo Trade\b/i, "NO TRADE")
    .replace(/\bTrade Ready\b/i, "VALID SETUP");
}

function formatKey(value) {
  return formatValue(value);
}

function formatConfirmation(value) {
  if (typeof value === "boolean") {
    return value ? "Confirmed" : "Not confirmed";
  }

  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "--";
  }

  return formatValue(value);
}

export default TradingPage;

