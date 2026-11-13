import type { Position } from '@/lib/types';
import { layoutTreemap } from '@/lib/treemap';
import { pct } from '@/lib/format';

/** Color by P&L %: green for profit, red for loss, intensity scales up to +/-10%. */
export function pnlColor(p: number): string {
  const a = Math.min(Math.abs(p) / 10, 1);
  const alpha = 0.25 + a * 0.6;
  return p >= 0 ? `rgba(38, 194, 129, ${alpha.toFixed(2)})` : `rgba(239, 75, 95, ${alpha.toFixed(2)})`;
}

export function Heatmap({ positions }: { positions: Position[] }) {
  const items = positions.map((p) => ({ key: p.ticker, value: Math.abs(p.quantity * p.current_price) }));
  const rects = layoutTreemap(items);
  const byTicker = Object.fromEntries(positions.map((p) => [p.ticker, p]));

  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="Portfolio heatmap">
      <div className="border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title">Positions heatmap</h2>
      </div>
      <div data-testid="heatmap" className="relative min-h-[100px] flex-1 p-1">
        {rects.length === 0 ? (
          <p className="p-2 text-xs text-mute">No positions yet. Buy a ticker to see it sized by weight and colored by P&amp;L.</p>
        ) : (
          <div className="absolute inset-1">
            {rects.map((r) => {
              const pos = byTicker[r.key];
              const pl = pos.avg_cost ? ((pos.current_price - pos.avg_cost) / pos.avg_cost) * 100 : 0;
              return (
                <div
                  key={r.key}
                  data-testid={`heatmap-cell-${r.key}`}
                  data-pnl={pl >= 0 ? 'profit' : 'loss'}
                  style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%`, background: pnlColor(pl) }}
                  className="absolute box-border border border-ink-900 p-1.5 text-white"
                >
                  <div className="text-sm font-bold">{r.key}</div>
                  <div className="num text-xs">{pct(pl)}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
