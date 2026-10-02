# Calculation

The calculator walks each outcome's asks from lowest price upward. It first determines the available quantity on each side, then prices both sides again at their common executable quantity. Automatic scanning covers Yes/No markets; inspect can calculate a two-outcome market with other labels while preserving its original outcome/token mapping.

All amounts below use the market's dollar-denominated collateral unit (pUSD for current markets). One complete pair is modeled as a settlement value of 1; this is a snapshot estimate, not a real redemption or trade.

```text
executable = min(first-side available, second-side available, target)
settlement = executable × 1
book cost  = first-side cost + second-side cost
gross      = settlement - book cost
fee(level) = consumed shares × fee rate × price × (1 - price)
fees       = sum of fees at every consumed level on both sides
slippage   = book cost × slippage rate
safety     = book cost × safety rate
net        = gross - fees - slippage - safety - extra cost
budget     = book cost + fees + slippage + safety + extra cost
net ROI    = net / budget
```

BUY taker fees are modeled as extra collateral cost. Fees are calculated at each consumed price level, not at the average price, and rounded half-up to five decimal places per level. Only an explicit `feesEnabled=false` yields zero fees; otherwise a validated rate with supported exponent `1` is required. The internal `base_fee_bps` field stores `rate × 1000` for compatibility; the fee function divides by 1000 to recover the rate.

`total_cost` in API results is book cost only; the ROI denominator is the all-in budget above. Slippage and safety buffers are each rounded half-up to six decimal places. `extra_cost` is an additional fixed allowance: scanner configuration defaults to 0.05; `/api/inspect` defaults to quantity 100 and extra cost 0.05. It does not discover actual gas, redemption, or execution costs.

Financial values use Python `Decimal`. Orderbook normalization merges duplicate levels, rejects invalid/negative/non-finite values, and sorts bids descending and asks ascending. Display rounding does not feed back into calculations.

The calculator rejects a shared asset on both legs, conflicting book conditions, or a supplied expected condition that differs from either book. `INVALID_PAIR`, `INVALID_BOOK`, `CROSSED_BOOK`, and `INVALID_CALCULATION` preserve these structural failures instead of hiding them behind freshness or minimum-size messages. Unrepresentable Decimal arithmetic produces an unusable result rather than terminating the scanner. A fee-enabled market with a missing or unsupported exponent remains `FEE_UNKNOWN`; it does not default to exponent `1`.

Partial depth is explicitly marked `PARTIAL`; automatic opportunity filtering accepts only `VALID`, so partial results cannot become candidates. Empty asks, unknown fees, unknown minimum order size (`MIN_ORDER_UNKNOWN`), stale quotes, quantities below the market minimum order size, unavailable markets, or results below configured quantity/profit/ROI thresholds cannot become valid candidates. The runtime rechecks the original REST books and current source age when displaying a candidate or saving a simulation. A mathematical `VALID` result can have a negative net difference and is distinct from passing all candidate gates. A positive snapshot estimate does not establish that both legs can execute or that settlement will occur as assumed.
