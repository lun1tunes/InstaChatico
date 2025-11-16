from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from api_v1.comments.schemas import SimpleMeta


class StatsRangeDTO(BaseModel):
    since: int
    until: int


class MonthInsightsDTO(BaseModel):
    month: str
    range: StatsRangeDTO
    insights: Dict[str, Any] = Field(default_factory=dict)


class StatsReportPayload(BaseModel):
    period: str
    generated_at: str
    months: List[MonthInsightsDTO]


class StatsReportResponse(BaseModel):
    meta: SimpleMeta
    payload: StatsReportPayload
