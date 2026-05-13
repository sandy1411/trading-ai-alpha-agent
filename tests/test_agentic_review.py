from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agentic.agents import (
    ComplianceSafetyAgent,
    DriftDetectionAgent,
    PostTradeReviewAgent,
    SignalCriticAgent,
)
from app.agentic.config import AgenticConfig
from app.agentic.journal import AgentDecisionJournal, HumanApprovalQueue
from app.agentic.models import (
    AgentDecisionStatus,
    AgentRecommendation,
    AgentSeverity,
    GenericReviewInput,
    HumanApprovalRecord,
    PostTradeReviewInput,
    SignalCriticInput,
    TradeQuality,
)
from app.agentic.orchestrator import AgenticOrchestrator
from app.agentic.policy import AgentAuthorityPolicy
from app.core.enums import Market
from app.intraday.models import Candle, MarketDataSnapshot
from app.intraday.pipeline import IntradayShadowPipeline


def _signal_input(**overrides) -> SignalCriticInput:
    payload = {
        "signalId": "signal-1",
        "symbol": "RELIANCE",
        "direction": "LONG",
        "strategyName": "VWAP_TREND_LONG",
        "marketRegime": "STRONG_BULLISH",
        "entryPrice": 100,
        "stopLoss": 99,
        "targetPrice": 102,
        "riskRewardRatio": 2.0,
        "confidenceScore": 0.7,
        "reasonCodes": ["test"],
        "candleSnapshot": {"close": 100},
        "marketSnapshot": {"last_price": 100, "vwap": 99.5},
        "sectorSnapshot": {},
        "currentOpenPositions": 0,
        "dailyPnl": 0,
        "tradesTakenToday": 0,
    }
    payload.update(overrides)
    return SignalCriticInput(**payload)


def _candles() -> tuple[Candle, ...]:
    start = datetime(2026, 5, 13, 9, 15, tzinfo=UTC)
    prices = [100, 101, 102, 103, 104]
    return tuple(
        Candle(
            timestamp=start + timedelta(minutes=index),
            open=price - 0.3,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000 + index * 300,
        )
        for index, price in enumerate(prices)
    )


def _snapshot() -> MarketDataSnapshot:
    candles = _candles()
    return MarketDataSnapshot(
        market=Market.INDIA,
        symbol="RELIANCE",
        timestamp=datetime(2026, 5, 13, 9, 30, tzinfo=UTC),
        last_price=104,
        vwap=103.6,
        volume=100000,
        previous_day_high=105,
        previous_day_low=95,
        opening_range_high_15m=103,
        opening_range_low_15m=99,
        opening_range_high_30m=104,
        opening_range_low_30m=98,
        atr=1.0,
        bid=103.98,
        ask=104.02,
        candles_1m=candles,
        candles_3m=candles,
        candles_5m=candles,
        index_trend=0.004,
        sector_trend=0.003,
        market_breadth=0.7,
        gap_pct=0.006,
        source="TEST",
    )


def test_invalid_json_agent_output_is_invalid_and_fail_safe(tmp_path) -> None:
    class BrokenSignalCritic(SignalCriticAgent):
        def _raw_review(self, payload: SignalCriticInput) -> str:
            return "{not-json"

    agent = BrokenSignalCritic(journal=AgentDecisionJournal(tmp_path))

    output, record = agent.review(_signal_input())

    assert output is None
    assert record.schema_validation_status == AgentDecisionStatus.INVALID
    assert AgentDecisionJournal(tmp_path).read_day()


def test_agent_high_severity_blocks_signal(tmp_path) -> None:
    agent = SignalCriticAgent(journal=AgentDecisionJournal(tmp_path))

    output, record = agent.review(_signal_input(marketRegime="STRONG_BEARISH"))

    assert output is not None
    assert output.severity == AgentSeverity.HIGH
    assert output.recommended_action == AgentRecommendation.BLOCK
    assert record.final_action_taken == "BLOCK"


