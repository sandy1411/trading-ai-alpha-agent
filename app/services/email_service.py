from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import FailClosedError
from app.services.performance_service import performance_service


class EmailSummaryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_daily_summary_text(self, summary: dict[str, Any] | None = None) -> str:
        data = summary or performance_service.daily_summary()
        portfolio = data["portfolio"]
        system = data["system"]
        risk = data["risk"]
        shadow = data["shadow"]
        bot = data["bot_activity"]
        readiness = data["readiness"]
        training = data.get("training", {})
        intraday_model = training.get("intraday_model", {})
        market_intelligence = data.get("market_intelligence", {})
        agent_consensus = market_intelligence.get("agent_consensus", {})
        daily_review = data.get("daily_review", {})
        review_markets = daily_review.get("markets", {})
        india_review = review_markets.get("INDIA", {})
        us_review = review_markets.get("US", {})
        history_lines = [
            "- {date}: India {india_pnl} INR, US {us_pnl} INR, real orders {orders}".format(
                date=row.get("review_date", "-"),
                india_pnl=(row.get("INDIA") or {}).get("hypothetical_pnl_inr", 0),
                us_pnl=(row.get("US") or {}).get("hypothetical_pnl_inr", 0),
                orders=row.get("total_real_orders", 0),
            )
            for row in daily_review.get("history", [])[:5]
        ] or ["- No daily review history snapshots yet."]
        broker_lines = [
            f"- {item['broker_name']} {item['market']}: auth={item['auth_status']}, "
            f"account={item['account_status']}, ready={item['trading_enabled'] and item['positions_reconciled']}, "
            f"reasons={', '.join(item.get('rejection_reasons') or ['none'])}"
            for item in data["brokers"]
        ]
        provider_lines = [
            f"- {item['provider_name']} {item['market']}: status={item['status']}, "
            f"freshness={item['freshness_status']}, error={item.get('last_error') or 'none'}"
            for item in data["providers"]
        ]
        agent_lines = [
            f"- {item['agent_name']}: status={item['status']}, "
            f"orders_placed={item.get('orders_placed', 0)}, "
            f"summary={item.get('summary', '')}"
            for item in market_intelligence.get("agents", [])[:7]
        ] or ["- Market-intelligence agents have not produced a dashboard snapshot yet."]
        observation_lines = [
            f"- {item['symbol']} {item['market']}: entry={item['entry_price']}, "
            f"signal={(item.get('assessment') or {}).get('action', 'NO_TRADE')}, "
            f"stop={(item.get('assessment') or {}).get('stop_loss', 'n/a')}, "
            f"target={(item.get('assessment') or {}).get('take_profit', 'n/a')}, "
            f"rr={(item.get('assessment') or {}).get('reward_risk_ratio', 'n/a')}, "
            f"current={item['current_price']}, hyp_qty={item['hypothetical_quantity']}, "
            f"hyp_pnl_inr={item['hypothetical_pnl_inr']}, hyp_pnl_pct={item['hypothetical_pnl_pct']}"
            for item in shadow["recent_observations"][:10]
        ] or ["- No market-hours observations recorded yet."]
        safety = system["safety_errors"] or ["none"]
        studied = bot["studied_symbols_today"] or ["none"]
        improvements = bot["improvement_actions"] or ["Continue collecting shadow data."]
        model_next_actions = [
            f"- {item}" for item in intraday_model.get("next_actions", [])[:5]
        ] or ["- Continue collecting stop-loss-aware intraday shadow samples."]
        readiness_blockers = [
            check["name"]
            for check in readiness["checks"]
            if not check["passed"] and check["severity"] == "BLOCKER"
        ] or ["none"]
        readiness_warnings = [
            str(check["detail"] or check["name"])
            for check in readiness["checks"]
            if not check["passed"] and check["severity"] == "WARN"
        ] or ["none"]

        return "\n".join(
            [
                f"{data['app_name']} daily shadow summary",
                f"Generated: {data['generated_at']}",
                "",
                "Executive status",
                f"- Live trading: {bot['live_trading_status']}",
                f"- Shadow bot: {bot['shadow_status']}",
                f"- Current action: {bot['current_action']}",
                f"- Next India session: {readiness['next_india_session_date']}",
                "",
                "Safety",
                f"- Mode: {system['trading_mode']}",
                f"- Live enabled: {system['live_trading_enabled']}",
                f"- Kill switch: {system['kill_switch']}",
                f"- Safety errors: {', '.join(safety)}",
                f"- Readiness blockers: {', '.join(readiness_blockers)}",
                f"- Readiness warnings: {', '.join(readiness_warnings)}",
                "",
                "Capital and shadow P&L",
                "- Real capital invested by bot today: 0",
                f"- Hypothetical shadow notional INR: {shadow['hypothetical_notional_inr']}",
                f"- Hypothetical shadow P&L INR: {shadow['hypothetical_pnl_inr']}",
                f"- Hypothetical shadow P&L pct: {shadow['hypothetical_pnl_pct']}",
                f"- Winners / losers / flat: {shadow['winners']} / {shadow['losers']} / {shadow['flat']}",
                f"- Portfolio value INR: {portfolio['total_value_inr']}",
                f"- Cash INR: {portfolio['cash_inr']}",
                f"- Daily P&L INR: {portfolio['daily_pnl_inr']}",
                f"- Total drawdown pct: {portfolio['total_drawdown_pct']}",
                "",
                "What we studied today",
                f"- Symbols: {', '.join(studied)}",
                *observation_lines,
                "",
                "Daily review by market",
                (
                    f"- India {india_review.get('review_date', '-')}: signals="
                    f"{india_review.get('signals', 0)}, marks={india_review.get('shadow_hypotheses', 0)}, "
                    f"hyp_pnl_inr={india_review.get('hypothetical_pnl_inr', 0)}, "
                    f"real_orders={india_review.get('real_orders', 0)}"
                ),
                (
                    f"- US {us_review.get('review_date', '-')}: signals="
                    f"{us_review.get('signals', 0)}, marks={us_review.get('shadow_hypotheses', 0)}, "
                    f"hyp_pnl_inr={us_review.get('hypothetical_pnl_inr', 0)}, "
                    f"real_orders={us_review.get('real_orders', 0)}"
                ),
                "Recent day P&L history",
                *history_lines,
                "",
                "Risk",
                f"- Decisions today: {risk['decisions_today']}",
                f"- Risk events today: {risk['risk_events_today']}",
                f"- Max risk per trade pct: {risk['max_risk_per_trade_pct']}",
                "",
                "Intraday model training",
                f"- Status: {intraday_model.get('status', 'WAITING_FOR_MARKET_DATA')}",
                f"- Shadow only: {intraday_model.get('shadow_only', True)}",
                f"- Total samples: {intraday_model.get('total_samples', 0)}",
                f"- Trainable samples: {intraday_model.get('trainable_samples', 0)}",
                f"- Stop-loss coverage: {intraday_model.get('stop_loss_coverage', 0)}",
                *model_next_actions,
                "",
                "Market intelligence agents",
                f"- Consensus: {agent_consensus.get('status', 'WAITING')}",
                f"- Summary: {agent_consensus.get('summary', 'No consensus snapshot yet.')}",
                f"- Orders placed by agents: {market_intelligence.get('orders_placed', 0)}",
                *agent_lines,
                "",
                "Brokers",
                *broker_lines,
                "",
                "Providers",
                *provider_lines,
                "",
                "How we improve next",
                *[f"- {item}" for item in improvements],
                "",
                "Note: This summary is observation-only. It does not promise returns and does not indicate live orders were placed.",
            ]
        )

    def send_daily_summary(self) -> dict[str, str | bool]:
        if not self.settings.enable_email_summary:
            return {
                "sent": False,
                "reason": "email_summary_disabled",
                "message": "Set ENABLE_EMAIL_SUMMARY=true and SMTP settings in local .env.",
            }
        required = {
            "EMAIL_SMTP_HOST": self.settings.email_smtp_host,
            "EMAIL_SMTP_PORT": self.settings.email_smtp_port,
            "EMAIL_TO": self.settings.email_to,
        }
        if self.settings.email_smtp_require_auth:
            required["EMAIL_USERNAME"] = self.settings.email_username
            required["EMAIL_PASSWORD"] = self.settings.email_password
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise FailClosedError(f"email_settings_missing:{','.join(missing)}")

        message = EmailMessage()
        message["Subject"] = "Sandy-Trading-AI daily shadow summary"
        message["From"] = self.settings.email_username or "sandy-trading-ai@localhost"
        message["To"] = self.settings.email_to
        message.set_content(self.build_daily_summary_text())

        with smtplib.SMTP(self.settings.email_smtp_host, self.settings.email_smtp_port) as smtp:
            if self.settings.email_smtp_use_tls:
                smtp.starttls()
            if self.settings.email_smtp_require_auth:
                smtp.login(self.settings.email_username, self.settings.email_password)
            smtp.send_message(message)

        return {"sent": True, "reason": "sent", "message": "Daily summary email sent."}


email_summary_service = EmailSummaryService()
