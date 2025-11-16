from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from api_v1.comments.views import JsonApiError, require_service_token
from api_v1.stats_report.schemas import StatsReportResponse, StatsReportPayload
from api_v1.comments.schemas import SimpleMeta
from core.dependencies import get_generate_stats_report_use_case
from core.use_cases.generate_stats_report import (
    GenerateStatsReportUseCase,
    StatsPeriod,
    StatsReportError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats_report", tags=["Stats Report"])


@router.get("", response_model=StatsReportResponse)
async def get_stats_report(
    period: StatsPeriod = Query(StatsPeriod.LAST_MONTH),
    use_case: GenerateStatsReportUseCase = Depends(get_generate_stats_report_use_case),
):
    try:
        result = await use_case.execute(period)
    except StatsReportError as exc:
        logger.error("Stats report error | period=%s | error=%s", period.value, exc)
        raise JsonApiError(exc.status_code, 5008, str(exc))

    payload = StatsReportPayload(**result)
    return StatsReportResponse(meta=SimpleMeta(), payload=payload)
