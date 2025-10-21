import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_telegram_test_connection(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/telegram/test-connection")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_telegram_test_notification_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    telegram_service = integration_environment["telegram_service"]

    response = await client.post("/api/v1/telegram/test-notification")
    assert response.status_code == 200
    assert len(telegram_service.notifications) == 1


@pytest.mark.asyncio
async def test_telegram_test_notification_failure(integration_environment):
    client: AsyncClient = integration_environment["client"]
    telegram_service = integration_environment["telegram_service"]
    telegram_service.should_fail_notification = True

    response = await client.post("/api/v1/telegram/test-notification")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_telegram_test_log_alert_invalid_level(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.post("/api/v1/telegram/test-log-alert", params={"level": "unknown"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_telegram_test_log_alert_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    telegram_service = integration_environment["telegram_service"]
    response = await client.post("/api/v1/telegram/test-log-alert", params={"level": "error"})
    assert response.status_code == 200
    await asyncio.sleep(0)  # allow background log task to complete
    assert telegram_service.log_alerts
