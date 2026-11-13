import { Page } from '@playwright/test';

export const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

export const money = (s: string | null) => parseFloat((s ?? '').replace(/[^0-9.\-]/g, ''));

export async function cash(page: Page) {
  return money(await page.getByTestId('header-cash').textContent());
}

export async function trade(page: Page, ticker: string, qty: number, side: 'buy' | 'sell') {
  await page.getByTestId('trade-ticker').fill(ticker);
  await page.getByTestId('trade-qty').fill(String(qty));
  await page.getByTestId(`trade-${side}`).click();
}

// Reset state between tests via the public API (no reset endpoint exists).
export async function resetState(page: Page) {
  const p = await (await page.request.get('/api/portfolio')).json();
  for (const pos of p.positions ?? []) {
    await page.request.post('/api/portfolio/trade', {
      data: { ticker: pos.ticker, quantity: pos.quantity, side: 'sell' },
    });
  }
  const w = await (await page.request.get('/api/watchlist')).json();
  const list: any[] = Array.isArray(w) ? w : (w.watchlist ?? w.tickers ?? []);
  for (const item of list) {
    const t = typeof item === 'string' ? item : item.ticker;
    if (!DEFAULT_TICKERS.includes(t)) await page.request.delete(`/api/watchlist/${t}`);
  }
  for (const t of DEFAULT_TICKERS) {
    await page.request.post('/api/watchlist', { data: { ticker: t } });
  }
}
