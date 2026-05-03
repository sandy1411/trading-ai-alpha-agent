# Compliance Notes

This is not financial advice. Trading involves risk. Past performance does not guarantee future returns. Autonomous trading can lose money.

This platform is for personal use only. The user remains responsible for broker terms, exchange rules, tax, and legal compliance.

India algo/API trading must comply with current SEBI, exchange, and broker rules. For Indian markets the platform includes compliance-readiness fields:

- `algo_id`
- `strategy_registration_status`
- `broker_approval_status`
- `exchange_algo_identifier`
- `order_tag`
- `unique_order_identifier`

`LIVE_AUTONOMOUS` for India must be blocked unless `compliance_status=APPROVED` or the user has explicitly configured the platform as compliant for the applicable broker/API flow.

The software must not promise profit, bypass deterministic controls, or allow uncontrolled LLM text to place orders.
