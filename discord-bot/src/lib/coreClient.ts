// core 트레이딩 코어 내부 HTTP API 클라이언트. 모든 요청에 Bearer 토큰을 싣는다 (docs/INTERNAL_API.md).
//
// Node 18+ 전역 fetch를 사용한다 — 새 HTTP 클라이언트 의존성을 추가하지 않는다.
import { config } from "../config.js";
import type { Holding, PortfolioStatus } from "../embeds/status.js";

const REQUEST_TIMEOUT_MS = 5_000;

export class CoreApiError extends Error {}

async function request<T>(method: "GET" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${config.core.apiUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${config.core.apiToken}`,
        "Content-Type": "application/json",
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok && response.status !== 202) {
      throw new CoreApiError(`core API ${method} ${path} -> HTTP ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof CoreApiError) throw err;
    throw new CoreApiError(`core API ${method} ${path} 요청 실패: ${(err as Error).message}`);
  } finally {
    clearTimeout(timeout);
  }
}

export interface OrderResult {
  approved: boolean;
  reason?: string;
  orderId?: string;
  fillPrice?: number;
}

export function getStatus(market?: "KR" | "US"): Promise<{ live: PortfolioStatus | null; simulation: PortfolioStatus }> {
  return request("GET", market ? `/api/v1/status?market=${market}` : "/api/v1/status");
}

export function getHoldings(market?: "KR" | "US"): Promise<{ holdings: Holding[] }> {
  return request("GET", market ? `/api/v1/holdings?market=${market}` : "/api/v1/holdings");
}

export interface OrderRecord {
  orderId: string;
  symbol: string;
  market: "KR" | "US";
  action: "BUY" | "SELL";
  quantity: number;
  price: number | null;
  status: string;
  createdAt: string;
}

export function getOrders(): Promise<{ orders: OrderRecord[] }> {
  return request("GET", "/api/v1/orders");
}

export function placeBuyOrder(symbol: string, quantity: number, price?: number): Promise<OrderResult> {
  return request("POST", "/api/v1/orders/buy", { symbol, quantity, price });
}

export function placeSellOrder(symbol: string, quantity: number, price?: number): Promise<OrderResult> {
  return request("POST", "/api/v1/orders/sell", { symbol, quantity, price });
}

export function cancelOrder(orderId: string): Promise<{ success: boolean; reason?: string }> {
  return request("POST", `/api/v1/orders/${orderId}/cancel`);
}

export function stopTrading(market?: "KR" | "US"): Promise<{
  success: boolean;
  emergencyStop: boolean;
  krStop: boolean;
  usStop: boolean;
}> {
  return request("POST", "/api/v1/control/stop", market ? { market } : {});
}

export function resumeTrading(): Promise<{ success: boolean }> {
  return request("POST", "/api/v1/control/resume", {});
}

export function setSimulate(
  state: "on" | "off",
): Promise<{ success: boolean; simulation: boolean; reason?: string }> {
  return request("POST", "/api/v1/control/simulate", { state });
}

export function setDryRun(state: "on" | "off"): Promise<{ success: boolean; dryRun: boolean }> {
  return request("POST", "/api/v1/control/dryrun", { state });
}

export interface SimStatus {
  startedAt: string | null;
  seedKrw: number;
  totalValueKrw: number;
  cumulativeReturnPct: number;
  mdd: number;
  sharpeRatio: number;
  tradeCount: number;
  winRate: number;
  avgHoldingDays: number;
  rejectionCount: number;
  apiCostKrw: number;
  apiCallCount: number;
}

export function getSimStatus(): Promise<SimStatus> {
  return request("GET", "/api/v1/simstatus");
}

export function generateReport(market?: "KR" | "US" | "ALL"): Promise<{ jobId: string }> {
  return request("POST", "/api/v1/reports/generate", market ? { market } : {});
}

export function getFund(): Promise<{
  operatingFundsKrw: number;
  cashBufferKrw: number;
  cumulativeReturnPct: number;
  positionRatios: { symbol: string; ratio: number }[];
}> {
  return request("GET", "/api/v1/fund");
}

export function getApiCost(): Promise<{ monthCostKrw: number; monthCostUsd: number; callCount: number }> {
  return request("GET", "/api/v1/fund/apicost");
}

export function getWatchlist(market?: "KR" | "US"): Promise<{
  items: { symbol: string; market: string; priority: number }[];
}> {
  return request("GET", market ? `/api/v1/watchlist?market=${market}` : "/api/v1/watchlist");
}

export function addWatchlistItem(symbol: string, market: "KR" | "US"): Promise<{ success: boolean }> {
  return request("POST", "/api/v1/watchlist", { symbol, market });
}

export function removeWatchlistItem(symbol: string): Promise<{ success: boolean }> {
  return request("DELETE", `/api/v1/watchlist/${symbol}`);
}

export function runBacktest(strategy: string, period: "1Y" | "3Y" | "5Y"): Promise<{ jobId: string }> {
  return request("POST", "/api/v1/backtest", { strategy, period });
}

export function getHealth(): Promise<{
  cpuPct: number;
  memoryPct: number;
  diskPct: number;
  tempC: number;
  tossApiReachable: boolean;
}> {
  return request("GET", "/api/v1/health");
}

export function getVersion(): Promise<{ strategyVersion: string; promptVersion: string; deployedAt: string | null }> {
  return request("GET", "/api/v1/version");
}

export interface VersionCandidate {
  id: number;
  market: "KR" | "US";
  strategyVersion: string;
  promptVersion: string;
  basedOn: string | null;
  changeSummary: string | null;
  backtestResult: { winRate: number; avgReturn: number; mdd: number; sharpeRatio: number; profitFactor: number } | null;
  proposedAt: string;
}

export function getVersionCandidates(): Promise<{ candidates: VersionCandidate[] }> {
  return request("GET", "/api/v1/version/candidates");
}

export function approveVersionCandidate(
  id: number,
  approvedBy: string,
): Promise<{ success: boolean; reason?: string }> {
  return request("POST", `/api/v1/version/${id}/approve`, { approvedBy });
}

export function rejectVersionCandidate(id: number): Promise<{ success: boolean; reason?: string }> {
  return request("POST", `/api/v1/version/${id}/reject`, {});
}

export function rollbackVersion(
  strategyVersion: string,
  approvedBy: string,
): Promise<{ success: boolean; reason?: string }> {
  return request("POST", "/api/v1/version/rollback", { strategyVersion, approvedBy });
}
