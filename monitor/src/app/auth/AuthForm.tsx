"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { formatCountdown, formatKstTimestamp } from "@/lib/format";
import styles from "./AuthGate.module.css";

type Phase = "loading" | "ready" | "blocked";

interface RequestCodeResponse {
  ok: boolean;
  reason?: "blocked" | "cooldown";
  expiresInSeconds?: number;
  maxAttempts?: number;
  maskedIp?: string;
}

interface VerifyCodeResponse {
  ok: boolean;
  reason?: "blocked" | "invalid" | "expired";
  attemptsRemaining?: number;
}

const DEFAULT_MAX_ATTEMPTS = 3;

function ShieldIcon({ blocked }: { blocked?: boolean }) {
  const stroke = blocked ? "oklch(78% 0.16 25)" : "oklch(70% 0.17 30)";
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 2L4 6V11C4 16 7.5 20.5 12 22C16.5 20.5 20 16 20 11V6L12 2Z"
        stroke={stroke}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      {!blocked && (
        <>
          <path d="M12 8V13" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="12" cy="16" r="0.9" fill={stroke} />
        </>
      )}
      {blocked && (
        <path d="M9 9L15 15M15 9L9 15" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
      )}
    </svg>
  );
}

function DiscordIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="oklch(72% 0.14 275)">
      <path d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.128 12.3 12.3 0 0 1-1.873.892.076.076 0 0 0-.04.106c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.029 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.055c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}

function DigitBoxes({ code, focused }: { code: string; focused: boolean }) {
  return (
    <div className={styles.codeRow}>
      {Array.from({ length: 6 }, (_, i) => {
        const filled = i < code.length;
        const isCursor = focused && i === code.length;
        return (
          <div key={i} className={`${styles.digitBox} ${filled ? styles.digitBoxFilled : ""}`}>
            {filled ? code[i] : isCursor ? <span className={styles.digitCursor} /> : null}
          </div>
        );
      })}
    </div>
  );
}

