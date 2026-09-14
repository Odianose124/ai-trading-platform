import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  ChevronRight,
  Clock3,
  Menu,
  PanelLeftClose,
  RefreshCw,
  Settings,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import api from "./services/api";
import TradeHistoryPage from "./TradeHistoryPage";
import MarketsPage from "./MarketsPage";
import AIAnalysisPage from "./AIAnalysisPage";
import TradingPage from "./TradingPage";
import LoginPage from "./LoginPage.jsx";
import PositionsPage from "./PositionsPage.jsx";
import "./App.css";

const navigation = [
  {
    to: "/",
    label: "Command Center",
    icon: Activity,
  },
  {
    to: "/markets",
    label: "Markets",
    icon: BarChart3,
  },
  {
    to: "/ai-analysis",
    label: "AI Analysis",
    icon: Bot,
  },
  {
    to: "/trading",
    label: "Trading",
    icon: TrendingUp,
  },
  {
    to: "/positions",
    label: "Positions",
    icon: BriefcaseBusiness,
  },
  {
    to: "/history",
    label: "Trade History",
    icon: Clock3,
  },
  {
    to: "/settings",
    label: "Settings",
    icon: Settings,
  },
];

function App() {
  return (
    <BrowserRouter>
      <AuthenticationGate />
    </BrowserRouter>
  );
}

function AuthenticationGate() {
  const [authState, setAuthState] = useState("checking");
  const [user, setUser] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function validateSession() {
      const token = localStorage.getItem(
        "ai_trading_access_token",
      );

      if (!token) {
        if (mounted) {
          setAuthState("unauthenticated");
          setUser(null);
        }

        return;
      }

      try {
        const response = await api.get(
          "/api/auth/me",
        );

        if (!mounted) {
          return;
        }

        setUser(response.data);
        setAuthState("authenticated");
      } catch {
        localStorage.removeItem(
          "ai_trading_access_token",
        );

        if (mounted) {
          setUser(null);
          setAuthState("unauthenticated");
        }
      }
    }

    validateSession();

    return () => {
      mounted = false;
    };
  }, []);

  if (authState === "checking") {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#020617",
          color: "#94a3b8",
          fontFamily:
            "Inter, system-ui, sans-serif",
        }}
      >
        Checking secure session...
      </div>
    );
  }

  if (authState === "unauthenticated") {
    return (
      <Routes>
        <Route
          path="/login"
          element={<LoginPage />}
        />

        <Route
          path="*"
          element={
            <Navigate
              to="/login"
              replace
              state={{
                from: {
                  pathname:
                    window.location.pathname,
                },
              }}
            />
          }
        />
      </Routes>
    );
  }

  return <TradingApplication user={user} />;
}

function TradingApplication() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [mt5Status, setMt5Status] = useState("checking");

  useEffect(() => {
    let mounted = true;

    async function checkServices() {
      try {
        await api.get("/");

        if (mounted) {
          setBackendStatus("online");
        }
      } catch {
        if (mounted) {
          setBackendStatus("offline");
        }
      }

      try {
        const response = await api.get("/api/mt5/status");

        if (mounted) {
          const connected =
            response?.data?.connected === true ||
            response?.data?.status === "connected";

          setMt5Status(
            connected ? "connected" : "disconnected",
          );
        }
      } catch {
        if (mounted) {
          setMt5Status("disconnected");
        }
      }
    }

    checkServices();

    const interval = window.setInterval(
      checkServices,
      15000,
    );

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div className="app-shell">
      <aside
        className={`sidebar ${
          mobileMenuOpen ? "sidebar-open" : ""
        }`}
      >
        <div className="sidebar-header">
          <div className="brand-mark">
            <Bot size={21} />
          </div>

          <div className="brand-copy">
            <strong>AI Trader</strong>
            <span>Trading Intelligence</span>
          </div>

          <button
            className="icon-button mobile-close"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        <div className="connection-panel">
          <ConnectionStatus
            label="Backend"
            status={backendStatus}
          />

          <ConnectionStatus
            label="MT5"
            status={mt5Status}
          />
        </div>

        <nav className="main-navigation">
          {navigation.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `navigation-link ${
                    isActive ? "active" : ""
                  }`
                }
              >
                <Icon size={19} />

                <span>{item.label}</span>

                <ChevronRight
                  size={16}
                  className="navigation-arrow"
                />
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="security-badge">
            <ShieldCheck size={17} />

            <div>
              <strong>Trading safety</strong>
              <span>Risk controls enabled</span>
            </div>
          </div>
        </div>
      </aside>

      {mobileMenuOpen && (
        <button
          className="mobile-overlay"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Close navigation"
        />
      )}

      <main className="main-content">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={21} />
          </button>

          <div className="topbar-title">
            <span>AI Trading Platform</span>
            <strong>Live Market Intelligence</strong>
          </div>

          <div className="topbar-status">
            <span
              className={`status-dot ${
                backendStatus === "online"
                  ? "online"
                  : ""
              }`}
            />

            <span>
              {backendStatus === "online"
                ? "System online"
                : backendStatus === "checking"
                  ? "Checking"
                  : "Backend offline"}
            </span>
          </div>
        </header>

        <div className="page-container">
          <Routes>
            <Route
              path="/"
              element={<CommandCenter />}
            />

            <Route
              path="/markets"
              element={<MarketsPage />}
            />

            <Route
  path="/ai-analysis"
  element={<AIAnalysisPage />}
/>

            <Route
              path="/trading"
              element={<TradingPage />}
            />

            <Route
              path="/positions"
              element={<PositionsPage />}
            />

            <Route
              path="/history"
              element={<TradeHistoryPage />}
            />

            <Route
              path="/settings"
              element={<SettingsPage />}
            />

            <Route
              path="*"
              element={<Navigate to="/" replace />}
            />
          </Routes>
        </div>
      </main>
    </div>
  );
}

