import React from 'react';
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';
import { formatCurrency } from '../../api/client';
import { TrendingDown, ShieldAlert } from 'lucide-react';

export const RiskTrendChart = ({ data, loading, error, onRetry }) => {
  if (loading) {
    return (
      <Card className="w-full h-80 flex items-center justify-center">
        <div className="flex flex-col items-center text-th-text-secondary">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-th-brand mb-4" />
          <p>Loading risk trend data...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-full h-80 flex items-center justify-center border-red-200 bg-red-50/50">
        <div className="flex flex-col items-center text-red-600">
          <ShieldAlert className="w-8 h-8 mb-4" />
          <p>Failed to load risk trend.</p>
          <button 
            onClick={onRetry}
            className="mt-4 text-sm font-medium hover:underline"
          >
            Try Again
          </button>
        </div>
      </Card>
    );
  }

  // Fallback default data
  const defaultData = [
    { label: '6mo ago', total_EAL_usd: 8500000, total_VaR95_usd: 12000000, controls_deployed: 45 },
    { label: '5mo ago', total_EAL_usd: 8100000, total_VaR95_usd: 11500000, controls_deployed: 48 },
    { label: '4mo ago', total_EAL_usd: 7500000, total_VaR95_usd: 10800000, controls_deployed: 52 },
    { label: '3mo ago', total_EAL_usd: 6200000, total_VaR95_usd: 9500000, controls_deployed: 61 },
    { label: '2mo ago', total_EAL_usd: 5800000, total_VaR95_usd: 9000000, controls_deployed: 65 },
    { label: '1mo ago', total_EAL_usd: 5500000, total_VaR95_usd: 8600000, controls_deployed: 68 },
    { label: 'Current', total_EAL_usd: 5100000, total_VaR95_usd: 8100000, controls_deployed: 72 },
  ];

  const chartData = data && data.length > 0 ? data : defaultData;
  const currentItem = chartData[chartData.length - 1] || {};
  const sixMoAgoItem = chartData[0] || {};
  
  const currentEAL = currentItem.total_EAL_usd || 0;
  const oldEAL = sixMoAgoItem.total_EAL_usd || 0;
  
  const pctChange = oldEAL > 0 ? ((currentEAL - oldEAL) / oldEAL) * 100 : 0;
  const isPositive = pctChange > 0;

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-th-surface border border-th-border p-3 rounded-lg shadow-soft text-sm">
          <div className="font-medium text-th-text-primary mb-2 border-b border-th-border pb-1">{label}</div>
          {payload.map((entry, index) => (
            <div key={index} className="flex items-center justify-between gap-4 mb-1">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                <span className="text-th-text-secondary">{entry.name}:</span>
              </div>
              <span className="font-semibold text-th-text-primary">
                {entry.name === 'Controls' ? entry.value : formatCurrency(entry.value)}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <Card className="w-full">
      <CardHeader className="pb-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <CardTitle>Risk Trend Analysis</CardTitle>
          <p className="text-xs text-th-text-secondary mt-1">Expected Annual Loss trajectory over time</p>
        </div>
        
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex flex-col bg-th-surface-el px-3 py-1.5 rounded-md border border-th-border">
            <span className="text-[10px] text-th-text-muted uppercase font-semibold">Current EAL</span>
            <span className="font-serif font-bold text-th-text-primary">{formatCurrency(currentEAL)}</span>
          </div>
          
          <div className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md border ${isPositive ? 'bg-red-50 border-red-200 text-red-700' : 'bg-green-50 border-green-200 text-green-700'}`}>
            {isPositive ? <TrendingDown className="w-4 h-4 rotate-180" /> : <TrendingDown className="w-4 h-4" />}
            <div className="flex flex-col">
              <span className="text-[10px] uppercase font-semibold opacity-80">6mo Change</span>
              <span className="text-xs font-bold font-serif">{isPositive ? '+' : ''}{pctChange.toFixed(1)}%</span>
            </div>
          </div>
          
          <div className="flex flex-col bg-th-surface-el px-3 py-1.5 rounded-md border border-th-border">
            <span className="text-[10px] text-th-text-muted uppercase font-semibold">Controls Deployed</span>
            <span className="font-serif font-bold text-th-text-primary">{currentItem.controls_deployed || 0}</span>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        <div className="h-72 mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="ealGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--th-brand)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--th-brand)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--th-border)" opacity={0.5} />
              <XAxis 
                dataKey="label" 
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#9ca3af', fontSize: 12 }}
                dy={10}
              />
              <YAxis 
                yAxisId="left"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#9ca3af', fontSize: 12 }}
                tickFormatter={(val) => `$${(val / 1000000).toFixed(1)}M`}
                width={70}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }} />
              <Area 
                yAxisId="left"
                type="monotone" 
                dataKey="total_EAL_usd" 
                name="EAL" 
                stroke="var(--th-brand)" 
                fillOpacity={1} 
                fill="url(#ealGradient)" 
                strokeWidth={2}
              />
              <Line 
                yAxisId="left"
                type="monotone" 
                dataKey="total_VaR95_usd" 
                name="95% VaR" 
                stroke="#eab308" 
                strokeWidth={2}
                dot={{ r: 3, fill: '#eab308' }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};
