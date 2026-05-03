# Intraday Shadow Strategy Plan

Sandy-Trading-AI must not become aggressive simply because faster trading feels more active. Intraday research is allowed only as a shadow-only evidence program until risk, broker, provider, compliance, and reconciliation gates are proven.

## Position

- No promise of profit.
- No live order placement from this plan.
- No short selling, margin, options, derivatives, leverage, or averaging down in v1.
- Every observed candidate must include entry, stop, target, reward/risk, rejection reasons, and data source.
- A losing streak reduces activity; it never increases size.

## Shadow Strategies To Study

1. Opening range continuation
   - Wait for the initial range to form.
   - Require price strength, volume confirmation, and no gap-risk blocker.
   - Stop below opening range or VWAP structure.
   - Target must clear at least 2.0 reward/risk before the idea is worth tracking.

2. VWAP pullback continuation
   - Only observe pullbacks in an intact session trend.
   - Reject extended moves that are already far from VWAP.
   - Stop below pullback swing low or VWAP failure band.
   - Exit hypothesis on failed VWAP reclaim, stop, target, or time cutoff.

3. Gap risk filter
   - This is a guardrail, not an entry strategy.
   - Blocks large adverse gaps, missing OHLC data, stale FX, or provider degradation.

4. Fast mean reversion
   - Disabled for now.
   - It is sensitive to latency, spread, and trend-day losses.
   - It requires a separate evidence review before even shadow expansion.

## Promotion Criteria

- Minimum 200 market-hours samples per active intraday profile and market.
- At least 20 reviewed trading days with stable behavior.
- Positive expectancy after conservative cost and slippage assumptions.
- No single-day shadow drawdown above 2%.
- All live-mode gates must remain fail-closed by default.
- India live automation must also satisfy current SEBI, exchange, and broker/API compliance requirements.
