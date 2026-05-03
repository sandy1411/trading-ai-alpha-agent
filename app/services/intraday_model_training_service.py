from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Market
from app.db.models.audit import AuditLog
from app.db.models.shadow import ShadowObservation
from app.db.session import SessionLocal


@dataclass(frozen=True)
class IntradayTrainingSample:
    market: str
    symbol: str
    opened_at: str
    last_marked_at: str
    entry_price: float
    current_price: float
    stop_loss: float | None
    take_profit: float | None
    confidence: float | None
    reward_risk_ratio: float | None
    expected_risk: float | None
    expected_reward: float | None
    hypothetical_notional_inr: float
    hypothetical_pnl_inr: float
    hypothetical_pnl_pct: float

    @property
    def has_stop_loss(self) -> bool:
        return self.stop_loss is not None and self.stop_loss > 0 and self.entry_price > 0

    @property
    def has_reward_risk(self) -> bool:
        return self.reward_risk_ratio is not None and self.reward_risk_ratio > 0

    @property
    def trainable(self) -> bool:
        return self.has_stop_loss and self.has_reward_risk


class IntradayModelTrainingService:
    """Builds a shadow-only intraday calibration report.

    This is deliberately not a live trading model. It summarizes whether the
    current shadow observations have enough stop-aware evidence for later human
    review and keeps the result as an auditable JSON artifact.
    """

    def __init__(
        self,
        *,
        artifact_path: Path | None = None,
        min_total_samples: int = 200,
        min_samples_per_market: int = 100,
        min_stop_loss_coverage: float = 0.95,
        max_samples: int = 5000,
    ) -> None:
        self.artifact_path = artifact_path or Path(".runtime") / "model_training" / (
            "intraday_shadow_model_report.json"
        )
        self.min_total_samples = min_total_samples
        self.min_samples_per_market = min_samples_per_market
        self.min_stop_loss_coverage = min_stop_loss_coverage
        self.max_samples = max_samples

    def status(self, db: Session | None = None) -> dict[str, Any]:
        close_session = db is None
        session = db or SessionLocal()
        try:
            return self.build_report(session, artifact_written=False)
        finally:
            if close_session:
                session.close()

    def train_shadow_only(self, db: Session | None = None) -> dict[str, Any]:
        close_session = db is None
        session = db or SessionLocal()
        try:
            report = self.build_report(session, artifact_written=True)
            self._write_artifact(report)
            session.add(
                AuditLog(
                    actor="intraday_model_training_service",
                    action="shadow_model_report_generated",
                    entity_type="intraday_shadow_model",
                    message=(
                        "Shadow-only intraday model report generated. "
                        "No order placement path is enabled."
                    ),
                    context={
                        "status": report["status"],
                        "total_samples": report["total_samples"],
                        "trainable_samples": report["trainable_samples"],
                        "artifact_path": report["artifact_path"],
                    },
                )
            )
            if close_session:
                session.commit()
            return report
        except Exception:
            if close_session:
                session.rollback()
            raise
        finally:
            if close_session:
                session.close()

    def build_report(self, session: Session, *, artifact_written: bool) -> dict[str, Any]:
        observations = session.scalars(
            select(ShadowObservation)
            .order_by(ShadowObservation.last_marked_at.desc())
            .limit(self.max_samples)
        ).all()
        samples = [self._sample_from_observation(observation) for observation in observations]
        trainable = [sample for sample in samples if sample.trainable]
        total_samples = len(samples)
        trainable_samples = len(trainable)
        stop_loss_coverage = (
            len([sample for sample in samples if sample.has_stop_loss]) / total_samples
            if total_samples
            else 0.0
        )
        market_reports = {
            market.value: self._market_report(market.value, samples)
            for market in Market
        }
        status = self._status(
            total_samples=total_samples,
            trainable_samples=trainable_samples,
            stop_loss_coverage=stop_loss_coverage,
            market_reports=market_reports,
        )
        report: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": status,
            "phase": "SHADOW_INTRADAY_MODEL_TRAINING",
            "shadow_only": True,
            "no_order_placement": True,
            "promotion_status": "LIVE_BLOCKED_BY_DESIGN",
            "artifact_written": artifact_written,
            "artifact_path": str(self.artifact_path),
            "min_total_samples_required": self.min_total_samples,
            "min_samples_per_market_required": self.min_samples_per_market,
            "min_stop_loss_coverage": self.min_stop_loss_coverage,
            "total_samples": total_samples,
            "trainable_samples": trainable_samples,
            "stop_loss_coverage": stop_loss_coverage,
            "markets": market_reports,
            "labels": self._label_counts(trainable),
            "feature_diagnostics": self._feature_diagnostics(trainable),
            "risk_controls": [
                "Training is fed only by shadow observations; it never places orders.",
                "Every trainable sample must include a deterministic stop-loss and reward/risk.",
                "A model report cannot change TRADING_MODE, LIVE_TRADING_ENABLED, or KILL_SWITCH.",
                "Promotion to live requires separate risk, compliance, broker, provider, FX, and market-calendar gates.",
            ],
            "next_actions": self._next_actions(
                total_samples=total_samples,
                trainable_samples=trainable_samples,
                stop_loss_coverage=stop_loss_coverage,
                market_reports=market_reports,
            ),
            "recent_samples": [
                {
                    "market": sample.market,
                    "symbol": sample.symbol,
                    "last_marked_at": sample.last_marked_at,
                    "entry_price": sample.entry_price,
                    "current_price": sample.current_price,
                    "stop_loss": sample.stop_loss,
                    "take_profit": sample.take_profit,
                    "reward_risk_ratio": sample.reward_risk_ratio,
                    "hypothetical_pnl_inr": sample.hypothetical_pnl_inr,
                    "hypothetical_pnl_pct": sample.hypothetical_pnl_pct,
                    "label": self._label(sample),
                }
                for sample in samples[:20]
            ],
        }
        return report

    def _write_artifact(self, report: dict[str, Any]) -> None:
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    def _status(
        self,
        *,
        total_samples: int,
        trainable_samples: int,
        stop_loss_coverage: float,
        market_reports: dict[str, dict[str, Any]],
    ) -> str:
        if total_samples == 0:
            return "WAITING_FOR_MARKET_DATA"
        if trainable_samples < self.min_total_samples:
            return "INSUFFICIENT_DATA"
        if stop_loss_coverage < self.min_stop_loss_coverage:
            return "INSUFFICIENT_STOP_LOSS_COVERAGE"
        thin_markets = [
            market
            for market, report in market_reports.items()
            if report["trainable_samples"] < self.min_samples_per_market
        ]
        if thin_markets:
            return "INSUFFICIENT_MARKET_COVERAGE"
        return "CALIBRATED_SHADOW_ONLY"

    def _sample_from_observation(self, observation: ShadowObservation) -> IntradayTrainingSample:
        metadata = observation.metadata_json or {}
        assessment = metadata.get("assessment") if isinstance(metadata, dict) else {}
        if not isinstance(assessment, dict):
            assessment = {}
        return IntradayTrainingSample(
            market=observation.market.value,
            symbol=observation.symbol,
            opened_at=observation.opened_at.isoformat(),
            last_marked_at=observation.last_marked_at.isoformat(),
            entry_price=float(observation.entry_price or 0),
            current_price=float(observation.current_price or 0),
            stop_loss=self._float_or_none(assessment.get("stop_loss")),
            take_profit=self._float_or_none(assessment.get("take_profit")),
            confidence=self._float_or_none(assessment.get("confidence")),
            reward_risk_ratio=self._float_or_none(assessment.get("reward_risk_ratio")),
            expected_risk=self._float_or_none(assessment.get("expected_risk")),
            expected_reward=self._float_or_none(assessment.get("expected_reward")),
            hypothetical_notional_inr=float(observation.hypothetical_notional_inr or 0),
            hypothetical_pnl_inr=float(observation.hypothetical_pnl_inr or 0),
            hypothetical_pnl_pct=float(observation.hypothetical_pnl_pct or 0),
        )

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _market_report(
        self,
        market: str,
        samples: list[IntradayTrainingSample],
    ) -> dict[str, Any]:
        market_samples = [sample for sample in samples if sample.market == market]
        trainable = [sample for sample in market_samples if sample.trainable]
        pnl_values = [sample.hypothetical_pnl_inr for sample in trainable]
        wins = [sample for sample in trainable if sample.hypothetical_pnl_inr > 0]
        losses = [sample for sample in trainable if sample.hypothetical_pnl_inr < 0]
        positives = sum(sample.hypothetical_pnl_inr for sample in wins)
        negatives = abs(sum(sample.hypothetical_pnl_inr for sample in losses))
        sorted_samples = sorted(trainable, key=lambda sample: sample.hypothetical_pnl_inr)
        return {
            "samples": len(market_samples),
            "trainable_samples": len(trainable),
            "stop_loss_coverage": (
                len([sample for sample in market_samples if sample.has_stop_loss])
                / len(market_samples)
                if market_samples
                else 0.0
            ),
            "hypothetical_pnl_inr": sum(pnl_values),
            "avg_hypothetical_pnl_inr": fmean(pnl_values) if pnl_values else 0.0,
            "avg_hypothetical_pnl_pct": (
                fmean([sample.hypothetical_pnl_pct for sample in trainable])
                if trainable
                else 0.0
            ),
            "win_rate": len(wins) / len(trainable) if trainable else 0.0,
            "profit_factor": positives / negatives if negatives else None,
            "avg_reward_risk_ratio": (
                fmean(
                    [
                        sample.reward_risk_ratio
                        for sample in trainable
                        if sample.reward_risk_ratio is not None
                    ]
                )
                if trainable
                else 0.0
            ),
            "labels": self._label_counts(trainable),
            "worst_samples": [
                {"symbol": sample.symbol, "pnl_inr": sample.hypothetical_pnl_inr}
                for sample in sorted_samples[:3]
            ],
            "best_samples": [
                {"symbol": sample.symbol, "pnl_inr": sample.hypothetical_pnl_inr}
                for sample in sorted_samples[-3:][::-1]
            ],
        }

    def _label_counts(self, samples: list[IntradayTrainingSample]) -> dict[str, int]:
        labels = {
            "POSITIVE": 0,
            "NEGATIVE": 0,
            "FLAT": 0,
            "STOP_AREA": 0,
            "TARGET_AREA": 0,
        }
        for sample in samples:
            labels[self._label(sample)] += 1
            if sample.stop_loss is not None and sample.current_price <= sample.stop_loss:
                labels["STOP_AREA"] += 1
            if sample.take_profit is not None and sample.current_price >= sample.take_profit:
                labels["TARGET_AREA"] += 1
        return labels

    @staticmethod
    def _label(sample: IntradayTrainingSample) -> str:
        if sample.hypothetical_pnl_pct > 0.001:
            return "POSITIVE"
        if sample.hypothetical_pnl_pct < -0.001:
            return "NEGATIVE"
        return "FLAT"

    def _feature_diagnostics(self, samples: list[IntradayTrainingSample]) -> list[dict[str, Any]]:
        features = {
            "confidence": [sample.confidence for sample in samples],
            "reward_risk_ratio": [sample.reward_risk_ratio for sample in samples],
            "expected_risk_pct": [
                self._safe_ratio(sample.expected_risk, sample.entry_price)
                for sample in samples
            ],
            "expected_reward_pct": [
                self._safe_ratio(sample.expected_reward, sample.entry_price)
                for sample in samples
            ],
            "distance_to_stop_pct": [
                self._safe_ratio(
                    sample.entry_price - sample.stop_loss
                    if sample.stop_loss is not None
                    else None,
                    sample.entry_price,
                )
                for sample in samples
            ],
            "distance_to_target_pct": [
                self._safe_ratio(
                    sample.take_profit - sample.entry_price
                    if sample.take_profit is not None
                    else None,
                    sample.entry_price,
                )
                for sample in samples
            ],
        }
        target = [sample.hypothetical_pnl_pct for sample in samples]
        diagnostics: list[dict[str, Any]] = []
        for name, values in features.items():
            paired = [
                (value, target_value)
                for value, target_value in zip(values, target, strict=False)
                if value is not None
            ]
            correlation = self._correlation([item[0] for item in paired], [item[1] for item in paired])
            diagnostics.append(
                {
                    "name": name,
                    "samples": len(paired),
                    "correlation_to_pnl_pct": correlation,
                    "directional_hint": self._directional_hint(correlation),
                }
            )
        return diagnostics

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float) -> float | None:
        if numerator is None or denominator <= 0:
            return None
        return numerator / denominator

    @staticmethod
    def _correlation(x_values: list[float], y_values: list[float]) -> float | None:
        if len(x_values) < 5 or len(y_values) < 5:
            return None
        x_mean = fmean(x_values)
        y_mean = fmean(y_values)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=False))
        x_var = sum((x - x_mean) ** 2 for x in x_values)
        y_var = sum((y - y_mean) ** 2 for y in y_values)
        if x_var == 0 or y_var == 0:
            return None
        return numerator / ((x_var * y_var) ** 0.5)

    @staticmethod
    def _directional_hint(correlation: float | None) -> str:
        if correlation is None:
            return "not_enough_variation"
        if correlation >= 0.2:
            return "positive_association"
        if correlation <= -0.2:
            return "negative_association"
        return "weak_or_no_association"

    def _next_actions(
        self,
        *,
        total_samples: int,
        trainable_samples: int,
        stop_loss_coverage: float,
        market_reports: dict[str, dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []
        if total_samples < self.min_total_samples:
            actions.append(
                f"Collect {self.min_total_samples - total_samples} more shadow observations before model review."
            )
        if trainable_samples < total_samples:
            actions.append("Reject or repair observations missing stop-loss or reward/risk metadata.")
        if stop_loss_coverage < self.min_stop_loss_coverage:
            actions.append("Keep stop-loss coverage above 95% before trusting intraday diagnostics.")
        for market, report in market_reports.items():
            missing = self.min_samples_per_market - int(report["trainable_samples"])
            if missing > 0:
                actions.append(f"Collect {missing} more trainable {market} intraday samples.")
        actions.append("Review only risk-adjusted expectancy after costs and slippage; do not optimize for raw returns.")
        actions.append("Keep live trading disabled until separate compliance and risk gates approve it.")
        return list(dict.fromkeys(actions))


intraday_model_training_service = IntradayModelTrainingService()
