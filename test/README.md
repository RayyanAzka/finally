# E2E tests

From repo root:
`docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright`

Selectors rely on these `data-testid`s (frontend contract): connection-status (attr data-status=connected|reconnecting|disconnected), header-cash, watchlist-row-{T}, watchlist-price-{T}, watchlist-remove-{T}, watchlist-add-input, watchlist-add-btn, trade-ticker, trade-qty, trade-buy, trade-sell, positions-row-{T}, heatmap, heatmap-cell-{T}, pnl-chart, chat-input, chat-send, chat-message-assistant.
