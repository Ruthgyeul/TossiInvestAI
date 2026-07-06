// core 트레이딩 코어 내부 HTTP API 클라이언트. 모든 요청에 Bearer 토큰을 싣는다 (docs/INTERNAL_API.md).
import type { Holding, PortfolioStatus } from "../embeds/status.js";

async function request<T>(method: "GET" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  throw new Error("Not implemented");
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

export function getOrders(): Promise<{ orders: unknown[] }> {
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

export function setSimulate(state: "on" | "off"): Promise<{ success: boolean; simulation: boolean }> {
  return request("POST", "/api/v1/control/simulate", { state });
}

export function setDryRun(state: "on" | "off"): Promise<{ success: boolean; dryRun: boolean }> {
  return request("POST", "/api/v1/control/dryrun", { state });
}

export function getSimStatus(): Promise<unknown> {
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

export function getVersion(): Promise<{ strategyVersion: string; promptVersion: string; deployedAt: string }> {
  return request("GET", "/api/v1/version");
}
