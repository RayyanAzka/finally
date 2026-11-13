'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { PriceProvider, usePrices } from '@/lib/store';
import * as api from '@/lib/api';
import type { ChatMessage, Portfolio, Snapshot } from '@/lib/types';
import { Header } from '@/components/Header';
import { Watchlist } from '@/components/Watchlist';
import { MainChart } from '@/components/MainChart';
import { Heatmap } from '@/components/Heatmap';
import { PnlChart } from '@/components/PnlChart';
import { PositionsTable } from '@/components/PositionsTable';
import { TradeBar } from '@/components/TradeBar';
import { ChatPanel } from '@/components/ChatPanel';

function Workstation() {
  const { prices, history, status } = usePrices();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [tickers, setTickers] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);

  const refreshPortfolio = useCallback(async () => {
    try {
      setPortfolio(await api.getPortfolio());
      setSnapshots(await api.getHistory());
    } catch {
      /* keep last known state */
    }
  }, []);
  const refreshWatchlist = useCallback(async () => {
    try {
      const w = await api.getWatchlist();
      setTickers(w.map((i) => i.ticker));
      setSelected((s) => s ?? w[0]?.ticker ?? null);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refreshPortfolio();
    void refreshWatchlist();
    const id = setInterval(refreshPortfolio, 15000);
    return () => clearInterval(id);
  }, [refreshPortfolio, refreshWatchlist]);

  // Mark positions to the live SSE price so values update continuously.
  const live = useMemo(() => {
    if (!portfolio) return null;
    const positions = portfolio.positions.map((p) => ({ ...p, current_price: prices[p.ticker]?.price ?? p.current_price }));
    const total = portfolio.cash_balance + positions.reduce((s, p) => s + p.quantity * p.current_price, 0);
    return { positions, total };
  }, [portfolio, prices]);

  const onTrade = async (ticker: string, quantity: number, side: 'buy' | 'sell') => {
    await api.postTrade({ ticker, quantity, side });
    await refreshPortfolio();
  };
  const onAdd = async (t: string) => {
    try {
      await api.addWatchlist(t);
    } catch {
      /* ignore */
    }
    await refreshWatchlist();
  };
  const onRemove = async (t: string) => {
    try {
      await api.removeWatchlist(t);
    } catch {
      /* ignore */
    }
    setSelected((s) => (s === t ? null : s));
    await refreshWatchlist();
  };
  const onSend = async (text: string) => {
    setMessages((m) => [...m, { id: `u${Date.now()}`, role: 'user', content: text }]);
    setChatLoading(true);
    try {
      const r = await api.sendChat(text);
      setMessages((m) => [...m, { id: `a${Date.now()}`, role: 'assistant', content: r.message, trades: r.trades, watchlist_changes: r.watchlist_changes, errors: r.errors }]);
      await Promise.all([refreshPortfolio(), refreshWatchlist()]);
    } catch (e) {
      setMessages((m) => [...m, { id: `a${Date.now()}`, role: 'assistant', content: 'The assistant could not respond.', errors: [e instanceof Error ? e.message : 'Request failed'] }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="flex h-screen min-h-[640px] flex-col">
      <Header totalValue={live?.total ?? null} cash={portfolio?.cash_balance ?? null} status={status} />
      <main className="flex min-h-0 flex-1 gap-2 p-2">
        <div className="grid min-h-0 min-w-0 flex-1 grid-cols-12 grid-rows-[minmax(0,1.5fr)_minmax(0,1fr)_auto] gap-2">
          <div className="col-span-4 row-span-2 min-h-0">
            <Watchlist tickers={tickers} prices={prices} history={history} selected={selected} onSelect={setSelected} onAdd={onAdd} onRemove={onRemove} />
          </div>
          <div className="col-span-8 min-h-0">
            <MainChart ticker={selected} series={selected ? history[selected] ?? [] : []} price={selected ? prices[selected]?.price : null} />
          </div>
          <div className="col-span-4 min-h-0">
            <Heatmap positions={live?.positions ?? []} />
          </div>
          <div className="col-span-4 min-h-0">
            <PnlChart snapshots={snapshots} />
          </div>
          <div className="col-span-12">
            <div className="grid grid-cols-12 gap-2">
              <div className="col-span-12 xl:col-span-5">
                <TradeBar selected={selected} onTrade={onTrade} />
              </div>
              <div className="col-span-12 max-h-44 min-h-0 overflow-hidden xl:col-span-7">
                <PositionsTable positions={live?.positions ?? []} />
              </div>
            </div>
          </div>
        </div>
        <div className={chatOpen ? 'w-80 shrink-0' : 'w-10 shrink-0'}>
          <ChatPanel messages={messages} loading={chatLoading} onSend={onSend} open={chatOpen} onToggle={() => setChatOpen((o) => !o)} />
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <PriceProvider>
      <Workstation />
    </PriceProvider>
  );
}
