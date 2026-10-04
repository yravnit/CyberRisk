import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import { Building2, Layers } from 'lucide-react';
import { formatCurrency } from '../../api/client';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-th-surface-el p-3 rounded-lg border border-th-border shadow-elevated text-xs space-y-1.5 min-w-[210px] z-50">
        <div className="font-semibold text-th-text-primary border-b border-th-border pb-1.5 flex items-center justify-between font-serif">
          <span>{data.business_unit}</span>
          <span className="text-[10px] text-th-brand font-mono font-medium">BU Exposure</span>
        </div>
        <div className="flex justify-between items-center text-th-text-secondary pt-1">
          <span>Total EAL:</span>
          <span className="font-mono font-bold text-th-text-primary tabular-nums">{formatCurrency(data.total_EAL_usd)}</span>
        </div>
        <div className="flex justify-between items-center text-th-text-secondary">
          <span>VaR 95% Bound:</span>
          <span className="font-mono font-semibold text-th-warning tabular-nums">
            {formatCurrency(data.total_VaR95_usd_upper_bound || data.total_VaR95_usd)}
          </span>
        </div>
        {data.top_contributors && (
          <div className="pt-2 mt-1 text-[11px] text-th-text-muted border-t border-th-border">
            <span className="font-medium text-th-text-secondary">Top Contributors: </span>
            <span className="font-mono">
              {Array.isArray(data.top_contributors)
                ? data.top_contributors.join(', ')
                : String(data.top_contributors)}
            </span>
          </div>
        )}
      </div>
    );
  }
  return null;
};

export const BusinessUnitChart = ({ data = [], loading, error, onRetry }) => {
  if (loading) {
    return (
      <Card className="h-[360px] flex flex-col justify-center items-center p-6">
        <div className="w-7 h-7 rounded-full border-2 border-th-brand border-t-transparent animate-spin mb-3"></div>
        <p className="text-sm text-th-text-muted font-medium">Aggregating Business Unit Risk Exposures...</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="h-[360px] flex flex-col justify-center items-center p-6 border-th-danger/30 bg-th-danger-tint">
        <p className="text-sm font-semibold text-th-danger mb-2 font-serif">Error loading Business Unit Risk</p>
        <p className="text-xs text-th-danger/90 mb-4 text-center max-w-sm">{error}</p>
        {onRetry && (
          <Button onClick={onRetry} variant="danger" size="sm">
            Retry
          </Button>
        )}
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card className="h-[360px] flex flex-col justify-center items-center p-6 text-center">
        <Layers className="w-8 h-8 text-th-text-muted mb-3" />
        <p className="text-sm font-semibold text-th-text-primary font-serif">No Business Unit Data</p>
        <p className="text-xs text-th-text-muted mt-1">Run the risk pipeline to populate metrics.</p>
      </Card>
    );
  }

  // Sort descending by total_EAL_usd (highest risk first)
  const sortedData = [...data].sort((a, b) => (b.total_EAL_usd || 0) - (a.total_EAL_usd || 0));

  return (
    <Card className="flex flex-col h-full justify-between p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-th-brand-tint text-th-brand shadow-soft">
            <Building2 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-th-text-primary font-serif">
              Risk Exposure by Business Unit
            </h3>
            <p className="text-xs text-th-text-secondary mt-0.5">
              Annualized loss magnitude across operational divisions
            </p>
          </div>
        </div>
        <Badge variant="brand">
          {sortedData.length} Units
        </Badge>
      </div>

      <div className="w-full h-[270px] mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={sortedData}
            layout="vertical"
            margin={{ top: 5, right: 20, left: 5, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
              stroke="var(--chart-axis)"
              fontSize={11}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="business_unit"
              stroke="var(--chart-axis)"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              width={110}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--surface-elevated)' }} />
            <Bar dataKey="total_EAL_usd" radius={[0, 4, 4, 0]}>
              {sortedData.map((entry, index) => {
                const fillVar = 
                  index === 0 ? 'var(--chart-bar-1)' :
                  index === 1 ? 'var(--chart-bar-2)' :
                  index === 2 ? 'var(--chart-bar-3)' :
                  'var(--chart-bar-4)';
                return <Cell key={`cell-${index}`} fill={fillVar} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};
