import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  LoaderCircle,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import api from "./services/api";

function TradeReviewPanel({ setup, isTradeReady }) {
  const [volume, setVolume] = useState(
    setup?.volume && Number(setup.volume) > 0
      ? String(setup.volume)
      : "0.01",
  );

  const [riskPercent, setRiskPercent] = useState("1");

  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  const canPreview =
    Boolean(isTradeReady) &&
    Number(volume) > 0 &&
    Number(setup?.entry_price) > 0 &&
    Number(setup?.stop_loss) > 0 &&
    Number(setup?.take_profit_1) > 0;

  async function generatePreview() {
    if (!canPreview) {
      return;
    }

    setPreviewLoading(true);
    setPreviewError("");
    setPreview(null);

    try {
      const response = await api.post(
        "/api/execution/preview",
        {
          symbol: setup.symbol || "XAUUSD",
          direction: setup.direction,
          volume: Number(volume),
          signal_entry_price: Number(setup.entry_price),
          stop_loss: Number(setup.stop_loss),
          take_profit: Number(setup.take_profit_1),
          risk_percent:
            riskPercent === ""
              ? null
              : Number(riskPercent),
        },
      );

      setPreview(response.data);
    } catch (error) {
      setPreviewError(
        error?.response?.data?.detail ||
          error?.response?.data?.message ||
          "Unable to create the execution preview.",
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  const approved = Boolean(preview?.approved);

  return (
    <section className="trading-panel trade-review-panel">
      <div className="trading-panel-header">
        <div>
          <span>Trade review</span>
          <h2>Execution preview</h2>
        </div>

        <div className="trade-review-lock">
          <ShieldCheck size={17} />
          Preview only
        </div>
      </div>

      <div className="trade-review-intro">
        <Eye size={20} />

        <div>
          <strong>
            Review the trade before confirmation
          </strong>

          <span>
            This step validates the proposed trade against
            the live broker environment. It does not send
            an MT5 order.
          </span>
        </div>
      </div>

      {!isTradeReady && (
        <div className="trade-review-blocked">
          <XCircle size={19} />

          <div>
            <strong>Trade review is locked</strong>

            <span>
              The AI setup is not currently executable.
              A preview can only be generated after the
              strategy produces a valid trade setup.
            </span>
          </div>
        </div>
      )}

      <div className="trade-review-input-grid">
        <label className="trade-review-field">
          <span>Volume</span>

          <input
            type="number"
            min="0.01"
            step="0.01"
            value={volume}
            onChange={(event) =>
              setVolume(event.target.value)
            }
            disabled={!isTradeReady || previewLoading}
          />
        </label>

        <label className="trade-review-field">
          <span>Risk %</span>

          <input
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={riskPercent}
            onChange={(event) =>
              setRiskPercent(event.target.value)
            }
            disabled={!isTradeReady || previewLoading}
          />
        </label>

        <div className="trade-review-field readonly">
          <span>Direction</span>
          <strong>
            {formatValue(setup?.direction)}
          </strong>
        </div>

        <div className="trade-review-field readonly">
          <span>Signal entry</span>
          <strong>
            {formatNumber(setup?.entry_price)}
          </strong>
        </div>

        <div className="trade-review-field readonly">
          <span>Stop loss</span>
          <strong>
            {formatNumber(setup?.stop_loss)}
          </strong>
        </div>

        <div className="trade-review-field readonly">
          <span>Take profit 1</span>
          <strong>
            {formatNumber(setup?.take_profit_1)}
          </strong>
        </div>
      </div>

      <button
        type="button"
        className="trade-review-preview-button"
        onClick={generatePreview}
        disabled={!canPreview || previewLoading}
      >
        {previewLoading ? (
          <>
            <LoaderCircle size={18} className="spin" />
            Validating with broker...
          </>
        ) : (
          <>
            <ShieldCheck size={18} />
            Generate execution preview
          </>
        )}
      </button>

      {previewError && (
        <div className="trade-review-result error">
          <AlertTriangle size={19} />

          <div>
            <strong>Preview failed</strong>
            <span>{previewError}</span>
          </div>
        </div>
      )}

      {preview && (
        <div
          className={`trade-review-result ${
            approved ? "approved" : "blocked"
          }`}
        >
          {approved ? (
            <CheckCircle2 size={21} />
          ) : (
            <XCircle size={21} />
          )}

          <div>
            <strong>
              {approved
                ? "READY FOR CONFIRMATION"
                : "EXECUTION PREVIEW BLOCKED"}
            </strong>

            <span>
              {preview.message ||
                "Execution preview completed."}
            </span>
          </div>
        </div>
      )}

      {preview && (
        <div className="trade-review-preview-grid">
          <PreviewMetric
            label="Status"
            value={formatValue(preview.status)}
          />

          <PreviewMetric
            label="Broker symbol"
            value={preview.broker_symbol}
          />

          <PreviewMetric
            label="Execution price"
            value={formatNumber(preview.execution_price)}
          />

          <PreviewMetric
            label="Signal deviation"
            value={
              preview.signal_price_deviation_percent ===
              null ||
              preview.signal_price_deviation_percent ===
              undefined
                ? "--"
                : `${formatNumber(
                    preview.signal_price_deviation_percent,
                  )}%`
            }
          />

          <PreviewMetric
            label="Spread"
            value={formatNumber(
              preview.market?.spread,
            )}
          />

          <PreviewMetric
            label="Spread points"
            value={formatNumber(
              preview.market?.spread_points,
            )}
          />

          <PreviewMetric
            label="Margin required"
            value={formatNumber(
              preview.margin?.required,
            )}
          />

          <PreviewMetric
            label="Free margin"
            value={formatNumber(
              preview.margin?.free,
            )}
          />

          <PreviewMetric
            label="Estimated risk"
            value={formatNumber(
              preview.risk?.amount,
            )}
          />

          <PreviewMetric
            label="Risk %"
            value={
              preview.risk?.percent === null ||
              preview.risk?.percent === undefined
                ? "--"
                : `${formatNumber(
                    preview.risk.percent,
                  )}%`
            }
          />
        </div>
      )}

      {preview?.checks?.length > 0 && (
        <div className="trade-review-check-section">
          <div className="trade-review-subheading">
            Safety checks passed
          </div>

          <div className="trade-review-check-list">
            {preview.checks.map((check, index) => (
              <div
                className="trade-review-check"
                key={`${check}-${index}`}
              >
                <CheckCircle2 size={16} />
                <span>{check}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {preview?.warnings?.length > 0 && (
        <div className="trade-review-check-section warnings">
          <div className="trade-review-subheading">
            Warnings
          </div>

          <div className="trade-review-check-list">
            {preview.warnings.map((warning, index) => (
              <div
                className="trade-review-check warning"
                key={`${warning}-${index}`}
              >
                <AlertTriangle size={16} />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {preview?.errors?.length > 0 && (
        <div className="trade-review-check-section errors">
          <div className="trade-review-subheading">
            Blocking errors
          </div>

          <div className="trade-review-check-list">
            {preview.errors.map((error, index) => (
              <div
                className="trade-review-check error"
                key={`${error}-${index}`}
              >
                <XCircle size={16} />
                <span>{error}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {preview && (
        <div className="trade-review-final-lock">
          <ShieldCheck size={18} />

          <span>
            <strong>No MT5 order has been sent.</strong>{" "}
            This is only an execution preview. Final
            confirmation and the protected MT5 execution
            pipeline remain separate.
          </span>
        </div>
      )}
    </section>
  );
}

function PreviewMetric({ label, value }) {
  return (
    <div className="trade-review-metric">
      <span>{label}</span>
      <strong>
        {value === null ||
        value === undefined ||
        value === ""
          ? "--"
          : value}
      </strong>
    </div>
  );
}

function formatNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
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

export default TradeReviewPanel;
