import json

import pytest
from httpx import AsyncClient

from core.utils.time import now_db_utc

from tests.integration.helpers import fetch_classification, fetch_comment


@pytest.mark.asyncio
async def test_webhook_verification_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.get(
        "/api/v1/webhook/",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-token",
            "hub.verify_token": "verify_token",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-token"


@pytest.mark.asyncio
async def test_webhook_verification_invalid_token(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.get(
        "/api/v1/webhook/",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-token",
            "hub.verify_token": "wrong",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(integration_environment):
    client: AsyncClient = integration_environment["client"]
    payload = {"object": "instagram", "entry": []}
    response = await client.post("/api/v1/webhook/", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_invalid_payload_returns_422(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": 10,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "c1",
                            "media": {"id": "m1"},
                            "text": "",
                            "from": {"id": "u1", "username": "user!"},
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await client.post(
        "/api/v1/webhook/",
        content=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_process_comment_success(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_123",
                            "media": {"id": "media_123", "media_product_type": "FEED"},
                            "text": "Test comment",
                            "from": {"id": "user_123", "username": "testuser"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await client.post(
        "/api/v1/webhook/",
        content=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    comment = await fetch_comment(session_factory, "comment_123")
    assert comment is not None
    assert comment.media_id == "media_123"
    assert comment.text == "Test comment"

    classification = await fetch_classification(session_factory, "comment_123")
    assert classification is not None
    assert classification.processing_status.name == "PENDING"

    assert any(
        entry["task"] == "core.tasks.classification_tasks.classify_comment_task"
        and entry["args"][0] == "comment_123"
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_webhook_invalid_signature(integration_environment):
    client: AsyncClient = integration_environment["client"]
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [],
            }
        ],
    }
    body = json.dumps(payload).encode()
    response = await client.post(
        "/api/v1/webhook/",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert response.status_code == 401
