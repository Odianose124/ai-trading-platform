import ManualTradeSetup from "./ManualTradeSetup";

export default function ManualTradePage() {
  return (
    <section className="page">
      <div
        style={{
          marginBottom: 26,
        }}
      >
        <div
          style={{
            color: "#38bdf8",
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: ".12em",
            textTransform: "uppercase",
            marginBottom: 8,
          }}
        >
          Manual execution
        </div>

        <h1
          style={{
            margin: 0,
            color: "#f8fafc",
            fontSize: "clamp(26px,5vw,38px)",
          }}
        >
          Manual Trade
        </h1>

        <p
          style={{
            margin: "10px 0 0",
            color: "#64748b",
            maxWidth: 720,
            lineHeight: 1.6,
          }}
        >
          Create, validate and explicitly authorize your
          own MT5 trade through the protected execution
          pipeline.
        </p>
      </div>

      <ManualTradeSetup />
    </section>
  );
}