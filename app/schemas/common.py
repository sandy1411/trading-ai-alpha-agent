from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=False)


def new_id() -> str:
    return str(uuid4())


class TimestampedSchema(StrictSchema):
    id: str = Field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None
