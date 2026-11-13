import { test, expect } from '@playwright/test';
import { DEFAULT_TICKERS, cash, trade, resetState } from './helpers';

test.beforeEach(async ({ page }) => {
  await resetState(page);
  await page.goto('/');
});

test('fresh start: default watchlist, cash, streaming prices', async ({ page }) => {
  for (const t of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${t}`)).toBeVisible();
  }
  await expect(page.getByTestId('header-cash')).toContainText('10,000');
  await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected');
  const price = page.getByTestId('watchlist-price-AAPL');
  await expect(price).toHaveText(/\d/);
  const first = await price.textContent();
  await expect.poll(async () => price.textContent(), { timeout: 15_000 }).not.toBe(first);
});

test('add and remove a ticker', async ({ page }) => {
  await page.getByTestId('watchlist-add-input').fill('PYPL');
  await page.getByTestId('watchlist-add-btn').click();
  await expect(page.getByTestId('watchlist-row-PYPL')).toBeVisible();
  await page.getByTestId('watchlist-remove-PYPL').click();
  await expect(page.getByTestId('watchlist-row-PYPL')).toHaveCount(0);
});

test('buy then sell shares', async ({ page }) => {
  await expect.poll(() => cash(page)).toBeGreaterThan(0);
  const start = await cash(page);
  await trade(page, 'AAPL', 5, 'buy');
  await expect(page.getByTestId('positions-row-AAPL')).toBeVisible();
  await expect.poll(() => cash(page)).toBeLessThan(start);

  const afterBuy = await cash(page);
  await trade(page, 'AAPL', 2, 'sell');
  await expect.poll(() => cash(page)).toBeGreaterThan(afterBuy);
  await expect(page.getByTestId('positions-row-AAPL')).toBeVisible();

  await trade(page, 'AAPL', 3, 'sell');
  await expect(page.getByTestId('positions-row-AAPL')).toHaveCount(0);
});

test('portfolio visualizations render', async ({ page }) => {
  await trade(page, 'MSFT', 3, 'buy');
  await expect(page.getByTestId('positions-row-MSFT')).toBeVisible();
  await expect(page.getByTestId('heatmap')).toBeVisible();
  await expect(page.getByTestId('heatmap-cell-MSFT')).toBeVisible();
  await expect(page.getByTestId('pnl-chart')).toBeVisible();
  const hist = await (await page.request.get('/api/portfolio/history')).json();
  const pts = Array.isArray(hist) ? hist : (hist.snapshots ?? hist.history ?? []);
  expect(pts.length).toBeGreaterThan(0);
});

test('AI chat (mocked) responds', async ({ page }) => {
  await page.getByTestId('chat-input').fill('Hello, how is my portfolio?');
  await page.getByTestId('chat-send').click();
  const reply = page.getByTestId('chat-message-assistant').first();
  await expect(reply).toBeVisible();
  expect((await reply.textContent())?.length).toBeGreaterThan(0);
});

test('API: trade validation rejects oversell and overspend', async ({ page }) => {
  const before = (await (await page.request.get('/api/portfolio')).json()).cash_balance;
  const r1 = await page.request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', quantity: 1000, side: 'sell' } });
  expect(r1.status()).toBeGreaterThanOrEqual(400);
  const r2 = await page.request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', quantity: 1e6, side: 'buy' } });
  expect(r2.status()).toBeGreaterThanOrEqual(400);
  const after = (await (await page.request.get('/api/portfolio')).json()).cash_balance;
  expect(after).toBe(before);
});

test('SSE resilience: reconnects after stream drop', async ({ page }) => {
  // Block the stream, reload so the first connection attempt fails, then restore it.
  await page.route('**/api/stream/prices', (route) => route.abort());
  await page.reload();
  const status = page.getByTestId('connection-status');
  await expect(status).not.toHaveAttribute('data-status', 'connected');
  await page.unroute('**/api/stream/prices');
  await expect(status).toHaveAttribute('data-status', 'connected', { timeout: 30_000 });
});

test('AI chat (mocked) executes a trade inline', async ({ page }) => {
  await page.getByTestId('chat-input').fill('buy 2 AAPL');
  await page.getByTestId('chat-send').click();
  await expect(page.getByTestId('chat-action-trade').first()).toBeVisible();
  await expect(page.getByTestId('positions-row-AAPL')).toBeVisible();
});
