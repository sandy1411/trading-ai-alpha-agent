from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.agentic.models import AgentDecisionRecord, HumanApprovalRecord


class AgentDecisionJournal:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(".runtime") / "agentic"

    def append(self, record: AgentDecisionRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"agent-decisions-{datetime.now(UTC).date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json", by_alias=True), default=str) + "\n")

    def read_day(self, day: date | None = None) -> list[dict[str, Any]]:
        selected_day = day or datetime.now(UTC).date()
        path = self.root / f"agent-decisions-{selected_day.isoformat()}.jsonl"
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows


class HumanApprovalQueue:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(".runtime") / "agentic"

    def enqueue(self, record: HumanApprovalRecord) -> HumanApprovalRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "human-approval-queue.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json", by_alias=True), default=str) + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        path = self.root / "human-approval-queue.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
