import { useEffect, useState } from "react";
import {
  Activity,
  Bot,
  TrendingUp,
} from "lucide-react";
import api from "./services/api";

export default function AIAnalysisPage() {
  const [analysis, setAnalysis] = useState(null);
  const [mtf, setMtf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadAnalysis() {
    try {
      setError("");

      const [aiResponse, mtfResponse] = await Promise.all([
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

  const bias =
    analysis?.overall_bias || "neutral";

  const confidence =
    analysis?.confidence ?? null;

  const decision = getDecision(
    bias,
    confidence,
  );

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
          value={formatBias(bias)}
          loading={loading}
        />

        <MetricCard
          label="Confidence"
          value={
            confidence == null
              ? "--"
              : `${Number(confidence).toFixed(1)}%`
          }
          loading={loading}
        />

        <MetricCard
          label="MTF bias"
          value={formatBias(
            mtf?.overall_bias || "neutral",
          )}
          loading={loading}
        />

        <MetricCard
          label="AI action"
          value={decision}
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
          <ReasoningBlock
            title="Final bias"
            value={formatBias(bias)}
          />

          <ReasoningBlock
            title="Market condition"
            value={formatBias(
              analysis?.market_condition ||
                "range_or_uncertain",
            )}
          />

          <ReasoningBlock
            title="Decision"
            value={decision}
          />

          <ReasoningBlock
            title="Directional scores"
            value={formatScores(
              analysis?.scores,
            )}
          />

          <ReasoningBlock
            title="Reasons"
            value={
              formatList(analysis?.reasons) ||
              "No detailed reasons returned."
            }
          />

          <ReasoningBlock
            title="Warnings"
            value={
              formatList(analysis?.warnings) ||
              formatList(mtf?.warnings) ||
              "No warnings returned."
            }
          />
        </div>
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <TrendingUp size={20} />

          <div>
            <h3>Timeframe breakdown</h3>

            <span>
              Lower timeframe, execution timeframe and
              higher timeframe context
            </span>
          </div>
        </div>

        <div className="reasoning-content">
          {Array.isArray(mtf?.analyses) &&
          mtf.analyses.length > 0 ? (
            mtf.analyses.map((timeframe) => (
              <ReasoningBlock
                key={timeframe.timeframe}
                title={`${timeframe.timeframe} · ${timeframe.status}`}
                value={`${formatBias(
                  timeframe.bias,
                )} · ${Number(
                  timeframe.confidence || 0,
                ).toFixed(1)}% confidence · ${formatBias(
                  timeframe.market_condition,
                )}`}
              />
            ))
          ) : (
            <ReasoningBlock
              title="Timeframes"
              value="No timeframe analysis returned."
            />
          )}

          <ReasoningBlock
            title="Higher timeframe bias"
            value={formatBias(
              mtf?.higher_timeframe_bias ||
                "neutral",
            )}
          />

          <ReasoningBlock
            title="15m execution bias"
            value={formatBias(
              mtf?.execution_timeframe_bias ||
                "neutral",
            )}
          />

          <ReasoningBlock
            title="MTF alignment"
            value={
              mtf?.alignment ||
              "No alignment information returned."
            }
          />

          <ReasoningBlock
            title="MTF conflicts"
            value={
              formatList(mtf?.conflicts) ||
              "No conflicts returned."
            }
          />
        </div>
      </div>

      <div className="analysis-panel">
        <div className="panel-heading">
          <Activity size={20} />

          <div>
            <h3>Component evidence</h3>

            <span>
              How the weighted AI engine reached its
              directional assessment
            </span>
          </div>
        </div>

        <div className="reasoning-content">
          {Array.isArray(
            analysis?.components,
          ) &&
          analysis.components.length > 0 ? (
            analysis.components.map(
              (component) => (
                <ReasoningBlock
                  key={component.name}
                  title={`${formatBias(
                    component.name,
                  )} · ${component.weight}% weight`}
                  value={`${formatBias(
                    component.signal,
                  )} · ${Number(
                    component.confidence || 0,
                  ).toFixed(1)}% confidence · ${
                    component.reason ||
                    "No component explanation returned."
                  }`}
                />
              ),
            )
          ) : (
            <ReasoningBlock
              title="Components"
              value="No component evidence returned."
            />
          )}
        </div>
      </div>
    </section>
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
        <span className="loading-text">
          Loading live data...
        </span>
      ) : (
        <strong>{formatValue(value)}</strong>
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
    return value.join(" · ");
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
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