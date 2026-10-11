/**
 * Real-time foreign-exchange rates with offline fallback.
 *
 * The dashboard's native reporting currency is USD. This module fetches live
 * rates from the Frankfurter API (ECB reference rates, keyless & CORS enabled)
 * so every monetary figure can be displayed in a user-selected currency.
 */

export const FX_BASE = 'USD';
export const DEFAULT_CURRENCY = 'USD';

const FX_ENDPOINT = 'https://api.frankfurter.app/latest';
const CACHE_KEY = 'cyberrisk.fx.v1';
const CACHE_TTL_MS = 6 * 60 * 60 * 1000; // 6 hours
const FETCH_TIMEOUT_MS = 8000;

// Backend base URL — the FastAPI service exposes /currency/rates so rates can
// be fetched (and cached server-side). Falls back to the upstream provider
// directly when the backend is unreachable.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/$/,
  '',
);

/**
 * Currencies exposed in the selector. Only codes the Frankfurter API supports
 * (ECB reference set) are included so live lookups always resolve.
 */
export const CURRENCY_META = {
  USD: { code: 'USD', symbol: '$', name: 'US Dollar', decimals: 0 },
  EUR: { code: 'EUR', symbol: '€', name: 'Euro', decimals: 0 },
  GBP: { code: 'GBP', symbol: '£', name: 'British Pound', decimals: 0 },
  INR: { code: 'INR', symbol: '₹', name: 'Indian Rupee', decimals: 0 },
  JPY: { code: 'JPY', symbol: '¥', name: 'Japanese Yen', decimals: 0 },
  AUD: { code: 'AUD', symbol: 'A$', name: 'Australian Dollar', decimals: 0 },
  CAD: { code: 'CAD', symbol: 'C$', name: 'Canadian Dollar', decimals: 0 },
  CHF: { code: 'CHF', symbol: 'CHF', name: 'Swiss Franc', decimals: 0 },
  CNY: { code: 'CNY', symbol: '¥', name: 'Chinese Yuan', decimals: 0 },
  SGD: { code: 'SGD', symbol: 'S$', name: 'Singapore Dollar', decimals: 0 },
  HKD: { code: 'HKD', symbol: 'HK$', name: 'Hong Kong Dollar', decimals: 0 },
  BRL: { code: 'BRL', symbol: 'R$', name: 'Brazilian Real', decimals: 0 },
  ZAR: { code: 'ZAR', symbol: 'R', name: 'South African Rand', decimals: 0 },
  MXN: { code: 'MXN', symbol: 'MX$', name: 'Mexican Peso', decimals: 0 },
  KRW: { code: 'KRW', symbol: '₩', name: 'South Korean Won', decimals: 0 },
  SEK: { code: 'SEK', symbol: 'kr', name: 'Swedish Krona', decimals: 0 },
  NOK: { code: 'NOK', symbol: 'kr', name: 'Norwegian Krone', decimals: 0 },
  NZD: { code: 'NZD', symbol: 'NZ$', name: 'New Zealand Dollar', decimals: 0 },
};

export const CURRENCY_CODES = Object.keys(CURRENCY_META);
const TARGET_CODES = CURRENCY_CODES.filter((code) => code !== FX_BASE);

/**
 * Approximate offline rates (1 USD = X). Used only when both the network call
 * and the browser cache are unavailable.
 */
export const FALLBACK_RATES = {
  USD: 1,
  EUR: 0.92,
  GBP: 0.79,
  INR: 83.4,
  JPY: 151.2,
  AUD: 1.52,
  CAD: 1.36,
  CHF: 0.88,
  CNY: 7.24,
  SGD: 1.34,
  HKD: 7.82,
  BRL: 5.05,
  ZAR: 18.6,
  MXN: 17.1,
  KRW: 1335,
  SEK: 10.5,
  NOK: 10.7,
  NZD: 1.64,
};

export function getCurrencyMeta(code) {
  return CURRENCY_META[code] || CURRENCY_META[DEFAULT_CURRENCY];
}

