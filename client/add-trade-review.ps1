$ErrorActionPreference = "Stop"

$tradeReviewPath = ".\src\TradeReviewPanel.jsx"
$tradingPagePath = ".\src\TradingPage.jsx"
$tradingCssPath = ".\src\trading.css"

$tradeReview = @'
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
'@

Set-Content `
  -Path $tradeReviewPath `
  -Value $tradeReview `
  -Encoding UTF8

Write-Host "Created TradeReviewPanel.jsx"

$tradingPage = Get-Content `
  -Path $tradingPagePath `
  -Raw

if ($tradingPage -notmatch 'TradeReviewPanel') {
    $tradingPage = $tradingPage.Replace(
        'import api from "./services/api";',
        'import api from "./services/api";' + "`r`n" +
        'import TradeReviewPanel from "./TradeReviewPanel";'
    )
}

$marker = @'
      <div className="trading-bottom-safety">
'@

if ($tradingPage.Contains($marker)) {
    if ($tradingPage -notmatch '<TradeReviewPanel') {
        $insert = @'
      <TradeReviewPanel
        setup={setup}
        isTradeReady={isTradeReady}
      />

'@

        $tradingPage = $tradingPage.Replace(
            $marker,
            $insert + $marker
        )

        Write-Host "Trade review panel connected to TradingPage."
    }
    else {
        Write-Host "Trade review panel is already connected."
    }
}
else {
    throw "Could not find the TradingPage insertion point."
}

Set-Content `
  -Path $tradingPagePath `
  -Value $tradingPage `
  -Encoding UTF8

$css = Get-Content `
  -Path $tradingCssPath `
  -Raw

if ($css -notmatch 'trade-review-panel') {

$tradeReviewCss = @'

/* Trade Review / Execution Preview */

.trade-review-panel {
  margin-top: 24px;
}

.trade-review-lock {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
}

.trade-review-intro {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 14px;
  background: rgba(37, 99, 235, 0.04);
}

.trade-review-intro svg {
  flex: 0 0 auto;
  color: #2563eb;
}

.trade-review-intro strong,
.trade-review-blocked strong,
.trade-review-result strong {
  display: block;
  margin-bottom: 4px;
}

.trade-review-intro span,
.trade-review-blocked span,
.trade-review-result span {
  display: block;
  color: #64748b;
  line-height: 1.5;
}

.trade-review-blocked {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid rgba(239, 68, 68, 0.18);
  border-radius: 14px;
  background: rgba(239, 68, 68, 0.05);
}

.trade-review-blocked > svg {
  flex: 0 0 auto;
  color: #ef4444;
}

.trade-review-input-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.trade-review-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.trade-review-field > span {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.trade-review-field input,
.trade-review-field.readonly {
  min-height: 44px;
  border-radius: 10px;
}

.trade-review-field input {
  width: 100%;
  border: 1px solid #cbd5e1;
  background: #fff;
  padding: 0 12px;
  font: inherit;
  color: #0f172a;
}

.trade-review-field input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.trade-review-field input:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.trade-review-field.readonly {
  display: flex;
  justify-content: center;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.trade-review-field.readonly strong {
  color: #0f172a;
}

.trade-review-preview-button {
  width: 100%;
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 0;
  border-radius: 11px;
  background: #2563eb;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
  transition:
    transform 0.15s ease,
    opacity 0.15s ease,
    background 0.15s ease;
}

.trade-review-preview-button:hover:not(:disabled) {
  background: #1d4ed8;
  transform: translateY(-1px);
}

.trade-review-preview-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.trade-review-result {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-top: 18px;
  padding: 16px;
  border-radius: 14px;
}

.trade-review-result.approved {
  border: 1px solid rgba(34, 197, 94, 0.2);
  background: rgba(34, 197, 94, 0.06);
}

.trade-review-result.approved > svg {
  color: #16a34a;
}

.trade-review-result.blocked,
.trade-review-result.error {
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.06);
}

.trade-review-result.blocked > svg,
.trade-review-result.error > svg {
  color: #dc2626;
}

.trade-review-preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.trade-review-metric {
  min-height: 74px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 11px;
  background: #f8fafc;
}

.trade-review-metric span {
  display: block;
  margin-bottom: 7px;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.trade-review-metric strong {
  color: #0f172a;
  font-size: 14px;
}

.trade-review-check-section {
  margin-top: 20px;
}

.trade-review-check-section.warnings {
  padding-top: 18px;
  border-top: 1px solid #e2e8f0;
}

.trade-review-check-section.errors {
  padding-top: 18px;
  border-top: 1px solid #fecaca;
}

.trade-review-subheading {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.trade-review-check-list {
  display: grid;
  gap: 8px;
}

.trade-review-check {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 11px;
  border-radius: 9px;
  background: rgba(34, 197, 94, 0.05);
  color: #166534;
  font-size: 13px;
  line-height: 1.45;
}

.trade-review-check svg {
  flex: 0 0 auto;
  margin-top: 2px;
}

.trade-review-check.warning {
  background: rgba(245, 158, 11, 0.07);
  color: #92400e;
}

.trade-review-check.error {
  background: rgba(239, 68, 68, 0.07);
  color: #991b1b;
}

.trade-review-final-lock {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 20px;
  padding: 14px 16px;
  border-radius: 11px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 13px;
  line-height: 1.5;
}

.trade-review-final-lock svg {
  flex: 0 0 auto;
  color: #22c55e;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .trade-review-input-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trade-review-preview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .trade-review-input-grid,
  .trade-review-preview-grid {
    grid-template-columns: 1fr;
  }

  .trade-review-lock {
    align-self: flex-start;
  }
}
'@

$css += $tradeReviewCss

Set-Content `
  -Path $tradingCssPath `
  -Value $css `
  -Encoding UTF8

Write-Host "Trade review styles added."
}
else {
    Write-Host "Trade review styles already exist."
}

Write-Host ""
Write-Host "SUCCESS: Trade Review / Execution Preview has been added."
Write-Host "No MT5 execution button has been added."
Write-Host "Run npm run build next."