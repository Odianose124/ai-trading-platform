import { useMemo, useState } from "react";
import {
  Bot,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  User,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import api from "./services/api";

function RegisterPage() {
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const passwordChecks = useMemo(
    () => ({
      length: password.length >= 8,
      uppercase: /[A-Z]/.test(password),
      lowercase: /[a-z]/.test(password),
      number: /\d/.test(password),
    }),
    [password],
  );

  const passwordStrength = useMemo(() => {
    if (!password) {
      return {
        label: "",
        percentage: 0,
      };
    }

    const score = Object.values(passwordChecks).filter(Boolean).length;

    if (score <= 1) {
      return {
        label: "Weak",
        percentage: 25,
      };
    }

    if (score === 2) {
      return {
        label: "Fair",
        percentage: 50,
      };
    }

    if (score === 3) {
      return {
        label: "Good",
        percentage: 75,
      };
    }

    return {
      label: "Strong",
      percentage: 100,
    };
  }, [password, passwordChecks]);

  const passwordsMatch =
    confirmPassword.length > 0 && password === confirmPassword;

  async function handleSubmit(event) {
    event.preventDefault();

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = fullName.trim();

    if (!normalizedEmail || !password || !confirmPassword) {
      setError("Please complete all required fields.");
      setSuccess("");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      setSuccess("");
      return;
    }

    if (password.length > 128) {
      setError("Password must not exceed 128 characters.");
      setSuccess("");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      setSuccess("");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await api.post("/api/auth/register", {
        email: normalizedEmail,
        password,
        full_name: normalizedName || null,
      });

      setSuccess("Your account has been created successfully.");

      window.setTimeout(() => {
        navigate("/login", {
          replace: true,
          state: {
            registeredEmail: normalizedEmail,
          },
        });
      }, 700);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;

      if (requestError?.response?.status === 409) {
        setError(
          "An account with this email already exists. Please sign in instead.",
        );
      } else if (requestError?.response?.status === 422) {
        if (Array.isArray(detail)) {
          const firstError = detail[0]?.msg;
          setError(firstError || "Please check the information provided.");
        } else {
          setError(
            detail || "Please check the information provided and try again.",
          );
        }
      } else if (Array.isArray(detail)) {
        const firstError = detail[0]?.msg;
        setError(firstError || "Unable to create your account.");
      } else {
        setError(
          detail || "Unable to create your account. Please try again.",
        );
      }
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
            <h1 style={styles.brandTitle}>AI Trader</h1>
            <p style={styles.brandSubtitle}>Trading Intelligence</p>
          </div>
        </div>

        <div style={styles.headingSection}>
          <h2 style={styles.heading}>Create your account</h2>

          <p style={styles.description}>
            Create a secure account to access your personal trading dashboard
            and connect your own MT5 account.
          </p>
        </div>

        {error && <div style={styles.errorBox}>{error}</div>}

        {success && (
          <div style={styles.successBox}>
            <CheckCircle2 size={17} />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>
            Full name
            <div style={styles.inputWrapper}>
              <User size={18} style={styles.inputIcon} />

              <input
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your full name"
                autoComplete="name"
                disabled={loading}
                style={styles.input}
              />
            </div>
          </label>

          <label style={styles.label}>
            Email address
            <div style={styles.inputWrapper}>
              <Mail size={18} style={styles.inputIcon} />

              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
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
              <LockKeyhole size={18} style={styles.inputIcon} />

              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setError("");
                }}
                placeholder="At least 8 characters"
                autoComplete="new-password"
                disabled={loading}
                required
                maxLength={128}
                style={{
                  ...styles.input,
                  paddingRight: "48px",
                }}
              />

              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                disabled={loading}
                aria-label={showPassword ? "Hide password" : "Show password"}
                style={styles.passwordButton}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>

            {password && (
              <div style={styles.passwordStrength}>
                <div style={styles.strengthHeader}>
                  <span>Password strength</span>

                  <span style={styles.strengthLabel}>
                    {passwordStrength.label}
                  </span>
                </div>

                <div style={styles.strengthTrack}>
                  <div
                    style={{
                      ...styles.strengthFill,
                      width: `${passwordStrength.percentage}%`,
                    }}
                  />
                </div>

                <div style={styles.passwordRequirements}>
                  <PasswordRequirement
                    valid={passwordChecks.length}
                    text="8+ characters"
                  />

                  <PasswordRequirement
                    valid={passwordChecks.uppercase}
                    text="Uppercase letter"
                  />

                  <PasswordRequirement
                    valid={passwordChecks.lowercase}
                    text="Lowercase letter"
                  />

                  <PasswordRequirement
                    valid={passwordChecks.number}
                    text="Number"
                  />
                </div>
              </div>
            )}
          </label>

          <label style={styles.label}>
            Confirm password

            <div style={styles.inputWrapper}>
              <LockKeyhole size={18} style={styles.inputIcon} />

              <input
                type={showConfirmPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  setError("");
                }}
                placeholder="Repeat your password"
                autoComplete="new-password"
                disabled={loading}
                required
                maxLength={128}
                style={{
                  ...styles.input,
                  paddingRight: "48px",
                  borderColor:
                    confirmPassword && !passwordsMatch
                      ? "rgba(239, 68, 68, 0.55)"
                      : confirmPassword && passwordsMatch
                        ? "rgba(34, 197, 94, 0.45)"
                        : "rgba(148, 163, 184, 0.2)",
                }}
              />

              <button
                type="button"
                onClick={() =>
                  setShowConfirmPassword((current) => !current)
                }
                disabled={loading}
                aria-label={
                  showConfirmPassword
                    ? "Hide password"
                    : "Show password"
                }
                style={styles.passwordButton}
              >
                {showConfirmPassword ? (
                  <EyeOff size={18} />
                ) : (
                  <Eye size={18} />
                )}
              </button>
            </div>

            {confirmPassword && (
              <span
                style={{
                  ...styles.matchMessage,
                  color: passwordsMatch ? "#86efac" : "#fca5a5",
                }}
              >
                {passwordsMatch
                  ? "Passwords match."
                  : "Passwords do not match."}
              </span>
            )}
          </label>

          <button
            type="submit"
            disabled={loading || Boolean(success)}
            style={{
              ...styles.submitButton,
              opacity: loading || success ? 0.7 : 1,
              cursor: loading || success ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <div style={styles.loginPrompt}>
          <span>Already have an account?</span>

          <Link to="/login" style={styles.loginLink}>
            Sign in
          </Link>
        </div>

        <div style={styles.securityNotice}>
          <ShieldCheck size={17} />

          <span>
            Your account is protected by authenticated API access. Your
            trading account remains isolated from other users.
          </span>
        </div>
      </main>
    </div>
  );
}

function PasswordRequirement({ valid, text }) {
  return (
    <span
      style={{
        ...styles.requirement,
        color: valid ? "#86efac" : "#64748b",
      }}
    >
      {valid ? "✓" : "○"} {text}
    </span>
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
    background: "rgba(15, 23, 42, 0.88)",
    border: "1px solid rgba(148, 163, 184, 0.16)",
    boxShadow: "0 30px 80px rgba(0, 0, 0, 0.45)",
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
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#ffffff",
    boxShadow: "0 10px 30px rgba(37, 99, 235, 0.3)",
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
    background: "rgba(239, 68, 68, 0.12)",
    border: "1px solid rgba(239, 68, 68, 0.28)",
    color: "#fca5a5",
    fontSize: "13px",
    lineHeight: 1.5,
  },

  successBox: {
    display: "flex",
    alignItems: "center",
    gap: "9px",
    padding: "12px 14px",
    marginBottom: "18px",
    borderRadius: "12px",
    background: "rgba(34, 197, 94, 0.12)",
    border: "1px solid rgba(34, 197, 94, 0.28)",
    color: "#86efac",
    fontSize: "13px",
    lineHeight: 1.5,
  },

  form: {
    display: "flex",
    flexDirection: "column",
    gap: "18px",
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
    border: "1px solid rgba(148, 163, 184, 0.2)",
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

  passwordStrength: {
    marginTop: "2px",
  },

  strengthHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "7px",
    color: "#64748b",
    fontSize: "11px",
    fontWeight: 500,
  },

  strengthLabel: {
    color: "#94a3b8",
    fontWeight: 700,
  },

  strengthTrack: {
    width: "100%",
    height: "4px",
    borderRadius: "999px",
    background: "#1e293b",
    overflow: "hidden",
  },

  strengthFill: {
    height: "100%",
    borderRadius: "999px",
    background: "linear-gradient(90deg, #ef4444, #f59e0b, #22c55e)",
    transition: "width 180ms ease",
  },

  passwordRequirements: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "5px 10px",
    marginTop: "8px",
  },

  requirement: {
    fontSize: "10px",
    fontWeight: 500,
  },

  matchMessage: {
    fontSize: "11px",
    fontWeight: 600,
  },

  submitButton: {
    width: "100%",
    height: "50px",
    marginTop: "4px",
    border: "none",
    borderRadius: "12px",
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    color: "#ffffff",
    fontSize: "14px",
    fontWeight: 700,
    cursor: "pointer",
    boxShadow: "0 12px 28px rgba(37, 99, 235, 0.25)",
  },

  loginPrompt: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: "6px",
    marginTop: "22px",
    color: "#64748b",
    fontSize: "13px",
  },

  loginLink: {
    color: "#60a5fa",
    textDecoration: "none",
    fontWeight: 700,
  },

  securityNotice: {
    display: "flex",
    alignItems: "flex-start",
    gap: "9px",
    marginTop: "25px",
    paddingTop: "20px",
    borderTop: "1px solid rgba(148, 163, 184, 0.12)",
    color: "#64748b",
    fontSize: "11px",
    lineHeight: 1.55,
  },
};

export default RegisterPage;