export function fallbackSnapshot() {
  return {
    base: FX_BASE,
    rates: { ...FALLBACK_RATES },
    status: 'fallback',
    updatedAt: null,
    date: null,
    source: 'fallback',
  };
}

/**
 * Read a non-expired snapshot from localStorage, or null.
 */
export function readCache() {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.rates || !parsed?.fetchedAt) return null;
    if (Date.now() - parsed.fetchedAt > CACHE_TTL_MS) return null;
    return {
      base: FX_BASE,
      rates: { [FX_BASE]: 1, ...parsed.rates },
      status: 'live',
      updatedAt: parsed.fetchedAt,
      date: parsed.date || null,
      source: 'cache',
    };
  } catch {
    return null;
  }
}

function writeCache(rates, fetchedAt, date) {
  try {
    window.localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ rates, fetchedAt, date }),
    );
  } catch {
    /* storage unavailable — ignore */
  }
}

/**
 * Fetch the latest rates from the network.
 * @returns {Promise<{base:string, rates:Object<string,number>, status:string,
 *   updatedAt:number, date:string|null, source:string}>}
 */
async function fetchJson(url, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`FX request failed with status ${res.status}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function normalizeRates(rawRates) {
  const rates = { [FX_BASE]: 1 };
  TARGET_CODES.forEach((code) => {
    const value = Number(rawRates?.[code]);
    rates[code] = Number.isFinite(value) && value > 0 ? value : FALLBACK_RATES[code];
  });
  return rates;
}

async function fetchFromBackend() {
  const payload = await fetchJson(`${API_BASE_URL}/currency/rates?base=${FX_BASE}`);
  return {
    rates: normalizeRates(payload?.rates),
    date: payload?.date || null,
    source: payload?.source === 'live' ? 'backend' : 'backend-cache',
  };
}

async function fetchFromUpstream() {
  const url = `${FX_ENDPOINT}?from=${FX_BASE}&to=${TARGET_CODES.join(',')}`;
  const payload = await fetchJson(url);
  return { rates: normalizeRates(payload?.rates), date: payload?.date || null, source: 'network' };
}

/**
 * Fetch the latest rates. Tries the backend service first (server-side cache),
 * then the upstream provider directly, and lets the caller fall back to static
 * rates if both fail.
 * @returns {Promise<{base:string, rates:Object<string,number>, status:string,
 *   updatedAt:number, date:string|null, source:string}>}
 */
export async function fetchRates() {
  let lastError;
  for (const attempt of [fetchFromBackend, fetchFromUpstream]) {
    try {
      const { rates, date, source } = await attempt();
      const fetchedAt = Date.now();
      writeCache(rates, fetchedAt, date);
      return { base: FX_BASE, rates, status: 'live', updatedAt: fetchedAt, date, source };
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error('All FX sources failed');
}

/**
 * Format an amount already expressed in the target currency.
 */
export function formatCurrencyValue(amount, code = DEFAULT_CURRENCY) {
  const meta = getCurrencyMeta(code);
  const value = Number(amount);
  if (amount === null || amount === undefined || !Number.isFinite(value)) {
    return `${meta.symbol}0`;
  }
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: meta.code,
      maximumFractionDigits: meta.decimals ?? 0,
      minimumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${meta.symbol}${Math.round(value).toLocaleString('en-US')}`;
  }
}

/**
 * Compact formatter for chart axes: $1.5M, £250k, ₹83k …
 */
export function formatCompactValue(amount, code = DEFAULT_CURRENCY) {
  const meta = getCurrencyMeta(code);
  const num = Number(amount) || 0;
  const abs = Math.abs(num);
  const prefix = meta.symbol.length > 1 ? `${meta.symbol} ` : meta.symbol;

  let body;
  if (abs >= 1e9) body = `${(num / 1e9).toFixed(1)}B`;
  else if (abs >= 1e6) body = `${(num / 1e6).toFixed(1)}M`;
  else if (abs >= 1e3) body = `${(num / 1e3).toFixed(0)}k`;
  else body = `${Math.round(num)}`;

  return `${prefix}${body}`;
}
