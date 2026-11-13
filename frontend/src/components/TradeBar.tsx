'use client';
import { useEffect, useState } from 'react';

interface Props {
  selected: string | null;
  onTrade: (ticker: string, quantity: number, side: 'buy' | 'sell') => Promise<void>;
}

export function TradeBar({ selected, onTrade }: Props) {
  const [ticker, setTicker] = useState('');
  const [qty, setQty] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selected) setTicker(selected);
  }, [selected]);

  const run = async (side: 'buy' | 'sell') => {
    const q = parseFloat(qty);
    const t = ticker.trim().toUpperCase();
    if (!t || !(q > 0)) {
      setMsg({ ok: false, text: 'Enter a ticker and a quantity greater than 0.' });
      return;
    }
    setBusy(true);
    try {
      await onTrade(t, q, side);
      setMsg({ ok: true, text: `${side === 'buy' ? 'Bought' : 'Sold'} ${q} ${t}` });
      setQty('');
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Trade failed' });
    } finally {
      setBusy(false);
    }
  };

  const field = 'num rounded border border-ink-600 bg-ink-900 px-2 py-1.5 text-sm text-white placeholder:text-mute';
  return (
    <div className="panel flex flex-wrap items-center gap-2 rounded-md px-3 py-2" aria-label="Trade bar">
      <span className="panel-title mr-1">Trade</span>
      <input data-testid="trade-ticker" aria-label="Ticker" placeholder="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} className={`${field} w-24 uppercase`} />
      <input data-testid="trade-qty" aria-label="Quantity" placeholder="Quantity" type="number" min="0" step="any" value={qty} onChange={(e) => setQty(e.target.value)} className={`${field} w-28`} />
      <button data-testid="trade-buy" disabled={busy} onClick={() => run('buy')} className="rounded bg-violet px-4 py-1.5 text-sm font-semibold text-white hover:brightness-125 disabled:opacity-50">
        Buy
      </button>
      <button data-testid="trade-sell" disabled={busy} onClick={() => run('sell')} className="rounded border border-violet px-4 py-1.5 text-sm font-semibold text-white hover:bg-violet/30 disabled:opacity-50">
        Sell
      </button>
      {msg && (
        <span data-testid="trade-message" role="status" className={`text-xs ${msg.ok ? 'text-up' : 'text-down'}`}>
          {msg.text}
        </span>
      )}
    </div>
  );
}
