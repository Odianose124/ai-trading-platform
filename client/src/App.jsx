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
  Settings,
  ShieldCheck,
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
      <TradingApplication />
    </BrowserRouter>
  );
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
        await api.get("/api/mt5/status");
        if (mounted) {
          setMt5Status("connected");
        }
      } catch {
        if (mounted) {
          setMt5Status("disconnected");
        }
      }
    }

    checkServices();

    const interval = window.setInterval(checkServices, 15000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenuOpen ? "sidebar-open" : ""}`}>
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
                  `navigation-link ${isActive ? "active" : ""}`
                }
              >
                <Icon size={19} />
                <span>{item.label}</span>
                <ChevronRight size={16} className="navigation-arrow" />
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
                backendStatus === "online" ? "online" : ""
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
              element={<Markets />}
            />

            <Route
              path="/ai-analysis"
              element={<AIAnalysis />}
            />

            <Route
              path="/positions"
              element={<Positions />}
            />

            <Route
              path="/history"
              element={<TradeHistory />}
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
            status === "connected" || status === "online"
              ? "online"
              : ""
          }`}
        />

        {text}
      </span>
    </div>
  );
}

function CommandCenter() {
  const [prices, setPrices] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [mtf, setMtf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    async function loadCommandCenter() {
      setLoading(true);
      setError("");

      try {
        const [priceResponse, analysisResponse, mtfResponse] =
          await Promise.all([
            api.get("/api/mt5/market-data/ticks"),
            api.get(
              "/api/mt5/market-data/analysis/ai/XAUUSD/15m",
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
          ]);

        if (!mounted) {
          return;
        }

        setPrices(priceResponse.data);
        setAnalysis(analysisResponse.data);
        setMtf(mtfResponse.data);
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
    analysis?.bias ||
    analysis?.market_bias ||
    mtf?.overall_bias ||
    "unavailable";

  const confidence =
    analysis?.confidence ??
    mtf?.confidence ??
    null;

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
                {formatBias(aiBias)}
              </h2>
            </div>

            <div className="confidence-ring">
              {confidence === null
                ? "--"
                : `${Number(confidence).toFixed(1)}%`}
              <span>confidence</span>
            </div>
          </div>

          <div className="decision-description">
            {loading
              ? "Reading live market conditions..."
              : analysis?.summary ||
                analysis?.reasoning ||
                mtf?.alignment ||
                "The AI is evaluating current market structure and available evidence."}
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
              <span className="card-label">Live prices</span>
              <h3>Market overview</h3>
            </div>
          </div>

          <div className="price-list">
            {["XAUUSD", "BTCUSD", "EURUSD"].map((symbol) => {
              const item = prices?.prices?.[symbol];

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

      <div className="section-title-row">
        <div>
          <span className="card-label">Intelligence</span>
          <h3>What the AI sees</h3>
        </div>
      </div>

      <div className="intelligence-grid">
        <InsightCard
          title="Market bias"
          value={formatBias(
            analysis?.bias ||
              analysis?.market_bias ||
              "unavailable",
          )}
          description="Current directional assessment."
        />

        <InsightCard
          title="Structure"
          value={
            analysis?.market_structure?.trend ||
            analysis?.structure?.trend ||
            "Available"
          }
          description="Market-structure assessment from MT5 candles."
        />

        <InsightCard
          title="Liquidity"
          value={
            analysis?.liquidity?.direction ||
            analysis?.liquidity_direction ||
            "Monitored"
          }
          description="Liquidity and sweep evidence."
        />

        <InsightCard
          title="Multi-timeframe"
          value={formatBias(
            mtf?.overall_bias ||
              mtf?.bias ||
              "unavailable",
          )}
          description={
            mtf?.alignment ||
            "Cross-timeframe confirmation."
          }
        />
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

function AIAnalysis() {
  const [analysis, setAnalysis] = useState(null);
  const [mtf, setMtf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadAnalysis() {
    try {
      setError("");

      const [aiResponse, mtfResponse] =
        await Promise.all([
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
        ]);

      setAnalysis(aiResponse.data);
      setMtf(mtfResponse.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to load AI analysis.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAnalysis();

    const interval = window.setInterval(
      loadAnalysis,
      15000,
    );

    return () => window.clearInterval(interval);
  }, []);

  return (
    <section className="page">
      <PageHeading
        eyebrow="AI Analysis"
        title="Market reasoning"
        description="The analysis shown here comes from the live MT5 analysis engines already connected to the backend."
      />

      {error && <ErrorBanner message={error} />}

      <div className="analysis-summary-grid">
        <MetricCard
          label="AI bias"
          value={formatBias(
            analysis?.bias ||
              analysis?.market_bias ||
              "unavailable",
          )}
          loading={loading}
        />

        <MetricCard
          label="Confidence"
          value={
            analysis?.confidence == null
              ? "--"
              : `${Number(analysis.confidence).toFixed(1)}%`
          }
          loading={loading}
        />

        <MetricCard
          label="MTF bias"
          value={formatBias(
            mtf?.overall_bias ||
              mtf?.bias ||
              "unavailable",
          )}
          loading={loading}
        />

        <MetricCard
          label="Alignment"
          value={
            mtf?.alignment ||
            "Unavailable"
          }
          loading={loading}
        />
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <Bot size={20} />
          <div>
            <h3>AI reasoning</h3>
            <span>XAUUSD · 15m</span>
          </div>
        </div>

        <div className="reasoning-content">
          {loading ? (
            <LoadingText />
          ) : (
            <>
              <ReasoningBlock
                title="Decision"
                value={
                  analysis?.decision ||
                  analysis?.bias ||
                  analysis?.market_bias ||
                  "Unavailable"
                }
              />

              <ReasoningBlock
                title="Summary"
                value={
                  analysis?.summary ||
                  analysis?.reasoning ||
                  "No summary was returned by the backend."
                }
              />

              <ReasoningBlock
                title="Warnings"
                value={
                  Array.isArray(mtf?.warnings)
                    ? mtf.warnings.join(" ")
                    : mtf?.warnings ||
                      "No warnings returned."
                }
              />
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Positions() {
  return (
    <section className="page">
      <PageHeading
        eyebrow="Positions"
        title="Open positions"
        description="Live trade positions will appear here once the connected trading account has open positions."
      />

      <EmptyState
        title="No open positions"
        description="No open MT5 positions are currently exposed to the frontend."
      />
    </section>
  );
}

function TradeHistory() {
  return (
    <section className="page">
      <PageHeading
        eyebrow="History"
        title="Trade history"
        description="Executed trades and their outcomes will be displayed here as the execution and history APIs are exposed to the frontend."
      />

      <EmptyState
        title="No trade history available"
        description="There are currently no executed trades available to display."
      />
    </section>
  );
}

function SettingsPage() {
  return (
    <section className="page">
      <PageHeading
        eyebrow="Settings"
        title="Platform settings"
        description="Trading controls and account configuration will be connected here as their backend controls become available."
      />

      <div className="settings-grid">
        <div className="settings-card">
          <div className="settings-icon">
            <ShieldCheck size={20} />
          </div>

          <div>
            <h3>Risk protection</h3>
            <p>
              Trading safety controls remain enforced by
              the backend execution layer.
            </p>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-icon">
            <PanelLeftClose size={20} />
          </div>

          <div>
            <h3>Interface</h3>
            <p>
              The interface is optimized for mobile,
              tablet and desktop screens.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function PriceRow({ symbol, data, loading }) {
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
          {data.mt5_symbol || data.symbol || symbol}
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

function MarketCard({ symbol, data, loading }) {
  return (
    <article className="market-card">
      <div className="market-card-header">
        <div>
          <span className="market-symbol">{symbol}</span>
          <span className="market-source">
            {data?.mt5_symbol || data?.symbol || "MT5"}
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
        <p className="muted">{data.error}</p>
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
      <strong>{formatValue(value)}</strong>
      <p>{description}</p>
    </article>
  );
}

function MetricCard({ label, value, loading }) {
  return (
    <article className="metric-card">
      <span>{label}</span>

      {loading ? (
        <LoadingText />
      ) : (
        <strong>{formatValue(value)}</strong>
      )}
    </article>
  );
}

function ReasoningBlock({ title, value }) {
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
      <span className="eyebrow">{eyebrow}</span>
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

function EmptyState({ title, description }) {
  return (
    <div className="empty-state">
      <BriefcaseBusiness size={25} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

function LoadingText() {
  return <span className="loading-text">Loading live data...</span>;
}

function biasClass(value) {
  const normalized = String(value).toLowerCase();

  if (normalized.includes("bull")) {
    return "bias-bullish";
  }

  if (normalized.includes("bear")) {
    return "bias-bearish";
  }

  return "bias-neutral";
}

function formatBias(value) {
  const text = String(value || "unavailable")
    .replaceAll("_", " ")
    .trim();

  if (!text) {
    return "Unavailable";
  }

  return text.charAt(0).toUpperCase() + text.slice(1);
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

  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 5,
  });
}

export default App;