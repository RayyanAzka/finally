# Review: Changes Since `14550e1`

## Findings

### [P1] Reconcile the new market-data contract with the implemented subsystem before treating this plan as the build contract

`planning/PLAN.md:141` notes that the proposed market-data additions must be reconciled with the existing implementation, but the document then presents those additions as the active API contract. They are incompatible with the committed market subsystem: `backend/app/market/models.py` has no `session_open`; `cache.py` has no history buffer; `simulator.py` removes a ticker from both the simulator and cache; `stream.py` sends one unnamed event containing all prices; and unknown ticker seed prices are random rather than deterministic. In contrast, the plan requires `session_open`, a 600-point history buffer, prices retained for held tickers, one named `price` event per ticker, and hash-derived seed prices (`planning/PLAN.md:151-180`).

Frontend, portfolio, and API work implemented to this revised plan will not interoperate with the existing market component. Implement the specified contract as part of this change, or keep the present market API in the plan until the corresponding implementation change lands.

## Verification

- `git diff --check` completed without whitespace errors.
- The backend test suite could not be run in this environment because its dependency download (`watchfiles==1.1.1`) was blocked by network restrictions.
