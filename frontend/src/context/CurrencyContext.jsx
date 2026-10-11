import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useReducer,
  useRef,
  useState,
} from 'react';
import { setCurrencyFormatters } from '../api/client';
import {
  CURRENCY_META,
  DEFAULT_CURRENCY,
  FALLBACK_RATES,
  fetchRates,
  formatCompactValue,
  formatCurrencyValue,
  getCurrencyMeta,
  readCache,
} from '../services/exchangeRates';

const STORAGE_KEY = 'cyberrisk.currency';

const CurrencyContext = createContext(null);

function readStoredCurrency() {
  try {
    const code = window.localStorage.getItem(STORAGE_KEY);
    if (code && CURRENCY_META[code]) return code;
  } catch {
    /* ignore */
  }
  return DEFAULT_CURRENCY;
}

/**
 * Global display-currency provider.
 *
 * Base data is always in USD; the selected currency + live exchange rates are
 * used to convert every monetary figure at render time. `formatCurrency` from
 * the API client is re-bound here, so existing call sites need no changes.
 */
export const CurrencyProvider = ({ children }) => {
  const initialCache = useRef(undefined);
  if (initialCache.current === undefined) {
    initialCache.current = readCache();
  }
  const [currency, setCurrencyState] = useState(readStoredCurrency);
  const [rates, setRates] = useState(
    () => initialCache.current?.rates || { ...FALLBACK_RATES },
  );
  const [status, setStatus] = useState(() => (initialCache.current ? 'live' : 'idle'));
  const [updatedAt, setUpdatedAt] = useState(() => initialCache.current?.updatedAt ?? null);
  const [date, setDate] = useState(() => initialCache.current?.date ?? null);
  const [, forceTick] = useReducer((n) => n + 1, 0);

  const apply = useCallback((snapshot) => {
    if (!snapshot) return;
    setRates(snapshot.rates);
    setStatus(snapshot.status);
    setUpdatedAt(snapshot.updatedAt ?? null);
    setDate(snapshot.date ?? null);
  }, []);

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      apply(await fetchRates());
    } catch {
      // Keep whatever rates we already have and flag them as offline fallback.
      setStatus('fallback');
    }
  }, [apply]);

  useEffect(() => {
    if (!initialCache.current) {
      refresh();
    }
  }, [refresh]);

  const setCurrency = useCallback((code) => {
    if (!CURRENCY_META[code]) return;
    setCurrencyState(code);
    try {
      window.localStorage.setItem(STORAGE_KEY, code);
    } catch {
      /* ignore */
    }
  }, []);

  const rate = rates[currency] ?? 1;

  const format = useCallback(
    (usdValue) => formatCurrencyValue((Number(usdValue) || 0) * rate, currency),
    [rate, currency],
  );

  const formatCompact = useCallback(
    (usdValue) => formatCompactValue((Number(usdValue) || 0) * rate, currency),
    [rate, currency],
  );

  // Re-bind the shared formatters before paint so all call sites (including
  // chart tick formatters) pick up the new currency in the same commit.
  useLayoutEffect(() => {
    setCurrencyFormatters({ format, formatCompact });
    forceTick();
  }, [format, formatCompact]);

  const value = {
    currency,
    setCurrency,
    rates,
    rate,
    status,
    updatedAt,
    date,
    refresh,
    format,
    formatCompact,
    meta: getCurrencyMeta(currency),
    availableCurrencies: Object.values(CURRENCY_META),
  };

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
};

export const useCurrency = () => {
  const context = useContext(CurrencyContext);
  if (!context) {
    throw new Error('useCurrency must be used within a CurrencyProvider');
  }
  return context;
};
