from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable

from app.intraday.models import JournalEntry


class TradeJournal:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(".runtime") / "intraday_shadow"
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, entry: JournalEntry) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(entry.timestamp.date())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.model_dump(), sort_keys=True) + "\n")

    def read_day(self, day: date | None = None) -> list[dict]:
        path = self._path(day or datetime.now(UTC).date())
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def read_many(self, days: Iterable[date]) -> list[dict]:
        rows: list[dict] = []
        for day in days:
            rows.extend(self.read_day(day))
        return rows

    def _path(self, day: date) -> Path:
        return self.root / f"journal-{day.isoformat()}.jsonl"
