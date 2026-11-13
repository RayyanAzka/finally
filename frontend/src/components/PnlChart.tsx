'use client';
import { useMemo } from 'react';
import type { Snapshot } from '@/lib/types';
import { LineChart } from './LineChart';

export function PnlChart({ snapshots }: { snapshots: Snapshot[] }) {
  const points = useMemo(
    () =>
      snapshots
        .map((s) => ({ time: new Date(s.recorded_at).getTime() / 1000, value: s.total_value }))
        .filter((p) => Number.isFinite(p.time))
        .sort((a, b) => a.time - b.time),
    [snapshots],
  );
  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="Portfolio value over time">
      <div className="border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title">Portfolio value</h2>
      </div>
      <div data-testid="pnl-chart" data-points={points.length} className="relative min-h-[140px] flex-1">
        {points.length === 0 && <p className="absolute left-3 top-3 z-10 text-xs text-mute">Snapshots appear every 30 seconds and after each trade.</p>}
        <LineChart points={points} color="#209dd7" />
      </div>
    </section>
  );
}