def test_agent_authority_rejects_forbidden_actions() -> None:
    policy = AgentAuthorityPolicy(AgenticConfig())

    assert policy.validate_recommendation("FORCE_TRADE")[0] is False
    assert policy.validate_recommendation("INCREASE_RISK")[0] is False
    assert policy.validate_recommendation("ENABLE_LIVE_TRADING")[0] is False


def test_prompt_version_is_stored_in_agent_decision(tmp_path) -> None:
    agent = SignalCriticAgent(journal=AgentDecisionJournal(tmp_path))

    _, record = agent.review(_signal_input())

    assert record.prompt_version == "1.0.0"
    assert record.prompt_checksum
    assert record.input_hash


def test_compliance_agent_blocks_live_orders_enabled(tmp_path) -> None:
    agent = ComplianceSafetyAgent(journal=AgentDecisionJournal(tmp_path))

    output, record = agent.review(
        GenericReviewInput(
            payload={
                "trading_mode": "SHADOW_LIVE",
                "live_trading_enabled": False,
                "live_orders_enabled": True,
                "kill_switch": True,
            }
        )
    )

    assert output is not None
    assert "live_orders_not_disabled" in output.safety_violations
    assert record.final_action_taken == "BLOCK"


def test_post_trade_classification_distinguishes_process_from_outcome(tmp_path) -> None:
    agent = PostTradeReviewAgent(journal=AgentDecisionJournal(tmp_path))

    output, _ = agent.review(
        PostTradeReviewInput(
            tradeId="trade-1",
            symbol="RELIANCE",
            strategyName="VWAP_TREND_LONG",
            entryPrice=100,
            exitPrice=99,
            stopLoss=98,
            targetPrice=104,
            netPnl=-100,
            rulesFollowed=True,
        )
    )

    assert output is not None
    assert output.trade_quality == TradeQuality.GOOD_TRADE_BAD_OUTCOME
    assert output.requires_backtest is True


def test_drift_detection_flags_loss_cluster(tmp_path) -> None:
    agent = DriftDetectionAgent(journal=AgentDecisionJournal(tmp_path))
    trades = [{"net_pnl": -1} for _ in range(13)] + [{"net_pnl": 1} for _ in range(7)]

    output, _ = agent.review(GenericReviewInput(payload={"trades": trades}))

    assert output is not None
    assert output.drift_detected is True
    assert output.recommended_action == AgentRecommendation.DISABLE_STRATEGY_TEMPORARILY


def test_strategy_recommendation_requires_backtest_and_human_queue(tmp_path) -> None:
    journal = AgentDecisionJournal(tmp_path)
    queue = HumanApprovalQueue(tmp_path)
    orchestrator = AgenticOrchestrator(
        config=AgenticConfig(),
        journal=journal,
        approval_queue=queue,
    )

    result = orchestrator.end_of_day_review({"trades_taken": 0, "net_pnl": 0})

    assert result.records
    queued = queue.read_all()
    assert queued
    assert queued[-1]["status"] == "PENDING"


def test_human_approval_record_starts_pending(tmp_path) -> None:
    queue = HumanApprovalQueue(tmp_path)
    record = queue.enqueue(
        HumanApprovalRecord(
            changeType="RISK_CONFIG_CHANGE",
            proposedByAgent="StrategyImprovementAgent",
            evidence={"reason": "test"},
            riskImpact="MEDIUM",
        )
    )

    assert record.status == "PENDING"
    assert queue.read_all()[0]["changeType"] == "RISK_CONFIG_CHANGE"


def test_pipeline_logs_agentic_decisions_and_remains_shadow_only(tmp_path) -> None:
    journal = AgentDecisionJournal(tmp_path / "agentic")
    orchestrator = AgenticOrchestrator(config=AgenticConfig(), journal=journal)
    pipeline = IntradayShadowPipeline(agentic=orchestrator)
    pipeline.journal.root = tmp_path / "trades"

    result = pipeline.process_snapshot(_snapshot())

    assert result["orders_placed"] == 0
    assert result["shadow_only"] is True
    assert result["agentic"]["decisions"]
    assert journal.read_day()
