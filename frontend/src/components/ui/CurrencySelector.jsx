import React from 'react';
import { RefreshCw, Globe, ChevronDown } from 'lucide-react';
import { useCurrency } from '../../context/CurrencyContext';

const STATUS_META = {
  live: { dot: 'bg-th-success', label: 'Live rates' },
  loading: { dot: 'bg-th-brand animate-pulse', label: 'Updating…' },
  fallback: { dot: 'bg-th-warning', label: 'Offline fallback rates' },
  idle: { dot: 'bg-th-text-muted', label: 'Rates idle' },
};

export const CurrencySelector = ({ className = '' }) => {
  const { currency, setCurrency, availableCurrencies, rate, status, updatedAt, refresh } =
    useCurrency();
  const statusMeta = STATUS_META[status] || STATUS_META.idle;

  const updatedLabel = updatedAt
    ? new Date(updatedAt).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'not yet synced';

  const rateLabel = `1 USD = ${rate.toLocaleString('en-US', { maximumFractionDigits: 2 })} ${currency}`;

  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <div className="relative flex items-center">
        <Globe className="w-3.5 h-3.5 text-th-text-muted absolute left-2.5 pointer-events-none" />
        <select
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
          title={`Display currency — ${rateLabel}`}
          aria-label="Display currency"
          className="appearance-none pl-7 pr-7 py-1.5 text-xs font-medium rounded-lg border border-th-border bg-th-surface text-th-text-primary hover:border-th-border-strong focus:outline-none focus:border-th-accent focus:ring-1 focus:ring-th-accent cursor-pointer transition-colors"
        >
          {availableCurrencies.map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
        <ChevronDown className="w-3 h-3 text-th-text-muted absolute right-2 pointer-events-none" />
      </div>

      <button
        type="button"
        onClick={refresh}
        disabled={status === 'loading'}
        title={`${statusMeta.label} • updated ${updatedLabel}`}
        aria-label="Refresh exchange rates"
        className="p-1.5 rounded-lg border border-th-border bg-th-surface text-th-text-secondary hover:text-th-brand hover:border-th-border-strong disabled:opacity-60 transition-colors"
      >
        <RefreshCw className={`w-3.5 h-3.5 ${status === 'loading' ? 'animate-spin' : ''}`} />
      </button>

      <span className="hidden xl:inline-flex items-center gap-1 text-[10px] font-medium text-th-text-muted">
        <span className={`w-1.5 h-1.5 rounded-full ${statusMeta.dot}`} />
        {statusMeta.label}
      </span>
    </div>
  );
};
