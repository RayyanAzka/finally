import type { Position } from '@/lib/types';
import { num, pct, pnlClass, signedUsd, usd } from '@/lib/format';

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="Positions">
      <div className="border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title">Positions</h2>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-ink-800 text-mute">
            <tr className="text-right">
              <th className="px-3 py-1.5 text-left font-medium">Ticker</th>
              <th className="px-2 font-medium">Qty</th>
              <th className="px-2 font-medium">Avg cost</th>
              <th className="px-2 font-medium">Price</th>
              <th className="px-2 font-medium">Unrealized P&amp;L</th>
              <th className="px-3 font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-mute">
                  You hold no positions. Use the trade bar to buy your first shares.
                </td>
              </tr>
            )}
            {positions.map((p) => {
              const pl = (p.current_price - p.avg_cost) * p.quantity;
              const plPct = p.avg_cost ? ((p.current_price - p.avg_cost) / p.avg_cost) * 100 : 0;
              return (
                <tr key={p.ticker} data-testid={`positions-row-${p.ticker}`} className="num border-t border-ink-700/70 text-right">
                  <td className="px-3 py-1.5 text-left font-sans font-semibold text-white">{p.ticker}</td>
                  <td className="px-2">{num(p.quantity, 4).replace(/\.?0+$/, '')}</td>
                  <td className="px-2">{usd(p.avg_cost)}</td>
                  <td className="px-2">{usd(p.current_price)}</td>
                  <td className={`px-2 ${pnlClass(pl)}`}>{signedUsd(pl)}</td>
                  <td className={`px-3 ${pnlClass(plPct)}`}>{pct(plPct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
