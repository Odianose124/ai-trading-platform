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

  const [intent, setIntent] = useState(null);
  const [intentLoading, setIntentLoading] = useState(false);
  const [intentError, setIntentError] = useState("");

  const [confirmation, setConfirmation] = useState(null);
  const [confirmationLoading, setConfirmationLoading] =
    useState(false);
  const [confirmationError, setConfirmationError] =
    useState("");

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
    setIntent(null);
    setIntentError("");
    setConfirmation(null);
    setConfirmationError("");

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

  async function createTradeIntent() {
    if (!preview?.approved || intentLoading) {
      return;
    }

    setIntentLoading(true);
    setIntentError("");
    setIntent(null);
    setConfirmation(null);
    setConfirmationError("");

    try {
      const response = await api.post(
        "/api/trade-intents",
        {
          symbol: setup.symbol || "XAUUSD",

          broker_symbol:
            preview.broker_symbol ||
            setup.broker_symbol ||
            setup.mt5_symbol ||
            setup.symbol ||
            "XAUUSD",

          direction: setup.direction,

          volume: Number(volume),

          signal_entry_price: Number(
            setup.entry_price,
          ),

          execution_price: Number(
            preview.execution_price,
          ),

          stop_loss: Number(
            setup.stop_loss,
          ),

          take_profit: Number(
            setup.take_profit_1,
          ),

          risk_percent:
            preview.risk?.percent === null ||
            preview.risk?.percent === undefined
              ? Number(riskPercent)
              : Number(preview.risk.percent),

          signal_price_deviation_percent:
            preview.signal_price_deviation_percent ??
            null,

          margin_required:
            preview.margin?.required ?? null,

          free_margin:
            preview.margin?.free ?? null,

          preview_status:
            preview.status || null,

          warnings:
            preview.warnings || [],

          checks:
            preview.checks || [],

          errors:
            preview.errors || [],
        },
      );

      setIntent(response.data);
    } catch (error) {
      setIntentError(
        error?.response?.data?.detail ||
          error?.response?.data?.message ||
          "Unable to create the trade intent.",
      );
    } finally {
      setIntentLoading(false);
    }
  }

  async function confirmTrade() {
    const intentId =
      intent?.id ?? intent?.intent_id ?? null;

    if (!intentId || confirmationLoading) {
      return;
    }

    setConfirmationLoading(true);
    setConfirmationError("");
    setConfirmation(null);

    try {
      const response = await api.post(
        "/api/trade-confirmation",
        {
          intent_id: Number(intentId),
        },
      );

      setConfirmation(response.data);
    } catch (error) {
      setConfirmationError(
        error?.response?.data?.detail ||
          error?.response?.data?.message ||
          "Unable to confirm the trade.",
      );
    } finally {
      setConfirmationLoading(false);
    }
  }

  const approved = Boolean(preview?.approved);

  const intentId =
    intent?.id ?? intent?.intent_id ?? null;

  const executionSent = Boolean(
    confirmation?.execution_sent,
  );

  return (
    <section className="trading-panel trade-review-panel">
      <div className="trading-panel-header">
        <div>
          <span>Trade review</span>
          <h2>Execution preview</h2>
        </div>

        <div className="trade-review-lock">
          <ShieldCheck size={17} />
          Protected execution
        </div>
      </div>

      <div className="trade-review-intro">
        <Eye size={20} />

        <div>
          <strong>
            Review the trade before confirmation
          </strong>

          <span>
            The platform validates the proposed trade
            against the live broker environment before
            any execution can be requested.
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
            disabled={
              !isTradeReady || previewLoading
            }
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
            disabled={
              !isTradeReady || previewLoading
            }
          />
        </label>

        <div className="trade-review-field readonly">
          <span>Direction</span>

          <strong>
            {formatDirection(setup?.direction)}
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
            <LoaderCircle
              size={18}
              className="spin"
            />
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
            approved
              ? "approved"
              : "blocked"
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
            value={formatNumber(
              preview.execution_price,
            )}
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
            {preview.checks.map(
              (check, index) => (
                <div
                  className="trade-review-check"
                  key={`${check}-${index}`}
                >
                  <CheckCircle2 size={16} />
                  <span>{check}</span>
                </div>
              ),
            )}
          </div>
        </div>
      )}

      {preview?.warnings?.length > 0 && (
        <div className="trade-review-check-section warnings">
          <div className="trade-review-subheading">
            Warnings
          </div>

          <div className="trade-review-check-list">
            {preview.warnings.map(
              (warning, index) => (
                <div
                  className="trade-review-check warning"
                  key={`${warning}-${index}`}
                >
                  <AlertTriangle size={16} />
                  <span>{warning}</span>
                </div>
              ),
            )}
          </div>
        </div>
      )}

      {preview?.errors?.length > 0 && (
        <div className="trade-review-check-section errors">
          <div className="trade-review-subheading">
            Blocking errors
          </div>

          <div className="trade-review-check-list">
            {preview.errors.map(
              (error, index) => (
                <div
                  className="trade-review-check error"
                  key={`${error}-${index}`}
                >
                  <XCircle size={16} />
                  <span>{error}</span>
                </div>
              ),
            )}
          </div>
        </div>
      )}

      {approved && !intent && (
        <div className="trade-review-intent-section">
          <div className="trade-review-intent-header">
            <div>
              <span>Next safety step</span>
              <strong>Create trade intent</strong>
            </div>

            <ShieldCheck size={21} />
          </div>

          <p>
            The broker preview has passed. Creating an
            intent stores the reviewed trade parameters
            for the protected confirmation workflow.
          </p>

          <button
            type="button"
            className="trade-review-preview-button"
            onClick={createTradeIntent}
            disabled={intentLoading}
          >
            {intentLoading ? (
              <>
                <LoaderCircle
                  size={18}
                  className="spin"
                />
                Creating trade intent...
              </>
            ) : (
              <>
                <ShieldCheck size={18} />
                Create trade intent
              </>
            )}
          </button>
        </div>
      )}

      {intentError && (
        <div className="trade-review-result error">
          <AlertTriangle size={19} />

          <div>
            <strong>Trade intent failed</strong>
            <span>{intentError}</span>
          </div>
        </div>
      )}

      {intent && !confirmation && (
        <>
          <div className="trade-review-result approved">
            <CheckCircle2 size={21} />

            <div>
              <strong>
                TRADE INTENT CREATED
              </strong>

              <span>
                Intent #{intentId} has been created
                successfully.
              </span>

              {intent.expires_at && (
                <span>
                  Expires:{" "}
                  {formatExpiry(
                    intent.expires_at,
                  )}
                </span>
              )}
            </div>
          </div>

          <div className="trade-confirmation-card">
            <div className="trade-confirmation-header">
              <div>
                <span>Final safety gate</span>
                <h3>Confirm this trade</h3>
              </div>

              <ShieldCheck size={24} />
            </div>

            <div className="trade-confirmation-warning">
              <AlertTriangle size={19} />

              <div>
                <strong>
                  This is the final execution action.
                </strong>

                <span>
                  Clicking Confirm &amp; Execute sends only
                  the server-side trade intent ID. The
                  server performs fresh ownership,
                  expiry, broker validation, margin,
                  price and MT5 safety checks before an
                  order can be submitted.
                </span>
              </div>
            </div>

            <div className="trade-confirmation-grid">
              <ConfirmationMetric
                label="Intent"
                value={`#${intentId}`}
              />

              <ConfirmationMetric
                label="Symbol"
                value={
                  intent.broker_symbol ||
                  intent.symbol
                }
              />

              <ConfirmationMetric
                label="Direction"
                value={formatDirection(
                  intent.direction,
                )}
              />

              <ConfirmationMetric
                label="Volume"
                value={formatNumber(
                  intent.volume,
                )}
              />

              <ConfirmationMetric
                label="Execution price"
                value={formatNumber(
                  intent.execution_price,
                )}
              />

              <ConfirmationMetric
                label="Stop loss"
                value={formatNumber(
                  intent.stop_loss,
                )}
              />

              <ConfirmationMetric
                label="Take profit"
                value={formatNumber(
                  intent.take_profit,
                )}
              />

              <ConfirmationMetric
                label="Risk %"
                value={
                  intent.risk_percent === null ||
                  intent.risk_percent ===
                    undefined
                    ? "--"
                    : `${formatNumber(
                        intent.risk_percent,
                      )}%`
                }
              />
            </div>

            <button
              type="button"
              className="trade-confirm-button"
              onClick={confirmTrade}
              disabled={
                confirmationLoading ||
                !intentId
              }
            >
              {confirmationLoading ? (
                <>
                  <LoaderCircle
                    size={19}
                    className="spin"
                  />
                  Revalidating with broker...
                </>
              ) : (
                <>
                  <ShieldCheck size={19} />
                  Confirm &amp; Execute Trade
                </>
              )}
            </button>

            <div className="trade-confirmation-note">
              <ShieldCheck size={17} />

              <span>
                <strong>Intent #{intentId}</strong>{" "}
                is the only value sent by the final
                confirmation action. The browser does not
                submit the trade price, volume, SL or TP
                directly to the execution endpoint.
              </span>
            </div>
          </div>
        </>
      )}

      {confirmationError && (
        <div className="trade-review-result error">
          <AlertTriangle size={19} />

          <div>
            <strong>
              Confirmation failed
            </strong>

            <span>{confirmationError}</span>
          </div>
        </div>
      )}

      {confirmation && (
        <div
          className={`trade-confirmation-result ${
            executionSent
              ? "executed"
              : "rejected"
          }`}
        >
          {executionSent ? (
            <CheckCircle2 size={24} />
          ) : (
            <XCircle size={24} />
          )}

          <div>
            <strong>
              {executionSent
                ? "TRADE EXECUTED"
                : "TRADE NOT EXECUTED"}
            </strong>

            <span>
              {confirmation.message ||
                "Trade confirmation completed."}
            </span>

            <span>
              Status:{" "}
              {formatValue(
                confirmation.status,
              )}
            </span>

            {confirmation.order_ticket && (
              <span>
                Order ticket:{" "}
                {confirmation.order_ticket}
              </span>
            )}

            {confirmation.deal_ticket && (
              <span>
                Deal ticket:{" "}
                {confirmation.deal_ticket}
              </span>
            )}

            {confirmation.retcode_description && (
              <span>
                Broker result:{" "}
                {confirmation.retcode_description}
              </span>
            )}
          </div>
        </div>
      )}

      {preview && !executionSent && (
        <div className="trade-review-final-lock">
          <ShieldCheck size={18} />

          <span>
            <strong>
              No MT5 order has been sent.
            </strong>{" "}
            The execution pipeline remains protected
            by server-side validation and MT5
            order_check() before order submission.
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

function ConfirmationMetric({
  label,
  value,
}) {
  return (
    <div className="trade-confirmation-metric">
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
    .replace(/\b\w/g, (character) =>
      character.toUpperCase(),
    );
}

function formatDirection(value) {
  const normalized = String(
    value || "",
  ).toLowerCase();

  if (
    normalized === "long" ||
    normalized === "buy" ||
    normalized === "bullish"
  ) {
    return "Long / Buy";
  }

  if (
    normalized === "short" ||
    normalized === "sell" ||
    normalized === "bearish"
  ) {
    return "Short / Sell";
  }

  return "Neutral";
}

function formatExpiry(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

export default TradeReviewPanel;