import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { PriceCell } from '@/components/PriceCell';
import { Watchlist } from '@/components/Watchlist';
import { PositionsTable } from '@/components/PositionsTable';
import { Heatmap } from '@/components/Heatmap';
import { ChatPanel } from '@/components/ChatPanel';
import { Header } from '@/components/Header';
import { parsePriceEvent } from '@/lib/store';
import { layoutTreemap } from '@/lib/treemap';
import type { ChatMessage, PriceUpdate, Position } from '@/lib/types';

afterEach(() => vi.useRealTimers());

describe('PriceCell flash', () => {
  it('flashes green on uptick, red on downtick, then fades', () => {
    vi.useFakeTimers();
    const { rerender } = render(<PriceCell price={100} testId="p" />);
    expect(screen.getByTestId('p').dataset.flash).toBe('');
    rerender(<PriceCell price={101} testId="p" />);
    expect(screen.getByTestId('p')).toHaveClass('flash-up');
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByTestId('p')).toHaveClass('flash-idle');
    rerender(<PriceCell price={99} testId="p" />);
    expect(screen.getByTestId('p')).toHaveClass('flash-down');
  });
});

describe('Watchlist', () => {
  const prices: Record<string, PriceUpdate> = {
    AAPL: { ticker: 'AAPL', price: 190.5, previous_price: 190, timestamp: 1 },
    MSFT: { ticker: 'MSFT', price: 400, previous_price: 401, timestamp: 1 },
  };
  const setup = () => {
    const h = { onSelect: vi.fn(), onAdd: vi.fn(), onRemove: vi.fn() };
    render(<Watchlist tickers={['AAPL', 'MSFT']} prices={prices} history={{ AAPL: [1, 2, 3] }} selected="AAPL" {...h} />);
    return h;
  };
  it('renders rows with prices', () => {
    setup();
    expect(screen.getByTestId('watchlist-row-AAPL')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('190.50');
    expect(screen.getByTestId('watchlist-price-MSFT')).toHaveTextContent('400.00');
  });
  it('adds (uppercased), selects and removes', () => {
    const h = setup();
    fireEvent.change(screen.getByTestId('watchlist-add-input'), { target: { value: 'pypl' } });
    fireEvent.click(screen.getByTestId('watchlist-add-btn'));
    expect(h.onAdd).toHaveBeenCalledWith('PYPL');
    fireEvent.click(screen.getByTestId('watchlist-row-MSFT'));
    expect(h.onSelect).toHaveBeenCalledWith('MSFT');
    fireEvent.click(screen.getByTestId('watchlist-remove-MSFT'));
    expect(h.onRemove).toHaveBeenCalledWith('MSFT');
    expect(h.onSelect).toHaveBeenCalledTimes(1);
  });
});

describe('Portfolio display', () => {
  const positions: Position[] = [
    { ticker: 'AAPL', quantity: 10, avg_cost: 100, current_price: 110, unrealized_pnl: 100 },
    { ticker: 'TSLA', quantity: 5, avg_cost: 200, current_price: 180, unrealized_pnl: -100 },
  ];
  it('positions table computes P&L', () => {
    render(<PositionsTable positions={positions} />);
    const aapl = screen.getByTestId('positions-row-AAPL');
    expect(aapl).toHaveTextContent('+$100.00');
    expect(aapl).toHaveTextContent('+10.00%');
    expect(screen.getByTestId('positions-row-TSLA')).toHaveTextContent('-$100.00');
  });
  it('heatmap colors profit and loss', () => {
    render(<Heatmap positions={positions} />);
    expect(screen.getByTestId('heatmap-cell-AAPL').dataset.pnl).toBe('profit');
    expect(screen.getByTestId('heatmap-cell-TSLA').dataset.pnl).toBe('loss');
  });
  it('treemap areas are proportional', () => {
    const r = layoutTreemap([{ key: 'a', value: 3 }, { key: 'b', value: 1 }]);
    const area = (k: string) => { const x = r.find((i) => i.key === k)!; return x.w * x.h; };
    expect(area('a') / area('b')).toBeCloseTo(3);
  });
  it('header shows connection status', () => {
    render(<Header totalValue={10000} cash={10000} status="reconnecting" />);
    expect(screen.getByTestId('connection-status').dataset.status).toBe('reconnecting');
    expect(screen.getByTestId('header-cash')).toHaveTextContent('$10,000.00');
  });
});

describe('SSE parsing', () => {
  it('parses ticker-keyed payload', () => {
    const u = parsePriceEvent(JSON.stringify({ AAPL: { ticker: 'AAPL', price: 1, previous_price: 1, timestamp: 1 } }));
    expect(u).toHaveLength(1);
    expect(u[0].ticker).toBe('AAPL');
  });
  it('ignores garbage', () => {
    expect(parsePriceEvent('nope')).toEqual([]);
  });
});

describe('ChatPanel', () => {
  const msgs: ChatMessage[] = [
    { id: '1', role: 'user', content: 'buy aapl' },
    {
      id: '2',
      role: 'assistant',
      content: 'Done.',
      trades: [{ ticker: 'AAPL', side: 'buy', quantity: 3, price: 190 }, { ticker: 'TSLA', side: 'buy', quantity: 999, error: 'Insufficient cash' }],
      watchlist_changes: [{ ticker: 'PYPL', action: 'add' }],
    },
  ];
  it('renders messages and inline confirmations', () => {
    render(<ChatPanel messages={msgs} loading={false} onSend={vi.fn()} open onToggle={vi.fn()} />);
    expect(screen.getByTestId('chat-message-assistant')).toHaveTextContent('Done.');
    expect(screen.getByTestId('chat-action-trade')).toHaveTextContent('Bought 3 AAPL @ $190.00');
    expect(screen.getByTestId('chat-action-error')).toHaveTextContent('Insufficient cash');
    expect(screen.getByTestId('chat-action-watchlist')).toHaveTextContent('Added PYPL to watchlist');
  });
  it('shows loading indicator and sends on submit', () => {
    const onSend = vi.fn();
    const { rerender } = render(<ChatPanel messages={[]} loading={false} onSend={onSend} open onToggle={vi.fn()} />);
    expect(screen.queryByTestId('chat-loading')).toBeNull();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hello' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    expect(onSend).toHaveBeenCalledWith('hello');
    rerender(<ChatPanel messages={[]} loading onSend={onSend} open onToggle={vi.fn()} />);
    expect(screen.getByTestId('chat-loading')).toBeInTheDocument();
  });
});
