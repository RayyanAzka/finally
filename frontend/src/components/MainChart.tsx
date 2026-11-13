'use client';
import { useMemo, useRef } from 'react';
import { LineChart } from './LineChart';
import { usd } from '@/lib/format';

/** Price chart for the selected ticker, built from the SSE history since page load. */
export function MainChart({ ticker, series, price }: { ticker: string | null; series: number[]; price?: number | null }) {
  const start = useRef(Math.floor(Date.now() / 1000));
  const points = useMemo(() => {
    const n = series.length;
    // SSE ticks arrive ~every 500ms; spread them evenly ending at "now".
    const end = Math.floor(Date.now() / 1000);
    const begin = Math.max(start.current, end - Math.ceil(n / 2));
    return series.map((v, i) => ({ time: begin + (i * (end - begin)) / Math.max(n - 1, 1), value: v }));
  }, [series]);
  const up = series.length < 2 || series[series.length - 1] >= series[0];

  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="Price chart">
      <div className="flex items-baseline justify-between border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title">{ticker ? `${ticker} price` : 'Price chart'}</h2>
        <span className="num text-sm font-semibold text-white">{ticker ? usd(price) : ''}</span>
      </div>
      <div className="relative min-h-[140px] flex-1">
        {ticker ? (
          <LineChart points={points} color={up ? '#26c281' : '#ef4b5f'} testId="main-chart" />
        ) : (
          <p className="p-4 text-xs text-mute">Select a ticker in the watchlist to chart it.</p>
        )}
      </div>
    </section>
  );
}
