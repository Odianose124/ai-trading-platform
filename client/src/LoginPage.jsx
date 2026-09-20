import { useState } from "react";
import {
  Bot,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "./services/api";

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState(
    location.state?.registeredEmail || "",
  );
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const redirectPath =
    location.state?.from?.pathname || "/";

  async function handleSubmit(event) {
    event.preventDefault();

    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new URLSearchParams();

      formData.append("username", normalizedEmail);
      formData.append("password", password);

      const response = await api.post(
        "/api/auth/login",
        formData,
        {
          headers: {
            "Content-Type":
              "application/x-www-form-urlencoded",
          },
        },
      );

      const token = response?.data?.access_token;

      if (!token) {
        throw new Error(
          "The server did not return an access token.",
        );
      }

      localStorage.setItem(
        "ai_trading_access_token",
        token,
      );

      /*
       * Validate the newly issued token before leaving
       * the login page. This prevents a successful login
       * from appearing to fail after the application
       * reloads and validates /api/auth/me.
       */
      const sessionResponse = await api.get(
        "/api/auth/me",
      );

      if (!sessionResponse?.data?.id) {
        throw new Error(
          "The server could not validate the authenticated session.",
        );
      }

      window.location.assign(redirectPath);
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail;

      if (
        requestError?.response?.status === 401
      ) {
        setError(
          "Unable to sign in. Please check your email and password.",
        );
      } else if (
        requestError?.response?.status === 403
      ) {
        setError(
          detail ||
            "Your account is inactive. Please contact support.",
        );
      } else if (detail) {
        setError(
          Array.isArray(detail)
            ? detail[0]?.msg ||
                "Unable to sign in. Please try again."
            : detail,
        );
      } else if (requestError?.message) {
        setError(requestError.message);
      } else {
        setError(
          "Unable to sign in. Please try again.",
        );
      }

      localStorage.removeItem(
        "ai_trading_access_token",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.backgroundGlow} />

      <main style={styles.card}>
        <div style={styles.brandSection}>
          <div style={styles.brandIcon}>
            <Bot size={27} />
          </div>

          <div>
            <h1 style={styles.brandTitle}>
              AI Trader
            </h1>

            <p style={styles.brandSubtitle}>
              Trading Intelligence
            </p>
          </div>
        </div>

        <div style={styles.headingSection}>
          <h2 style={styles.heading}>
            Welcome back
          </h2>

          <p style={styles.description}>
            Sign in to access your live AI trading
            intelligence and protected trading tools.
          </p>
        </div>

        {error && (
          <div style={styles.errorBox}>
            {error}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          style={styles.form}
        >
          <label style={styles.label}>
            Email address

            <div style={styles.inputWrapper}>
              <Mail
                size={18}
                style={styles.inputIcon}
              />

              <input
                type="email"
                value={email}
                onChange={(event) =>
                  setEmail(event.target.value)
                }
                placeholder="you@example.com"
                autoComplete="email"
                disabled={loading}
                required
                style={styles.input}
              />
            </div>
          </label>

          <label style={styles.label}>
            Password

            <div style={styles.inputWrapper}>
              <LockKeyhole
                size={18}
                style={styles.inputIcon}
              />

              <input
                type={
                  showPassword
                    ? "text"
                    : "password"
                }
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                placeholder="Enter your password"
                autoComplete="current-password"
                disabled={loading}
                required
                style={{
                  ...styles.input,
                  paddingRight: "48px",
                }}
              />

              <button
                type="button"
                onClick={() =>
                  setShowPassword(
                    (current) => !current,
                  )
                }
                disabled={loading}
                aria-label={
                  showPassword
                    ? "Hide password"
                    : "Show password"
                }
                style={styles.passwordButton}
              >
                {showPassword ? (
                  <EyeOff size={18} />
                ) : (
                  <Eye size={18} />
                )}
              </button>
            </div>
          </label>

          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.submitButton,
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading
              ? "Signing in..."
              : "Sign in"}
          </button>
        </form>

        <div style={styles.registerPrompt}>
          <span>Don't have an account?</span>

          <button
            type="button"
            onClick={() => navigate("/register")}
            style={styles.registerLink}
            disabled={loading}
          >
            Create account
          </button>
        </div>

        <div style={styles.securityNotice}>
          <ShieldCheck size={17} />

          <span>
            Protected trading access. Live order
            execution remains behind the platform's
            separate safety and confirmation pipeline.
          </span>
        </div>
      </main>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px",
    position: "relative",
    overflow: "hidden",
    background:
      "linear-gradient(135deg, #020617 0%, #0f172a 55%, #111827 100%)",
    boxSizing: "border-box",
  },

  backgroundGlow: {
    position: "absolute",
    width: "420px",
    height: "420px",
    borderRadius: "50%",
    background:
      "radial-gradient(circle, rgba(37,99,235,0.22) 0%, rgba(37,99,235,0) 70%)",
    top: "-160px",
    right: "-100px",
    pointerEvents: "none",
  },

  card: {
    width: "100%",
    maxWidth: "460px",
    padding: "34px",
    borderRadius: "24px",
    background:
      "rgba(15, 23, 42, 0.88)",
    border:
      "1px solid rgba(148, 163, 184, 0.16)",
    boxShadow:
      "0 30px 80px rgba(0, 0, 0, 0.45)",
    backdropFilter: "blur(18px)",
    position: "relative",
    zIndex: 1,
    boxSizing: "border-box",
  },

  brandSection: {
    display: "flex",
    alignItems: "center",
    gap: "13px",
    marginBottom: "34px",
  },

  brandIcon: {
    width: "52px",
    height: "52px",
    borderRadius: "15px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background:
      "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#ffffff",
    boxShadow:
      "0 10px 30px rgba(37, 99, 235, 0.3)",
  },

  brandTitle: {
    margin: 0,
    color: "#f8fafc",
    fontSize: "20px",
    fontWeight: 800,
  },

  brandSubtitle: {
    margin: "3px 0 0",
    color: "#94a3b8",
    fontSize: "13px",
  },

  headingSection: {
    marginBottom: "25px",
  },

  heading: {
    margin: 0,
    color: "#f8fafc",
    fontSize: "30px",
    fontWeight: 800,
    letterSpacing: "-0.6px",
  },

  description: {
    margin: "9px 0 0",
    color: "#94a3b8",
    fontSize: "14px",
    lineHeight: 1.65,
  },

  errorBox: {
    padding: "12px 14px",
    marginBottom: "18px",
    borderRadius: "12px",
    background:
      "rgba(239, 68, 68, 0.12)",
    border:
      "1px solid rgba(239, 68, 68, 0.28)",
    color: "#fca5a5",
    fontSize: "13px",
    lineHeight: 1.5,
  },

  form: {
    display: "flex",
    flexDirection: "column",
    gap: "20px",
  },

  label: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    color: "#cbd5e1",
    fontSize: "13px",
    fontWeight: 600,
  },

  inputWrapper: {
    position: "relative",
    width: "100%",
  },

  inputIcon: {
    position: "absolute",
    left: "15px",
    top: "50%",
    transform: "translateY(-50%)",
    color: "#64748b",
    pointerEvents: "none",
  },

  input: {
    width: "100%",
    height: "50px",
    boxSizing: "border-box",
    borderRadius: "12px",
    border:
      "1px solid rgba(148, 163, 184, 0.2)",
    background: "#020617",
    color: "#f8fafc",
    padding: "0 15px 0 45px",
    outline: "none",
    fontSize: "14px",
  },

  passwordButton: {
    position: "absolute",
    right: "8px",
    top: "50%",
    transform: "translateY(-50%)",
    width: "36px",
    height: "36px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "none",
    borderRadius: "9px",
    background: "transparent",
    color: "#64748b",
    cursor: "pointer",
  },

  submitButton: {
    width: "100%",
    height: "50px",
    marginTop: "4px",
    border: "none",
    borderRadius: "12px",
    background:
      "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#ffffff",
    fontSize: "14px",
    fontWeight: 700,
    cursor: "pointer",
    boxShadow:
      "0 12px 28px rgba(37, 99, 235, 0.25)",
  },

  registerPrompt: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: "6px",
    marginTop: "22px",
    color: "#64748b",
    fontSize: "13px",
  },

  registerLink: {
    border: "none",
    background: "transparent",
    padding: 0,
    color: "#60a5fa",
    fontSize: "13px",
    fontWeight: 700,
    cursor: "pointer",
  },

  securityNotice: {
    display: "flex",
    alignItems: "flex-start",
    gap: "9px",
    marginTop: "25px",
    paddingTop: "20px",
    borderTop:
      "1px solid rgba(148, 163, 184, 0.12)",
    color: "#64748b",
    fontSize: "11px",
    lineHeight: 1.55,
  },
};

export default LoginPage;
