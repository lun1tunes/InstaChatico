import pytest
from httpx import AsyncClient
from sqlalchemy import select

from core.models.stats_report import StatsReport


@pytest.mark.asyncio
async def test_instagram_insights_stats_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    instagram_service.insights_default_response = {
        "success": True,
        "data": {"data": [{"metric": "views"}]},
    }

    response = await client.get("/api/v1/stats/instagram_insights?period=last_month")

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["period"] == "last_month"
    assert len(body["payload"]["months"]) >= 1
    first_month = body["payload"]["months"][0]
    assert first_month["insights"]["engagement"]["data"][0]["metric"] == "views"

    async with session_factory() as session:
        reports = (await session.execute(select(StatsReport))).scalars().all()
        assert len(reports) >= 1


@pytest.mark.asyncio
async def test_instagram_insights_stats_failure(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.insights_default_response = {"success": False, "error": "boom"}

    response = await client.get("/api/v1/stats/instagram_insights?period=last_month")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5008
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_instagram_account_insights_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_response = {
        "success": True,
        "data": {
            "username": "ichatico_app_test_acc",
            "media_count": 6,
            "followers_count": 122,
            "follows_count": 0,
            "id": "24857059897262720",
        },
    }

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["username"] == "ichatico_app_test_acc"
    assert body["payload"]["followers_count"] == 122


@pytest.mark.asyncio
async def test_instagram_account_insights_failure(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_response = {"success": False, "error": "fail"}

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5009
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_instagram_account_insights_exception(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_error = RuntimeError("boom")

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5009
    assert body["payload"] is None
