from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from math import floor
from pathlib import Path
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Market
from app.db.models.signal import AgentSignal
from app.db.models.audit import AuditLog
from app.db.models.shadow import ShadowObservation, ShadowTrainingSample
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
        min_total_samples: int | None = None,
        min_samples_per_market: int | None = None,
        min_stop_loss_coverage: float | None = None,
        max_samples: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.artifact_path = artifact_path or Path(".runtime") / "model_training" / (
            "intraday_shadow_model_report.json"
        )
        self.min_total_samples = (
            min_total_samples
            if min_total_samples is not None
            else self.settings.intraday_min_total_samples
        )
        self.min_samples_per_market = (
            min_samples_per_market
            if min_samples_per_market is not None
            else self.settings.intraday_min_samples_per_market
        )
        self.min_stop_loss_coverage = (
            min_stop_loss_coverage
            if min_stop_loss_coverage is not None
            else self.settings.intraday_min_stop_loss_coverage
        )
        self.max_samples = (
            max_samples
            if max_samples is not None
            else self.settings.intraday_training_max_samples
        )

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
        samples = self._load_samples(session)
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
            "max_samples_loaded": self.max_samples,
            "sample_goal": {
                "purpose": "long_run_shadow_evidence_gate",
                "plain_english": (
                    "The target is intentionally high so the bot keeps learning across many "
                    "market sessions before any live-trading discussion."
                ),
                "target_total_samples": self.min_total_samples,
                "target_samples_per_market": self.min_samples_per_market,
                "max_samples_loaded_per_report": self.max_samples,
            },
            "total_samples": total_samples,
            "trainable_samples": trainable_samples,
            "stop_loss_coverage": stop_loss_coverage,
            "markets": market_reports,
            "labels": self._label_counts(trainable),
            "outcome_summary": self._outcome_summary(trainable),
            "feature_diagnostics": self._feature_diagnostics(trainable),
            "risk_controls": [
                "Training is fed only by shadow observations; it never places orders.",
                "Every trainable sample must include a deterministic stop-loss and reward/risk.",
                "Loss-discipline rules can pause fresh shadow entries after repeated losing samples.",
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

    def _load_samples(self, session: Session) -> list[IntradayTrainingSample]:
        sample_rows = session.scalars(
            select(ShadowTrainingSample)
            .order_by(ShadowTrainingSample.sample_at.desc())
            .limit(self.max_samples)
        ).all()
        samples = [self._sample_from_training_sample(sample) for sample in sample_rows]
        remaining_limit = max(self.max_samples - len(samples), 0)
        if remaining_limit == 0:
            return samples

        sampled_observation_ids = [sample.observation_id for sample in sample_rows if sample.observation_id]
        sampled_signal_ids = {sample.signal_id for sample in sample_rows if sample.signal_id}

        signal_rows = self._load_unsampled_signals(session, sampled_signal_ids, remaining_limit)
        signal_samples = self._samples_from_signals(signal_rows)
        samples.extend(signal_samples)
        sampled_signal_ids.update(signal.id for signal in signal_rows)
        remaining_limit = max(self.max_samples - len(samples), 0)
        if remaining_limit == 0:
            return samples

        legacy_query = select(ShadowObservation).order_by(ShadowObservation.last_marked_at.desc())
        if sampled_observation_ids:
            legacy_query = legacy_query.where(ShadowObservation.id.not_in(sampled_observation_ids))
        if sampled_signal_ids:
            legacy_query = legacy_query.where(ShadowObservation.signal_id.not_in(sampled_signal_ids))
        legacy_observations = session.scalars(legacy_query.limit(remaining_limit)).all()
        samples.extend(
            self._sample_from_observation(observation)
            for observation in legacy_observations
        )
        return samples

    @staticmethod
    def _load_unsampled_signals(
        session: Session,
        sampled_signal_ids: set[str | None],
        limit: int,
    ) -> list[AgentSignal]:
        if limit <= 0:
            return []
        query = (
            select(AgentSignal)
            .where(AgentSignal.strategy_name == "shadow_training_observation_v1")
            .order_by(AgentSignal.created_at.desc())
            .limit(limit)
        )
        concrete_signal_ids = [signal_id for signal_id in sampled_signal_ids if signal_id]
        if concrete_signal_ids:
            query = query.where(AgentSignal.id.not_in(concrete_signal_ids))
        return list(session.scalars(query).all())

    def _samples_from_signals(self, signals: list[AgentSignal]) -> list[IntradayTrainingSample]:
        entry_state: dict[tuple[str, str, str], dict[str, Any]] = {}
        samples: list[IntradayTrainingSample] = []
        for signal in sorted(signals, key=lambda item: self._aware_datetime(item.created_at)):
            sample = self._sample_from_signal(signal, entry_state)
            if sample:
                samples.append(sample)
        return sorted(samples, key=lambda sample: sample.last_marked_at, reverse=True)

    def _sample_from_signal(
        self,
        signal: AgentSignal,
        entry_state: dict[tuple[str, str, str], dict[str, Any]],
    ) -> IntradayTrainingSample | None:
        payload = signal.payload or {}
        assessment = payload.get("assessment") if isinstance(payload, dict) else {}
        if not isinstance(assessment, dict):
            assessment = {}
        last_price = self._last_price_from_signal(signal, payload, assessment)
        if last_price is None or last_price <= 0:
            return None
        fx_rate = self._signal_fx_rate(signal, payload)
        created_at = self._aware_datetime(signal.created_at)
        key = (signal.market.value, signal.symbol, created_at.date().isoformat())
        if key not in entry_state:
            price_inr = last_price * fx_rate
            quantity = floor(self.settings.shadow_hypothesis_notional_inr / price_inr) if price_inr > 0 else 0
            entry_state[key] = {
                "opened_at": created_at,
                "entry_price": last_price,
                "quantity": quantity,
                "notional": quantity * last_price * fx_rate,
            }
        entry = entry_state[key]
        quantity = int(entry["quantity"])
        notional = float(entry["notional"])
        pnl = (last_price - float(entry["entry_price"])) * quantity * fx_rate
        return IntradayTrainingSample(
            market=signal.market.value,
            symbol=signal.symbol,
            opened_at=entry["opened_at"].isoformat(),
            last_marked_at=created_at.isoformat(),
            entry_price=float(entry["entry_price"]),
            current_price=last_price,
            stop_loss=self._float_or_none(assessment.get("stop_loss")),
            take_profit=self._float_or_none(assessment.get("take_profit")),
            confidence=self._float_or_none(assessment.get("confidence")),
            reward_risk_ratio=self._float_or_none(assessment.get("reward_risk_ratio")),
            expected_risk=self._float_or_none(assessment.get("expected_risk")),
            expected_reward=self._float_or_none(assessment.get("expected_reward")),
            hypothetical_notional_inr=notional,
            hypothetical_pnl_inr=pnl,
            hypothetical_pnl_pct=pnl / notional if notional else 0.0,
        )

    @staticmethod
    def _aware_datetime(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @staticmethod
    def _last_price_from_signal(
        signal: AgentSignal,
        payload: dict[str, Any],
        assessment: dict[str, Any],
    ) -> float | None:
        candidates = []
        if signal.market == Market.US:
            candidates.append(payload.get("last_price_usd"))
        candidates.append(payload.get("last_price"))
        metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
        candidates.append(metrics.get("last_price"))
        for value in candidates:
            parsed = IntradayModelTrainingService._float_or_none(value)
            if parsed and parsed > 0:
                return parsed
        return None

    @staticmethod
    def _signal_fx_rate(signal: AgentSignal, payload: dict[str, Any]) -> float:
        if signal.market != Market.US:
            return 1.0
        return IntradayModelTrainingService._float_or_none(payload.get("usd_inr")) or 1.0

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

    def _sample_from_training_sample(self, sample: ShadowTrainingSample) -> IntradayTrainingSample:
        metadata = sample.metadata_json or {}
        assessment = metadata.get("assessment") if isinstance(metadata, dict) else {}
        if not isinstance(assessment, dict):
            assessment = {}
        return IntradayTrainingSample(
            market=sample.market.value,
            symbol=sample.symbol,
            opened_at=sample.sample_at.isoformat(),
            last_marked_at=sample.sample_at.isoformat(),
            entry_price=float(sample.entry_price or 0),
            current_price=float(sample.current_price or 0),
            stop_loss=self._float_or_none(assessment.get("stop_loss")),
            take_profit=self._float_or_none(assessment.get("take_profit")),
            confidence=self._float_or_none(assessment.get("confidence")),
            reward_risk_ratio=self._float_or_none(assessment.get("reward_risk_ratio")),
            expected_risk=self._float_or_none(assessment.get("expected_risk")),
            expected_reward=self._float_or_none(assessment.get("expected_reward")),
            hypothetical_notional_inr=float(sample.hypothetical_notional_inr or 0),
            hypothetical_pnl_inr=float(sample.hypothetical_pnl_inr or 0),
            hypothetical_pnl_pct=float(sample.hypothetical_pnl_pct or 0),
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

    def _outcome_summary(self, samples: list[IntradayTrainingSample]) -> dict[str, Any]:
        groups: dict[tuple[str, str, str], list[IntradayTrainingSample]] = {}
        for sample in samples:
            opened_date = self._parse_datetime(sample.opened_at).date().isoformat()
            groups.setdefault((sample.market, sample.symbol, opened_date), []).append(sample)

        outcome_counts = {
            "TARGET_TOUCHED": 0,
            "STOP_TOUCHED": 0,
            "TIME_EXIT_POSITIVE": 0,
            "TIME_EXIT_NEGATIVE": 0,
            "TIME_EXIT_FLAT": 0,
        }
        symbol_pnl: dict[str, float] = {}
        market_counts: dict[str, dict[str, int]] = {
            market.value: {key: 0 for key in outcome_counts}
            for market in Market
        }
        idea_rows: list[dict[str, Any]] = []
        for (market, symbol, opened_date), group in groups.items():
            ordered = sorted(group, key=lambda sample: self._parse_datetime(sample.last_marked_at))
            first = ordered[0]
            final = ordered[-1]
            outcome = self._group_outcome(ordered)
            outcome_counts[outcome] += 1
            market_counts[market][outcome] += 1
            symbol_pnl[symbol] = symbol_pnl.get(symbol, 0.0) + final.hypothetical_pnl_inr
            idea_rows.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "opened_date": opened_date,
                    "samples": len(ordered),
                    "outcome": outcome,
                    "entry_price": first.entry_price,
                    "final_price": final.current_price,
                    "stop_loss": first.stop_loss,
                    "take_profit": first.take_profit,
                    "hypothetical_pnl_inr": final.hypothetical_pnl_inr,
                    "hypothetical_pnl_pct": final.hypothetical_pnl_pct,
                }
            )
        sorted_symbols = sorted(symbol_pnl.items(), key=lambda item: item[1])
        return {
            "ideas": len(groups),
            "counts": outcome_counts,
            "markets": market_counts,
            "net_hypothetical_pnl_inr": sum(symbol_pnl.values()),
            "target_touch_rate": outcome_counts["TARGET_TOUCHED"] / len(groups) if groups else 0.0,
            "stop_touch_rate": outcome_counts["STOP_TOUCHED"] / len(groups) if groups else 0.0,
            "best_symbols": [
                {"symbol": symbol, "pnl_inr": pnl}
                for symbol, pnl in sorted_symbols[-5:][::-1]
            ],
            "worst_symbols": [
                {"symbol": symbol, "pnl_inr": pnl}
                for symbol, pnl in sorted_symbols[:5]
            ],
            "recent_ideas": sorted(
                idea_rows,
                key=lambda row: (row["opened_date"], row["market"], row["symbol"]),
                reverse=True,
            )[:20],
        }

    def _group_outcome(self, samples: list[IntradayTrainingSample]) -> str:
        for sample in samples:
            if sample.stop_loss is not None and sample.current_price <= sample.stop_loss:
                return "STOP_TOUCHED"
            if sample.take_profit is not None and sample.current_price >= sample.take_profit:
                return "TARGET_TOUCHED"
        final = samples[-1]
        if final.hypothetical_pnl_pct > 0.001:
            return "TIME_EXIT_POSITIVE"
        if final.hypothetical_pnl_pct < -0.001:
            return "TIME_EXIT_NEGATIVE"
        return "TIME_EXIT_FLAT"

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

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
