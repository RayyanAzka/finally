'use client';
import { useState } from 'react';
import type { PriceUpdate } from '@/lib/types';
import { pct, pnlClass } from '@/lib/format';
import { PriceCell } from './PriceCell';
import { Sparkline } from './Sparkline';

interface Props {
  tickers: string[];
  prices: Record<string, PriceUpdate>;
  history: Record<string, number[]>;
  selected: string | null;
  onSelect: (t: string) => void;
  onAdd: (t: string) => void | Promise<void>;
  onRemove: (t: string) => void | Promise<void>;
}

export function Watchlist({ tickers, prices, history, selected, onSelect, onAdd, onRemove }: Props) {
  const [draft, setDraft] = useState('');

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = draft.trim().toUpperCase();
    if (!t) return;
    void onAdd(t);
    setDraft('');
  };

  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="Watchlist">
      <div className="flex items-center justify-between border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title">Watchlist</h2>
        <form onSubmit={submit} className="flex gap-1">
          <input
            data-testid="watchlist-add-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add ticker"
            maxLength={6}
            aria-label="Add ticker"
            className="num w-24 rounded border border-ink-600 bg-ink-900 px-2 py-1 text-xs uppercase text-white placeholder:normal-case placeholder:text-mute"
          />
          <button
            type="submit"
            data-testid="watchlist-add-btn"
            className="rounded bg-violet px-2.5 py-1 text-xs font-semibold text-white hover:brightness-125"
          >
            Add
          </button>
        </form>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {tickers.length === 0 && <li className="px-3 py-4 text-xs text-mute">No tickers yet. Add one above to start streaming prices.</li>}
        {tickers.map((t) => {
          const p = prices[t];
          const changePct = p ? (p.change_percent ?? (p.previous_price ? ((p.price - p.previous_price) / p.previous_price) * 100 : 0)) : null;
          return (
            <li
              key={t}
              data-testid={`watchlist-row-${t}`}
              onClick={() => onSelect(t)}
              className={`group grid cursor-pointer grid-cols-[3.5rem_1fr_auto_auto] items-center gap-2 border-b border-ink-700/70 px-3 py-1.5 text-sm hover:bg-ink-700/60 ${
                selected === t ? 'border-l-2 border-l-accent bg-ink-700/70' : 'border-l-2 border-l-transparent'
              }`}
            >
              <span className="font-semibold text-white">{t}</span>
              <span className="text-right">
                <PriceCell price={p?.price} testId={`watchlist-price-${t}`} />
              </span>
              <span className={`num w-16 text-right text-xs ${changePct == null ? 'text-mute' : pnlClass(changePct)}`}>{pct(changePct)}</span>
              <span className="flex items-center gap-1">
                <Sparkline data={history[t] ?? []} />
                <button
                  data-testid={`watchlist-remove-${t}`}
                  aria-label={`Remove ${t}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    void onRemove(t);
                  }}
                  className="rounded px-1 text-mute opacity-40 hover:text-down group-hover:opacity-100"
                >
                  x
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
