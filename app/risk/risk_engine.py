from __future__ import annotations

from collections.abc import Mapping

from app.core.config import Settings, get_settings
from app.core.enums import (
    AccountStatus,
    AuthStatus,
    Market,
    RiskDecisionType,
    TradeAction,
    TradingMode,
)
from app.risk.data_freshness import fx_rejection_reason, provider_freshness_reasons
from app.risk.drawdown import drawdown_reasons
from app.risk.exposure import exposure_reasons
from app.risk.kill_switch import SystemStateSnapshot
from app.risk.liquidity import liquidity_rejection_reason
from app.risk.long_only import existing_long_quantity, long_only_rejection_reason
from app.risk.position_sizing import calculate_quantity_by_risk, cap_quantity
from app.risk.rules import reward_risk_rejection_reason, stop_loss_rejection_reason
from app.risk.slippage import slippage_rejection_reason
from app.schemas.broker import BrokerHealth
from app.schemas.fx import FXRateStatus
from app.schemas.portfolio import PortfolioSnapshot
from app.schemas.provider import ProviderHealth
from app.schemas.risk import ComplianceStatus, MarketCalendarStatus, RiskConfig, RiskDecision
from app.schemas.signal import TradeCandidate


class RiskEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioSnapshot,
        broker_health: BrokerHealth | None,
        provider_health: ProviderHealth | list[ProviderHealth] | None,
        market_calendar: MarketCalendarStatus | None,
        risk_config: RiskConfig | None = None,
        fx_status: FXRateStatus | None = None,
        compliance_status: ComplianceStatus | None = None,
        system_state: SystemStateSnapshot | None = None,
        signal_id: str | None = None,
        quote_metrics: Mapping[str, float | int | None] | None = None,
    ) -> RiskDecision:
        config = risk_config or RiskConfig.from_settings(self.settings)
        state = system_state or SystemStateSnapshot.from_settings(self.settings)
        providers = (
            []
            if provider_health is None
            else provider_health
            if isinstance(provider_health, list)
            else [provider_health]
        )

        if candidate.action in {TradeAction.HOLD, TradeAction.NO_TRADE}:
            return RiskDecision(
                signal_id=signal_id,
                decision=RiskDecisionType.NO_TRADE,
                rejection_reasons=[],
                required_actions=["no_trade_requested"],
                risk_metrics={},
            )

        rejection_reasons: list[str] = []
        required_actions: list[str] = []
        risk_metrics: dict[str, float | int | str | bool] = {
            "trading_mode": state.trading_mode.value,
            "shadow_or_backtest": not state.trading_mode.is_live_capable,
        }
        normalized_quote_metrics = dict(quote_metrics) if quote_metrics is not None else None
        if normalized_quote_metrics is not None and candidate.market == Market.US and fx_status:
            normalized_quote_metrics.setdefault("fx_rate", fx_status.rate)
        require_quote_metrics = (
            state.trading_mode == TradingMode.LIVE_AUTONOMOUS
            and self.settings.live_market_quality_checks_required
        ) or (
            state.trading_mode == TradingMode.MICRO_LIVE_AUTONOMOUS
            and self.settings.micro_live_market_quality_checks_required
        )
        risk_metrics["quote_metrics_required"] = require_quote_metrics
        risk_metrics["quote_metrics_present"] = normalized_quote_metrics is not None

        if state.kill_switch:
            rejection_reasons.append("kill_switch_enabled")
        if state.trading_mode.is_live_capable and not state.live_trading_enabled:
            rejection_reasons.append("live_trading_enabled_false")
        if state.trading_mode.is_live_capable:
            if not self.settings.real_provider_required:
                rejection_reasons.append("real_provider_required_false")
            if not self.settings.broker_reconciliation_required:
                rejection_reasons.append("broker_reconciliation_required_false")
            if not self.settings.risk_engine_required:
                rejection_reasons.append("risk_engine_required_false")
            blocked_flags = {
                "allow_dummy_broker": self.settings.allow_dummy_broker,
                "allow_mock_broker": self.settings.allow_mock_broker,
                "allow_fake_market_data": self.settings.allow_fake_market_data,
                "allow_fake_order_fills": self.settings.allow_fake_order_fills,
                "allow_margin": self.settings.allow_margin,
                "allow_short_selling": self.settings.allow_short_selling,
                "allow_options": self.settings.allow_options,
                "allow_derivatives": self.settings.allow_derivatives,
                "allow_crypto": self.settings.allow_crypto,
                "allow_leveraged_etfs": self.settings.allow_leveraged_etfs,
            }
            rejection_reasons.extend(
                f"{name}_true" for name, enabled in blocked_flags.items() if enabled
            )

        if candidate.market == Market.INDIA and state.trading_mode.is_live_capable:
            if compliance_status is None:
                rejection_reasons.append("india_compliance_status_missing")
            elif compliance_status.market != candidate.market:
                rejection_reasons.append("india_compliance_market_mismatch")
            elif not compliance_status.approved:
                rejection_reasons.append("india_compliance_not_approved")
                rejection_reasons.extend(compliance_status.rejection_reasons)

        if broker_health is None:
            rejection_reasons.append("broker_health_missing")
        else:
            if broker_health.market != candidate.market:
                rejection_reasons.append("broker_market_mismatch")
            if broker_health.auth_status == AuthStatus.MISSING_CREDENTIALS:
                rejection_reasons.append("broker_credentials_missing")
            elif broker_health.auth_status != AuthStatus.VALID:
                rejection_reasons.append("broker_session_invalid")
            if broker_health.account_status != AccountStatus.ACTIVE:
                rejection_reasons.append("broker_account_not_active")
            if not broker_health.trading_enabled:
                rejection_reasons.append("broker_trading_disabled")
            if not broker_health.positions_reconciled:
                rejection_reasons.append("portfolio_reconciliation_required")

        rejection_reasons.extend(provider_freshness_reasons(providers, candidate.market))

        if market_calendar is None:
            rejection_reasons.append("market_calendar_status_missing")
        elif market_calendar.market != candidate.market:
            rejection_reasons.append("market_calendar_market_mismatch")
        elif not market_calendar.is_open:
            rejection_reasons.append("market_closed")

        fx_reason = fx_rejection_reason(candidate.market, fx_status)
        if fx_reason:
            rejection_reasons.append(fx_reason)

        stop_loss_reason = stop_loss_rejection_reason(candidate)
        if stop_loss_reason:
            rejection_reasons.append(stop_loss_reason)

        rejection_reasons.extend(drawdown_reasons(portfolio, config))

        liquidity_reason = liquidity_rejection_reason(
            candidate,
            settings=self.settings,
            quote_metrics=normalized_quote_metrics,
            require_quote_metrics=require_quote_metrics,
        )
        if liquidity_reason:
            rejection_reasons.append(liquidity_reason)
        slippage_reason = slippage_rejection_reason(
            candidate,
            settings=self.settings,
            quote_metrics=normalized_quote_metrics,
            require_quote_metrics=require_quote_metrics,
        )
        if slippage_reason:
            rejection_reasons.append(slippage_reason)
        reward_reason = reward_risk_rejection_reason(candidate, config.min_reward_risk_ratio)
        if reward_reason:
            rejection_reasons.append(reward_reason)

        open_positions_total = len([position for position in portfolio.positions if position.quantity > 0])
        open_positions_market = len(
            [
                position
                for position in portfolio.positions
                if position.quantity > 0 and position.market == candidate.market
            ]
        )
        if candidate.action == TradeAction.BUY:
            if open_positions_total >= config.max_open_positions_total:
                rejection_reasons.append("max_open_positions_total_exceeded")
            if candidate.market == Market.INDIA and open_positions_market >= config.max_open_positions_india:
                rejection_reasons.append("max_open_positions_india_exceeded")
            if candidate.market == Market.US and open_positions_market >= config.max_open_positions_us:
                rejection_reasons.append("max_open_positions_us_exceeded")

        approved_quantity = 0
        approved_capital = 0.0
        approved_risk = 0.0

        if candidate.stop_loss is not None:
            fx_rate = fx_status.rate if candidate.market == Market.US and fx_status else 1.0
            entry_price_inr = candidate.entry_price * fx_rate
            stop_loss_inr = candidate.stop_loss * fx_rate
            risk_metrics["fx_rate_used"] = fx_rate
            quantity_by_risk = calculate_quantity_by_risk(
                portfolio.total_value_inr,
                entry_price_inr,
                stop_loss_inr,
                config.max_risk_per_trade_pct,
            )
            approved_quantity, sizing_metrics = cap_quantity(
                candidate, portfolio, config, quantity_by_risk, entry_price_inr
            )
            risk_metrics.update(sizing_metrics)
            if candidate.action == TradeAction.SELL:
                available = existing_long_quantity(candidate, portfolio.positions)
                approved_quantity = min(approved_quantity, available)
            long_only_reason = long_only_rejection_reason(
                candidate, approved_quantity, portfolio.positions
            )
            if long_only_reason:
                rejection_reasons.append(long_only_reason)
            approved_capital = approved_quantity * entry_price_inr
            approved_risk = approved_quantity * abs(entry_price_inr - stop_loss_inr)
            rejection_reasons.extend(
                exposure_reasons(
                    candidate.market,
                    portfolio,
                    config,
                    approved_capital if candidate.action == TradeAction.BUY else 0,
                )
            )
        else:
            risk_metrics["quantity_by_risk"] = 0

        if candidate.action == TradeAction.BUY and portfolio.cash_inr <= 0:
            rejection_reasons.append("cash_unavailable")
        if approved_quantity <= 0 and not stop_loss_reason:
            rejection_reasons.append("position_size_zero")

        deduped_rejections = list(dict.fromkeys(rejection_reasons))
        if deduped_rejections:
            return RiskDecision(
                signal_id=signal_id,
                decision=RiskDecisionType.REJECTED,
                approved_quantity=0,
                approved_capital=0,
                approved_risk=0,
                rejection_reasons=deduped_rejections,
                required_actions=required_actions or ["resolve_risk_rejections"],
                risk_metrics=risk_metrics,
            )

        return RiskDecision(
            signal_id=signal_id,
            decision=RiskDecisionType.APPROVED,
            approved_quantity=approved_quantity,
            approved_capital=approved_capital,
            approved_risk=approved_risk,
            rejection_reasons=[],
            required_actions=required_actions,
            risk_metrics=risk_metrics,
        )