function ConnectionStatus({ label, status }) {
  const text =
    status === "connected" || status === "online"
      ? "Connected"
      : status === "checking"
        ? "Checking..."
        : "Unavailable";

  return (
    <div className="connection-row">
      <span>{label}</span>

      <span className="connection-value">
        <span
          className={`status-dot ${
            status === "connected" ||
            status === "online"
              ? "online"
              : ""
          }`}
        />

        {text}
      </span>
    </div>
  );
}

function AccountMetric({
  label,
  value,
  suffix = "",
  prefix = "",
  profit = false,
}) {
  const numericValue =
    value === null ||
    value === undefined ||
    value === ""
      ? null
      : Number(value);

  const displayValue =
    numericValue === null ||
    Number.isNaN(numericValue)
      ? "--"
      : `${prefix}${numericValue.toLocaleString(
          undefined,
          {
            minimumFractionDigits:
              numericValue % 1 === 0 ? 0 : 2,
            maximumFractionDigits: 2,
          },
        )}${suffix}`;

  const profitClass =
    profit && numericValue !== null
      ? numericValue > 0
        ? "account-profit-positive"
        : numericValue < 0
          ? "account-profit-negative"
          : ""
      : "";

  return (
    <div className="account-metric-card">
      <span>{label}</span>

      <strong className={profitClass}>
        {displayValue}
      </strong>
    </div>
  );
}
function CommandCenter() {
  const [prices, setPrices] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [mtf, setMtf] = useState(null);
  const [accountStatus, setAccountStatus] = useState(null);
  const [positionSummary, setPositionSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    async function loadCommandCenter() {
      try {
        setError("");

        const [
          priceResponse,
          analysisResponse,
          mtfResponse,
          accountResponse,
          positionsResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),

          api.get(
            "/api/mt5/market-data/analysis/ai/XAUUSD/15m",
            {
              params: {
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/analysis/multi-timeframe/XAUUSD",
            {
              params: {
                primary_timeframe: "15m",
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/status",
          ),

          api.get(
            "/api/mt5/positions/summary",
          ),
        ]);

        if (!mounted) {
          return;
        }

        setPrices(priceResponse.data);
        setAnalysis(analysisResponse.data);
        setMtf(mtfResponse.data);
        setAccountStatus(accountResponse.data);
        setPositionSummary(positionsResponse.data);
      } catch (requestError) {
        if (!mounted) {
          return;
        }

        setError(
          requestError?.response?.data?.detail ||
            "Unable to load live trading intelligence.",
        );
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadCommandCenter();

    const interval = window.setInterval(
      loadCommandCenter,
      15000,
    );

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const aiBias =
    analysis?.overall_bias || "neutral";

  const aiConfidence =
    analysis?.confidence ?? null;

  const mtfBias =
    mtf?.overall_bias || "neutral";

  const executionBias =
    mtf?.execution_timeframe_bias ||
    "neutral";

  const higherTimeframeBias =
    mtf?.higher_timeframe_bias ||
    "neutral";

  const marketCondition =
    analysis?.market_condition ||
    "range_or_uncertain";

  const decision = getDecision(
    aiBias,
    aiConfidence,
  );

  const account =
    accountStatus?.account || {};

  const accountBalance =
    account.balance ?? null;

  const accountEquity =
    account.equity ?? null;

  const accountFreeMargin =
    account.free_margin ?? null;

  const accountMargin =
    account.margin ?? null;

  const accountMarginLevel =
    accountMargin && Number(accountMargin) > 0
      ? (Number(accountEquity || 0) / Number(accountMargin)) * 100
      : null;

  const openPositions =
    positionSummary?.open_trades ??
    positionSummary?.count ??
    0;

  const floatingProfit =
    positionSummary?.floating_profit ??
    0;

  return (
    <section className="page">
      <PageHeading
        eyebrow="Command Center"
        title="Your AI trading command center"
        description="Live market intelligence, multi-timeframe context and execution awareness in one place."
      />

      {error && <ErrorBanner message={error} />}

      <div className="hero-grid">
        <section className="ai-decision-card">
          <div className="card-label">
            <span className="live-indicator" />
            AI market decision
          </div>

          <div className="decision-main">
            <div>
              <span className="instrument-label">
                XAUUSD · 15m
              </span>

              <h2 className={biasClass(aiBias)}>
                {loading
                  ? "Reading..."
                  : formatBias(aiBias)}
              </h2>

              {!loading && (
                <div className="decision-description">
                  {formatBias(marketCondition)}
                </div>
              )}
            </div>

            <div className="confidence-ring">
              {aiConfidence === null
                ? "--"
                : `${Number(aiConfidence).toFixed(1)}%`}

              <span>confidence</span>
            </div>
          </div>

          <div className="decision-description">
            {loading ? (
              "Reading live market conditions..."
            ) : (
              <DecisionMessage
                analysis={analysis}
                mtf={mtf}
                decision={decision}
              />
            )}
          </div>

          <div className="decision-footer">
            <span>
              <Activity size={16} />
              Live analysis
            </span>

            <span>
              <TrendingUp size={16} />
              MTF confirmation
            </span>
          </div>
        </section>

        <section className="market-overview-card">
          <div className="section-heading">
            <div>
              <span className="card-label">
                Live prices
              </span>

              <h3>Market overview</h3>
            </div>
          </div>

          <div className="price-list">
            {[
              "XAUUSD",
              "BTCUSD",
              "EURUSD",
            ].map((symbol) => {
              const item =
                prices?.prices?.[symbol];

              return (
                <PriceRow
                  key={symbol}
                  symbol={symbol}
                  data={item}
                  loading={loading}
                />
              );
            })}
          </div>
        </section>
      </div>

      <div className="section-title-row account-snapshot-heading">
        <div>
          <span className="card-label">
            Live account
          </span>

          <h3>MT5 account snapshot</h3>
        </div>

        <span className="account-live-badge">
          <span className="live-indicator" />
          Live
        </span>
      </div>

      <div className="account-snapshot-grid">
        <AccountMetric
          label="Balance"
          value={accountBalance}
          suffix=" USD"
        />

        <AccountMetric
          label="Equity"
          value={accountEquity}
          suffix=" USD"
        />

        <AccountMetric
          label="Free margin"
          value={accountFreeMargin}
          suffix=" USD"
        />

        <AccountMetric
          label="Used margin"
          value={accountMargin}
          suffix=" USD"
        />

        <AccountMetric
          label="Margin level"
          value={accountMarginLevel}
          suffix="%"
        />

        <AccountMetric
          label="Open positions"
          value={openPositions}
        />

        <AccountMetric
          label="Floating P/L"
          value={floatingProfit}
          suffix=" USD"
          profit
        />

        <AccountMetric
          label="Leverage"
          value={account.leverage}
          prefix="1:"
        />
      </div>

      <div className="section-title-row">
        <div>
          <span className="card-label">
            Intelligence
          </span>

          <h3>What the AI sees</h3>
        </div>
      </div>

      <div className="intelligence-grid">
        <InsightCard
          title="AI market bias"
          value={formatBias(aiBias)}
          description="Final weighted directional assessment."
        />

        <InsightCard
          title="15m execution bias"
          value={formatBias(executionBias)}
          description="Directional assessment for the primary execution timeframe."
        />

        <InsightCard
          title="Higher timeframe"
          value={formatBias(higherTimeframeBias)}
          description="Combined 1h and 4h directional context."
        />

        <InsightCard
          title="Market condition"
          value={formatBias(marketCondition)}
          description="Current market regime and conviction."
        />
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <Bot size={20} />

          <div>
            <h3>Multi-timeframe context</h3>
            <span>
              XAUUSD · live MT5 analysis
            </span>
          </div>
        </div>

        <div className="reasoning-content">
          <ReasoningBlock
            title="Overall MTF bias"
            value={formatBias(mtfBias)}
          />

          <ReasoningBlock
            title="MTF alignment"
            value={
              mtf?.alignment ||
              "No alignment information returned."
            }
          />

          <ReasoningBlock
            title="Higher timeframe"
            value={formatBias(
              higherTimeframeBias,
            )}
          />

          <ReasoningBlock
            title="15m execution timeframe"
            value={formatBias(executionBias)}
          />

          <ReasoningBlock
            title="AI action"
            value={decision}
          />
        </div>
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <Activity size={20} />

          <div>
            <h3>AI evidence</h3>
            <span>
              Structure, liquidity and institutional-style
              market context
            </span>
          </div>
        </div>

        <div className="reasoning-content">
          <ReasoningBlock
            title="Structure"
            value={formatNestedTrend(
              analysis?.market_structure,
              analysis?.trend,
            )}
          />

          <ReasoningBlock
            title="Liquidity"
            value={describeLiquidity(
              analysis?.liquidity,
            )}
          />

          <ReasoningBlock
            title="Fair value gaps"
            value={describeCollection(
              analysis?.fvg,
              "FVG",
            )}
          />

          <ReasoningBlock
            title="Order blocks"
            value={describeCollection(
              analysis?.order_blocks,
              "order block",
            )}
          />

          <ReasoningBlock
            title="Support / resistance"
            value={describeSupportResistance(
              analysis?.support_resistance,
            )}
          />
        </div>
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <ShieldCheck size={20} />

          <div>
            <h3>AI safety interpretation</h3>
            <span>
              The platform does not turn a low-confidence
              bias into an automatic trade.
            </span>
          </div>
        </div>

        <div className="reasoning-content">
          <ReasoningBlock
            title="Decision"
            value={decision}
          />

          <ReasoningBlock
            title="Confirmations"
            value={
              formatList(
                analysis?.confirmations,
              ) ||
              "No directional confirmations returned."
            }
          />

          <ReasoningBlock
            title="Warnings"
            value={
              formatList(
                analysis?.warnings,
              ) ||
              formatList(mtf?.warnings) ||
              "No warnings returned."
            }
          />
        </div>
      </div>
    </section>
  );
}

function Markets() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadMarkets() {
    try {
      setError("");

      const response = await api.get(
        "/api/mt5/market-data/ticks",
      );

      setData(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to load live MT5 prices.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMarkets();

    const interval = window.setInterval(
      loadMarkets,
      10000,
    );

    return () => window.clearInterval(interval);
  }, []);

  const marketPrices = data?.prices || {};

  return (
    <section className="page">
      <PageHeading
        eyebrow="Markets"
        title="Live markets"
        description="Prices are read directly from the connected MetaTrader 5 terminal."
      />

      {error && <ErrorBanner message={error} />}

      <div className="market-grid">
        {Object.entries(marketPrices).map(
          ([symbol, price]) => (
            <MarketCard
              key={symbol}
              symbol={symbol}
              data={price}
              loading={loading}
            />
          ),
        )}
      </div>

      {!loading &&
        Object.keys(marketPrices).length === 0 &&
        !error && (
          <EmptyState
            title="No market data available"
            description="The backend did not return live MT5 market prices."
          />
        )}
    </section>
  );
}
  

/*
|--------------------------------------------------------------------------
| LIVE MT5 POSITIONS
|--------------------------------------------------------------------------
*/

function Positions() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  async function loadPositions(
    manualRefresh = false,
  ) {
    try {
      if (manualRefresh) {
        setRefreshing(true);
      }

      setError("");

      const response = await api.get(
        "/api/mt5/positions",
      );

      setData(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to load live MT5 positions.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadPositions();

    const interval = window.setInterval(
      () => loadPositions(false),
      5000,
    );

    return () =>
      window.clearInterval(interval);
  }, []);

  const positions = Array.isArray(
    data?.positions,
  )
    ? data.positions
    : [];

  const summary = data?.summary || {
    open_trades: 0,
    total_volume: 0,
    floating_profit: 0,
  };

  return (
    <section className="page">
      <div className="page-heading-row">
        <PageHeading
          eyebrow="Positions"
          title="Live open positions"
          description="Real-time positions currently exposed by the connected MetaTrader 5 account."
        />

        <button
          className="secondary-button"
          onClick={() => loadPositions(true)}
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

      {error && <ErrorBanner message={error} />}

      <div className="live-source-banner">
        <span className="live-indicator" />

        <div>
          <strong>
            Live MetaTrader 5 positions
          </strong>

          <span>
            Auto-refreshing every 5 seconds ·
            AI-managed positions only
          </span>
        </div>
      </div>

      <div className="position-summary-grid">
        <PositionSummaryCard
          label="Open trades"
          value={summary.open_trades}
          icon={BriefcaseBusiness}
        />

        <PositionSummaryCard
          label="Total volume"
          value={formatVolume(
            summary.total_volume,
          )}
          icon={BarChart3}
        />

        <PositionSummaryCard
          label="Floating P/L"
          value={formatMoney(
            summary.floating_profit,
          )}
          icon={
            Number(summary.floating_profit) >= 0
              ? TrendingUp
              : TrendingDown
          }
          positive={
            Number(summary.floating_profit) > 0
          }
          negative={
            Number(summary.floating_profit) < 0
          }
        />
      </div>

      <div className="section-title-row">
        <div>
          <span className="card-label">
            MT5 account
          </span>

          <h3>Open positions</h3>
        </div>

        {data?.magic && (
          <span className="position-magic">
            Magic {data.magic}
          </span>
        )}
      </div>

      {loading ? (
        <div className="positions-loading">
          <LoadingText />
        </div>
      ) : positions.length === 0 ? (
        <EmptyState
          title="No open positions"
          description="There are currently no AI-managed positions open on the connected MetaTrader 5 account."
        />
      ) : (
        <div className="positions-list">
          {positions.map((position) => (
            <LivePositionCard
              key={position.ticket}
              position={position}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function PositionSummaryCard({
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

function LivePositionCard({
  position,
}) {
  const isBuy =
    String(position.type || "").toLowerCase() ===
    "buy";

  const profit = Number(
    position.profit || 0,
  );

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
              {position.symbol}
            </strong>

            <span>
              Ticket #{position.ticket}
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
          {isBuy ? "BUY" : "SELL"}
        </div>
      </div>

      <div className="position-details-grid">
        <PositionDetail
          label="Volume"
          value={formatVolume(
            position.volume,
          )}
        />

        <PositionDetail
          label="Entry"
          value={formatNumber(
            position.entry_price,
          )}
        />

        <PositionDetail
          label="Current"
          value={formatNumber(
            position.current_price,
          )}
        />

        <PositionDetail
          label="Stop Loss"
          value={
            Number(position.stop_loss || 0) > 0
              ? formatNumber(
                  position.stop_loss,
                )
              : "Not set"
          }
        />

        <PositionDetail
          label="Take Profit"
          value={
            Number(position.take_profit || 0) > 0
              ? formatNumber(
                  position.take_profit,
                )
              : "Not set"
          }
        />

        <PositionDetail
          label="Swap"
          value={formatMoney(
            position.swap,
          )}
        />
      </div>

      <div className="position-profit-row">
        <span>Floating P/L</span>

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

      <div className="position-card-footer">
        <span>
          MT5 · AI managed
        </span>

        <span>
          Magic {position.magic}
        </span>
      </div>
    </article>
  );
}

function PositionDetail({
  label,
  value,
}) {
  return (
    <div className="position-detail">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TradeHistory() {
  return <TradeHistoryPage />;
}

function SettingsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [action, setAction] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadStatus(manualRefresh = false) {
    try {
      if (manualRefresh) {
        setRefreshing(true);
      }

      setError("");
      setMessage("");

      const response = await api.get(
        "/api/mt5/status",
      );

      setData(response.data);
    } catch (requestError) {
      setData(null);

      setError(
        requestError?.response?.data?.detail ||
          "Unable to load MetaTrader 5 status.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function connectMT5() {
    try {
      setAction("connect");
      setError("");
      setMessage("");

      const response = await api.post(
        "/api/mt5/connect",
      );

      setData(response.data);

      setMessage(
        "MetaTrader 5 connected successfully.",
      );
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to connect to MetaTrader 5.",
      );
    } finally {
      setAction("");
    }
  }

  async function disconnectMT5() {
    try {
      setAction("disconnect");
      setError("");
      setMessage("");

      const response = await api.post(
        "/api/mt5/disconnect",
      );

      setData({
        connected: false,
      });

      setMessage(
        response?.data?.message ||
          "MetaTrader 5 disconnected.",
      );
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to disconnect MetaTrader 5.",
      );
    } finally {
      setAction("");
    }
  }

  useEffect(() => {
    loadStatus();

    const interval = window.setInterval(
      () => loadStatus(false),
      15000,
    );

    return () =>
      window.clearInterval(interval);
  }, []);

  const connected =
    data?.connected === true;

  const account = data?.account || {};
  const terminal = data?.terminal || {};
  const version = data?.version || {};

  return (
    <section className="page">
      <div className="page-heading-row">
        <PageHeading
          eyebrow="Settings"
          title="Platform settings"
          description="Manage the MetaTrader 5 connection and view the live trading account configuration."
        />

        <button
          className="secondary-button"
          onClick={() => loadStatus(true)}
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
        <ErrorBanner message={error} />
      )}

      {message && (
        <div className="live-source-banner">
          <span className="live-indicator" />

          <div>
            <strong>{message}</strong>

            <span>
              MetaTrader 5 connection status
              updated successfully.
            </span>
          </div>
        </div>
      )}

      <div className="live-source-banner">
        <span
          className={`live-indicator ${
            connected ? "" : "status-offline"
          }`}
        />

        <div>
          <strong>
            MetaTrader 5
          </strong>

          <span>
            {loading
              ? "Checking terminal connection..."
              : connected
                ? "Connected to live MT5 terminal"
                : "MT5 terminal is currently unavailable"}
          </span>
        </div>

        <strong
          className={
            connected
              ? "profit-positive"
              : "profit-negative"
          }
        >
          {loading
            ? "Checking..."
            : connected
              ? "CONNECTED"
              : "DISCONNECTED"}
        </strong>
      </div>

      <div className="settings-grid">
        <div className="settings-card">
          <div className="settings-icon">
            <ShieldCheck size={20} />
          </div>

          <div>
            <h3>Connection control</h3>

            <p>
              Connect or disconnect the platform
              from the MetaTrader 5 terminal.
            </p>

            <div
              style={{
                display: "flex",
                gap: "10px",
                flexWrap: "wrap",
                marginTop: "16px",
              }}
            >
              <button
                className="secondary-button"
                onClick={connectMT5}
                disabled={
                  action !== "" ||
                  connected
                }
              >
                <Activity size={17} />

                {action === "connect"
                  ? "Connecting..."
                  : connected
                    ? "Already connected"
                    : "Connect MT5"}
              </button>

              <button
                className="secondary-button"
                onClick={disconnectMT5}
                disabled={
                  action !== "" ||
                  !connected
                }
              >
                <PanelLeftClose size={17} />

                {action === "disconnect"
                  ? "Disconnecting..."
                  : "Disconnect MT5"}
              </button>
            </div>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-icon">
            <Bot size={20} />
          </div>

          <div>
            <h3>AI trading safety</h3>

            <p>
              The execution layer remains responsible
              for trade validation, risk controls and
              AI-managed execution decisions.
            </p>
          </div>
        </div>
      </div>

      {connected && (
        <>
          <div className="section-title-row">
            <div>
              <span className="card-label">
                Live account
              </span>

              <h3>
                MetaTrader 5 account
              </h3>
            </div>
          </div>

          <div className="position-summary-grid">
            <PositionSummaryCard
              label="Balance"
              value={formatMoney(
                account.balance,
              )}
              icon={BriefcaseBusiness}
            />

            <PositionSummaryCard
              label="Equity"
              value={formatMoney(
                account.equity,
              )}
              icon={TrendingUp}
            />

            <PositionSummaryCard
              label="Free margin"
              value={formatMoney(
                account.free_margin,
              )}
              icon={BarChart3}
            />

            <PositionSummaryCard
              label="Leverage"
              value={
                account.leverage
                  ? `1:${account.leverage}`
                  : "--"
              }
              icon={Activity}
            />
          </div>

          <div className="analysis-panel">
            <div className="panel-heading">
              <BriefcaseBusiness size={20} />

              <div>
                <h3>Account information</h3>

                <span>
                  Information returned directly
                  by the connected MT5 terminal
                </span>
              </div>
            </div>

            <div className="reasoning-content">
              <ReasoningBlock
                title="Account"
                value={
                  account.login
                    ? String(account.login)
                    : "Unavailable"
                }
              />

              <ReasoningBlock
                title="Account name"
                value={
                  account.name ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Server"
                value={
                  account.server ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Currency"
                value={
                  account.currency ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Trading allowed"
                value={
                  account.trade_allowed
                    ? "Yes"
                    : "No"
                }
              />

              <ReasoningBlock
                title="Margin"
                value={formatMoney(
                  account.margin,
                )}
              />
            </div>
          </div>

          <div className="analysis-panel">
            <div className="panel-heading">
              <Settings size={20} />

              <div>
                <h3>Terminal information</h3>

                <span>
                  Connected MetaTrader 5 environment
                </span>
              </div>
            </div>

            <div className="reasoning-content">
              <ReasoningBlock
                title="Terminal"
                value={
                  terminal.name ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Company"
                value={
                  terminal.company ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Terminal build"
                value={
                  version.build
                    ? String(version.build)
                    : "Unavailable"
                }
              />

              <ReasoningBlock
                title="Terminal version"
                value={
                  version.terminal
                    ? String(version.terminal)
                    : "Unavailable"
                }
              />

              <ReasoningBlock
                title="Release date"
                value={
                  version.release_date
                    ? String(
                        version.release_date,
                      )
                    : "Unavailable"
                }
              />

              <ReasoningBlock
                title="Terminal path"
                value={
                  terminal.path ||
                  "Unavailable"
                }
              />
            </div>
          </div>
        </>
      )}

      {!loading && !connected && (
        <EmptyState
          title="MetaTrader 5 is not connected"
          description="Connect the MT5 terminal to view the live account configuration and trading status."
        />
      )}
    </section>
  );
}

function PriceRow({
  symbol,
  data,
  loading,
}) {
  if (loading && !data) {
    return (
      <div className="price-row">
        <span>{symbol}</span>
        <span className="skeleton-value" />
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div className="price-row">
        <span>{symbol}</span>

        <span className="muted">
          {data?.error || "Unavailable"}
        </span>
      </div>
    );
  }

  return (
    <div className="price-row">
      <div>
        <strong>{symbol}</strong>

        <span>
          {data.mt5_symbol ||
            data.symbol ||
            symbol}
        </span>
      </div>

      <div className="price-values">
        <strong>
          {formatNumber(data.bid)}
        </strong>

        <span>
          Ask {formatNumber(data.ask)}
        </span>
      </div>
    </div>
  );
}

function MarketCard({
  symbol,
  data,
  loading,
}) {
  return (
    <article className="market-card">
      <div className="market-card-header">
        <div>
          <span className="market-symbol">
            {symbol}
          </span>

          <span className="market-source">
            {data?.mt5_symbol ||
              data?.symbol ||
              "MT5"}
          </span>
        </div>

        <span className="live-pill">
          <span className="live-indicator" />
          Live
        </span>
      </div>

      {loading && !data ? (
        <LoadingText />
      ) : data?.error ? (
        <p className="muted">
          {data.error}
        </p>
      ) : (
        <>
          <div className="market-price">
            {formatNumber(data?.bid)}
          </div>

          <div className="market-details">
            <span>
              Ask {formatNumber(data?.ask)}
            </span>

            <span>
              Spread {formatNumber(data?.spread)}
            </span>
          </div>
        </>
      )}
    </article>
  );
}

function InsightCard({
  title,
  value,
  description,
}) {
  return (
    <article className="insight-card">
      <span>{title}</span>

      <strong>
        {formatValue(value)}
      </strong>

      <p>{description}</p>
    </article>
  );
}

function MetricCard({
  label,
  value,
  loading,
}) {
  return (
    <article className="metric-card">
      <span>{label}</span>

      {loading ? (
        <LoadingText />
      ) : (
        <strong>
          {formatValue(value)}
        </strong>
      )}
    </article>
  );
}

function ReasoningBlock({
  title,
  value,
}) {
  return (
    <div className="reasoning-block">
      <span>{title}</span>
      <p>{formatValue(value)}</p>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  description,
}) {
  return (
    <div className="page-heading">
      <span className="eyebrow">
        {eyebrow}
      </span>

      <h1>{title}</h1>

      <p>{description}</p>
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="error-banner">
      <Activity size={17} />
      <span>{message}</span>
    </div>
  );
}

function EmptyState({
  title,
  description,
}) {
  return (
    <div className="empty-state">
      <BriefcaseBusiness size={25} />

      <h3>{title}</h3>

      <p>{description}</p>
    </div>
  );
}

function LoadingText() {
  return (
    <span className="loading-text">
      Loading live data...
    </span>
  );
}

function DecisionMessage({
  analysis,
  mtf,
  decision,
}) {
  const overallBias =
    analysis?.overall_bias ||
    "neutral";

  const confidence =
    Number(analysis?.confidence || 0);

  const executionBias =
    mtf?.execution_timeframe_bias ||
    "neutral";

  const higherBias =
    mtf?.higher_timeframe_bias ||
    "neutral";

  if (overallBias === "neutral") {
    return (
      "The current evidence is mixed or insufficiently aligned for a reliable directional bias."
    );
  }

  if (
    executionBias !== overallBias &&
    executionBias !== "neutral"
  ) {
    return `${formatBias(
      executionBias,
    )} short-term execution conditions are conflicting with the ${formatBias(
      overallBias,
    )} overall AI bias. ${decision}.`;
  }

  if (
    higherBias !== overallBias &&
    higherBias !== "neutral"
  ) {
    return `${formatBias(
      executionBias,
    )} execution conditions are different from the ${formatBias(
      higherBias,
    )} higher-timeframe context. ${decision}.`;
  }

  if (confidence < 50) {
    return `${formatBias(
      overallBias,
    )} evidence exists, but conviction is low at ${confidence.toFixed(
      1,
    )}%. ${decision}.`;
  }

  if (confidence < 65) {
    return `${formatBias(
      overallBias,
    )} evidence has an advantage, but additional confirmation is required. ${decision}.`;
  }

  return `${formatBias(
    overallBias,
  )} evidence currently has the strongest weighted advantage. ${decision}.`;
}

function getDecision(
  bias,
  confidence,
) {
  const normalized =
    String(bias || "neutral").toLowerCase();

  const numericConfidence =
    Number(confidence || 0);

  if (
    normalized === "neutral" ||
    !["bullish", "bearish"].includes(
      normalized,
    )
  ) {
    return "WAIT — NO CLEAR DIRECTION";
  }

  if (numericConfidence < 50) {
    return "WAIT — LOW CONFIDENCE";
  }

  if (numericConfidence < 65) {
    return "WAIT — CONFIRMATION REQUIRED";
  }

  return `${formatBias(
    normalized,
  )} BIAS — SETUP CONFIRMATION REQUIRED`;
}

function biasClass(value) {
  const normalized =
    String(value).toLowerCase();

  if (normalized.includes("bull")) {
    return "bias-bullish";
  }

  if (normalized.includes("bear")) {
    return "bias-bearish";
  }

  return "bias-neutral";
}

function formatBias(value) {
  const text = String(
    value || "unavailable",
  )
    .replaceAll("_", " ")
    .trim();

  if (!text) {
    return "Unavailable";
  }

  return (
    text.charAt(0).toUpperCase() +
    text.slice(1)
  );
}

function formatValue(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "Unavailable";
  }

  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
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
    numericValue > 0
      ? "+"
      : "";

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

function formatList(value) {
  if (!Array.isArray(value)) {
    return "";
  }

  return value
    .filter(Boolean)
    .map(formatBias)
    .join(" · ");
}

function formatScores(scores) {
  if (!scores) {
    return "No directional scores returned.";
  }

  const bullish =
    Number(scores.bullish || 0);

  const bearish =
    Number(scores.bearish || 0);

  return `Bullish ${bullish.toFixed(
    2,
  )} · Bearish ${bearish.toFixed(2)}`;
}

function formatNestedTrend(
  structure,
  fallback,
) {
  if (!structure) {
    return formatBias(
      fallback || "neutral",
    );
  }

  const trend =
    structure.trend ||
    fallback ||
    "neutral";

  const structureEvents =
    Array.isArray(structure.structure)
      ? structure.structure
      : [];

  const latest =
    structureEvents.length > 0
      ? structureEvents[
          structureEvents.length - 1
        ]
      : null;

  if (latest) {
    const eventType =
      latest.type ||
      latest.event ||
      "structure event";

    const direction =
      latest.direction ||
      "neutral";

    return `${formatBias(
      trend,
    )} · latest ${formatBias(
      direction,
    )} ${formatBias(eventType)}`;
  }

  return formatBias(trend);
}

function describeLiquidity(
  liquidity,
) {
  if (!liquidity) {
    return "No liquidity data returned.";
  }

  const sweeps =
    Array.isArray(
      liquidity.liquidity_sweeps,
    )
      ? liquidity.liquidity_sweeps
      : [];

  if (sweeps.length === 0) {
    return "No recent relevant liquidity sweeps detected.";
  }

  const latest =
    sweeps[sweeps.length - 1];

  return `${sweeps.length} liquidity sweep(s) detected · latest ${formatBias(
    latest.direction ||
      "neutral",
  )}`;
}

function describeCollection(
  data,
  label,
) {
  if (!data) {
    return `No ${label} data returned.`;
  }

  const active =
    Array.isArray(
      data.active_fvg,
    )
      ? data.active_fvg
      : Array.isArray(
          data.active_order_blocks,
        )
        ? data.active_order_blocks
        : [];

  if (active.length === 0) {
    return `No relevant active ${label} evidence detected.`;
  }

  return `${active.length} active ${label} signal(s) detected.`;
}

function describeSupportResistance(
  data,
) {
  if (!data) {
    return "No support/resistance data returned.";
  }

  const support =
    data.nearest_support;

  const resistance =
    data.nearest_resistance;

  const supportText = support?.price
    ? `Support ${formatNumber(
        support.price,
      )}`
    : "Support unavailable";

  const resistanceText =
    resistance?.price
      ? `Resistance ${formatNumber(
          resistance.price,
        )}`
      : "Resistance unavailable";

  return `${supportText} · ${resistanceText}`;
}

export default App;