export function AuthForm() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [code, setCode] = useState("");
  const [focused, setFocused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [maxAttempts, setMaxAttempts] = useState(DEFAULT_MAX_ATTEMPTS);
  const [attemptsRemaining, setAttemptsRemaining] = useState(DEFAULT_MAX_ATTEMPTS);
  const [maskedIp, setMaskedIp] = useState("");
  const [requestedAt, setRequestedAt] = useState<Date | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestedOnce = useRef(false);
  // The input is `disabled` while pending/loading; calling .focus() right after
  // setPhase("ready") is a no-op because React hasn't re-rendered yet. This flag
  // defers the actual focus() call to an effect that runs after that re-render.
  const wantsFocus = useRef(false);

  async function requestCode() {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/request-code", { method: "POST" });
      const data: RequestCodeResponse = await res.json();
      if (!res.ok || !data.ok) {
        if (data.reason === "blocked") {
          setPhase("blocked");
        } else {
          setError("잠시 후 다시 시도하세요.");
          setPhase("ready");
        }
        return;
      }
      setMaxAttempts(data.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);
      setAttemptsRemaining(data.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);
      setMaskedIp(data.maskedIp ?? "");
      setSecondsLeft(data.expiresInSeconds ?? 0);
      setRequestedAt(new Date());
      setCode("");
      setPhase("ready");
      wantsFocus.current = true;
    } catch {
      setError("네트워크 오류가 발생했습니다.");
      setPhase("ready");
    } finally {
      setPending(false);
    }
  }

  async function verifyCode(submitted: string) {
    setPending(true);
    try {
      const res = await fetch("/api/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: submitted }),
      });
      const data: VerifyCodeResponse = await res.json();
      if (!res.ok || !data.ok) {
        if (data.reason === "blocked") {
          setPhase("blocked");
        } else if (data.reason === "expired") {
          setError("코드가 만료되었습니다. 재전송해주세요.");
          setSecondsLeft(0);
          setCode("");
        } else {
          setError("인증코드가 일치하지 않습니다. 3회 실패 시 해당 IP는 자동 차단됩니다.");
          if (typeof data.attemptsRemaining === "number") setAttemptsRemaining(data.attemptsRemaining);
          setCode("");
          wantsFocus.current = true;
        }
        return;
      }
      window.location.href = "/";
    } catch {
      setError("네트워크 오류가 발생했습니다.");
      setCode("");
    } finally {
      setPending(false);
    }
  }

  // Deferred so the first render matches the server before hydration (see LiveClock).
  useEffect(() => {
    if (requestedOnce.current) return;
    requestedOnce.current = true;
    const kickoff = setTimeout(() => requestCode(), 0);
    return () => clearTimeout(kickoff);
  }, []);

  // Runs after every render, i.e. after the DOM reflects the latest `disabled` state —
  // exactly what wantsFocus.current needs (see its declaration above).
  useEffect(() => {
    if (wantsFocus.current && !pending) {
      wantsFocus.current = false;
      inputRef.current?.focus();
    }
  });

  // Re-armed setTimeout (not setInterval) each tick — avoids setInterval drift and
  // keeps `secondsLeft` an honest dependency for exhaustive-deps.
  useEffect(() => {
    if (phase !== "ready" || secondsLeft <= 0) return;
    const id = setTimeout(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(id);
  }, [phase, secondsLeft]);

  function handleCodeChange(e: ChangeEvent<HTMLInputElement>) {
    const digits = e.target.value.replace(/\D/g, "").slice(0, 6);
    setCode(digits);
    setError(null);
    if (digits.length === 6 && !pending) {
      verifyCode(digits);
    }
  }

  if (phase === "blocked") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.header}>
            <div className={`${styles.headerIcon} ${styles.headerIconBlocked}`}>
              <ShieldIcon blocked />
            </div>
            <h1 className={styles.title}>접근 차단됨</h1>
            <p className={styles.blockedText}>
              인증 실패 횟수를 초과해 이 네트워크에서의 접근이 영구적으로 차단되었습니다.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const codeExpired = phase === "ready" && secondsLeft <= 0 && requestedAt !== null;

  return (
    <div className={styles.page}>
      <div className={styles.brand}>
        <div className={styles.brandLogo}>빈</div>
        <div className={styles.brandTitle}>BIN MONITOR</div>
      </div>

      <div className={styles.status}>
        <span className={styles.statusDot} />
        <span>외부 IP 감지 · 인증 필요</span>
      </div>

      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerIcon}>
            <ShieldIcon />
          </div>
          <h1 className={styles.title}>외부 접속 인증</h1>
          <p className={styles.subtitle}>
            내부망 밖에서 접속이 감지되었습니다.
            <br />
            Discord DM으로 전송된 인증코드를 입력하세요.
          </p>
        </div>

        <div className={styles.dmHint}>
          <DiscordIcon />
          <div className={styles.dmHintText}>
            {phase === "loading" ? (
              "인증 코드를 요청하는 중입니다..."
            ) : (
              <>
                <strong>Discord DM</strong>으로 6자리 코드를 전송했습니다.{" "}
                <span className={styles.dmHintMuted}>받지 못했다면 재전송을 요청하세요.</span>
              </>
            )}
          </div>
        </div>

        <div className={styles.codeBlock}>
          <div style={{ position: "relative" }}>
            <DigitBoxes code={code} focused={focused} />
            <input
              ref={inputRef}
              className={styles.codeInput}
              type="text"
              inputMode="numeric"
              pattern="\d*"
              autoComplete="one-time-code"
              value={code}
              onChange={handleCodeChange}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              disabled={phase !== "ready" || pending || codeExpired}
              aria-label="6자리 인증 코드"
            />
          </div>

          <div className={styles.codeMeta}>
            <span className={styles.attemptsLabel}>
              남은 시도 <span className={styles.attemptsValue}>{attemptsRemaining}</span>/{maxAttempts}
            </span>
            <span className={styles.expiryLabel}>
              {requestedAt ? `코드 유효시간 ${formatCountdown(secondsLeft)}` : "코드 요청 대기"}
            </span>
          </div>
        </div>

        {(error || codeExpired) && (
          <div className={styles.errorHint}>
            <span className={styles.errorMark}>!</span>
            <span className={styles.errorText}>{error ?? "코드가 만료되었습니다. 재전송해주세요."}</span>
          </div>
        )}

        <button
          className={styles.submitButton}
          type="button"
          disabled={phase !== "ready" || pending || code.length !== 6}
          onClick={() => verifyCode(code)}
        >
          {pending ? "확인 중..." : "인증하고 접속하기"}
        </button>

        <div className={styles.resendLine}>
          코드를 받지 못했나요?{" "}
          <button className={styles.resendLink} type="button" onClick={requestCode} disabled={pending}>
            Discord DM 재전송
          </button>
        </div>
      </div>

      <div className={styles.footer}>
        접속 IP {maskedIp || "-"} (외부) · 요청 시각 {requestedAt ? formatKstTimestamp(requestedAt) : "-"}
      </div>
    </div>
  );
}
