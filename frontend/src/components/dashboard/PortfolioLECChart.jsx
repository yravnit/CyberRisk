import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { formatCurrency } from '../../api/client';
import { TrendingUp, ShieldAlert, AlertCircle, Info, Landmark } from 'lucide-react';

// Hoisted out of the component so Recharts does not remount it on
// every render (oxlint react/static-components).
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const val = payload[0].value;
    return (
      <div className="bg-th-surface border border-th-border p-3.5 rounded-lg shadow-soft text-xs space-y-1.5">
        <div className="font-semibold text-th-text-primary border-b border-th-border pb-1">
          Annual Exceedance Probability: {label}
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-th-text-secondary">Loss Exceedance Threshold:</span>
          <span className="font-bold text-th-brand font-mono">{formatCurrency(val)}</span>
        </div>
        <p className="text-[11px] text-th-text-muted italic pt-1">
          There is a {label} statistical probability that annual loss will exceed {formatCurrency(val)}.
        </p>
      </div>
    );
  }
  return null;
};

export const PortfolioLECChart = ({ data, loading, error, onRetry }) => {
  if (loading) {
    return (
      <Card className="w-full h-80 flex items-center justify-center">
        <div className="flex flex-col items-center text-th-text-secondary">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-th-brand mb-4" />
          <p>Loading portfolio loss exceedance curve...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-full h-80 flex items-center justify-center border-red-200 bg-red-50/50">
        <div className="flex flex-col items-center text-red-600">
          <ShieldAlert className="w-8 h-8 mb-4" />
          <p>Failed to load portfolio loss exceedance data.</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-4 text-sm font-medium hover:underline"
            >
              Try Again
            </button>
          )}
        </div>
      </Card>
    );
  }

  // No invented curve: without a pipeline run there is nothing real to plot.
  const lecData = data?.lec_points || [];
  const totalEal = data?.total_eal_usd || 0;
  const var95 = data?.total_var95_usd || 0;
  const var99 = data?.total_var99_usd || 0;
  const maxLoss = data?.max_probable_loss_usd || 0;

  if (lecData.length === 0) {
    return (
      <Card className="w-full h-80 flex items-center justify-center">
        <div className="flex flex-col items-center text-th-text-secondary text-center px-4">
          <ShieldAlert className="w-8 h-8 mb-4 text-th-text-muted" />
          <p>No portfolio loss curve available.</p>
          <p className="text-xs text-th-text-muted mt-1">
            Load a dataset to aggregate per-asset Monte Carlo distributions.
          </p>
        </div>
      </Card>
    );
  }

;

  return (
    <Card className="w-full border-th-border shadow-soft">
      <CardHeader className="pb-3 border-b border-th-border bg-th-surface-el flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <TrendingUp className="w-5 h-5 text-th-brand" />
            <CardTitle className="text-base font-semibold text-th-text-primary font-serif">
              Enterprise Loss Exceedance Curve (Portfolio LEC)
            </CardTitle>
            <Badge variant="brand">Portfolio Aggregate</Badge>
          </div>
          <p className="text-xs text-th-text-secondary mt-1">
            Open FAIR™ enterprise-wide tail-risk distribution combining loss exceedance across all operational assets.
          </p>
        </div>

        {/* Readout Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="px-3 py-1.5 rounded-md bg-th-bg border border-th-border text-center">
            <span className="text-[10px] text-th-text-muted uppercase font-semibold block">Total EAL</span>
            <span className="text-xs font-bold text-th-text-primary font-mono">{formatCurrency(totalEal)}</span>
          </div>
          <div className="px-3 py-1.5 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/40 text-center">
            <span className="text-[10px] text-amber-700 dark:text-amber-400 uppercase font-semibold block">VaR 95% (1-in-20)</span>
            <span className="text-xs font-bold text-amber-800 dark:text-amber-300 font-mono">{formatCurrency(var95)}</span>
          </div>
          <div className="px-3 py-1.5 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/40 text-center">
            <span className="text-[10px] text-red-700 dark:text-red-400 uppercase font-semibold block">VaR 99% (1-in-100)</span>
            <span className="text-xs font-bold text-red-800 dark:text-red-300 font-mono">{formatCurrency(var99)}</span>
          </div>
          <div className="px-3 py-1.5 rounded-md bg-th-surface border border-th-border text-center">
            <span className="text-[10px] text-th-text-muted uppercase font-semibold block">Max Tail Loss</span>
            <span className="text-xs font-bold text-th-text-primary font-mono">{formatCurrency(maxLoss)}</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-5">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={lecData} margin={{ top: 10, right: 15, left: 10, bottom: 5 }}>
              <defs>
                <linearGradient id="portfolioLecFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--chart-area-fill-start, #0284c7)" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="var(--chart-area-fill-end, #0369a1)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid, #e2e8f0)" />
              <XAxis
                dataKey="probability"
                stroke="var(--chart-axis, #64748b)"
                fontSize={11}
                tickLine={false}
              />
              <YAxis
                stroke="var(--chart-axis, #64748b)"
                fontSize={11}
                tickFormatter={(v) => `$${(v / 1000000).toFixed(1)}M`}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="loss_usd"
                name="Loss Threshold"
                stroke="var(--chart-area-stroke, #0284c7)"
                strokeWidth={2.5}
                fill="url(#portfolioLecFill)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 pt-3 border-t border-th-border flex flex-col sm:flex-row sm:items-center justify-between text-xs text-th-text-secondary gap-2">
          <div className="flex items-center space-x-1.5">
            <Info className="w-3.5 h-3.5 text-th-brand shrink-0" />
            <span>
              Per-asset Monte Carlo loss curves aggregated by summing loss quantiles — a
              perfect-correlation upper bound on enterprise tail risk.
            </span>
          </div>
          <span className="text-[11px] text-th-text-muted">
            Click any asset in the <strong>Asset Portfolio</strong> tab for individual asset-level LEC breakdown.
          </span>
        </div>
      </CardContent>
    </Card>
  );
};
