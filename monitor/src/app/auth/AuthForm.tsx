"use client";

import { useState, type FormEvent } from "react";
import styles from "./AuthGate.module.css";

type Step = "request" | "verify";

interface RequestCodeResponse {
  ok: boolean;
  reason?: "blocked" | "cooldown";
}

interface VerifyCodeResponse {
  ok: boolean;
  reason?: "blocked" | "invalid" | "expired";
  attemptsRemaining?: number;
}

export function AuthForm() {
  const [step, setStep] = useState<Step>("request");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [pending, setPending] = useState(false);
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);

  async function handleRequestCode() {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/request-code", { method: "POST" });
      const data: RequestCodeResponse = await res.json();
      if (!res.ok || !data.ok) {
        if (data.reason === "blocked") setBlocked(true);
        else if (data.reason === "cooldown") setError("잠시 후 다시 시도하세요.");
        else setError("코드 요청에 실패했습니다.");
        return;
      }
      setStep("verify");
    } catch {
      setError("네트워크 오류가 발생했습니다.");
    } finally {
      setPending(false);
    }
  }

  async function handleVerify(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data: VerifyCodeResponse = await res.json();
      if (!res.ok || !data.ok) {
        if (data.reason === "blocked") {
          setBlocked(true);
        } else if (data.reason === "expired") {
          setError("코드가 만료되었습니다. 다시 요청하세요.");
          setStep("request");
        } else {
          setError("코드가 일치하지 않습니다.");
          if (typeof data.attemptsRemaining === "number") setAttemptsRemaining(data.attemptsRemaining);
        }
        return;
      }
      window.location.href = "/";
    } catch {
      setError("네트워크 오류가 발생했습니다.");
    } finally {
      setPending(false);
    }
  }

  if (blocked) {
    return (
      <main className={styles.wrap}>
        <div className={styles.card}>
          <h1 className={styles.title}>접근 차단됨</h1>
          <p className={styles.body}>인증 실패 횟수를 초과해 이 네트워크에서의 접근이 차단되었습니다.</p>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.wrap}>
      <div className={styles.card}>
        <h1 className={styles.title}>BIN MONITOR — 외부 접속 인증</h1>
        <p className={styles.body}>
          내부 네트워크가 아닌 곳에서 접속했습니다. Discord DM으로 받은 인증 코드를 입력해야 대시보드를 볼 수
          있습니다.
        </p>

        {step === "request" && (
          <button className={styles.button} onClick={handleRequestCode} disabled={pending}>
            {pending ? "요청 중..." : "인증 코드 요청 (Discord DM)"}
          </button>
        )}

        {step === "verify" && (
          <form className={styles.form} onSubmit={handleVerify}>
            <label className={styles.label} htmlFor="code">
              6자리 인증 코드
            </label>
            <input
              id="code"
              className={styles.input}
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              autoFocus
            />
            <button className={styles.button} type="submit" disabled={pending || code.length !== 6}>
              {pending ? "확인 중..." : "확인"}
            </button>
            <button type="button" className={styles.linkButton} onClick={handleRequestCode} disabled={pending}>
              코드 다시 받기
            </button>
          </form>
        )}

        {error && <p className={styles.error}>{error}</p>}
        {attemptsRemaining !== null && attemptsRemaining > 0 && (
          <p className={styles.hint}>남은 시도 횟수: {attemptsRemaining}회</p>
        )}
      </div>
    </main>
  );
}
